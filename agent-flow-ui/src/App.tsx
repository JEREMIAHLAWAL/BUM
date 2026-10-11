import React, { useEffect, useState, useCallback, useRef } from 'react';
import type { RunState, RunSummary } from './types';
import {
  fetchRuns,
  fetchRunDetails,
  subscribeToRunEvents,
  fetchPipelineStatus,
  launchPipeline,
  stopPipeline,
  retryPipelineRun,
  resumePipelineRun,
  approveRun,
  rejectRun,
  purgeRuns,
  deleteSingleRun,
  fetchProjects,
  selectProject,
} from './api';
import type { WorkspaceProject, VersionInfo } from './api';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { TaskInputBar } from './components/TaskInputBar';
import { PipelineFlow } from './components/PipelineFlow';
import { InspectionPanel } from './components/InspectionPanel';
import { ReviewRail } from './components/ReviewRail';
import './App.css';

export const App: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [currentRunState, setCurrentRunState] = useState<RunState | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>('planner');
  const [selectedAttemptIndex, setSelectedAttemptIndex] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isPipelineRunning, setIsPipelineRunning] = useState<boolean>(false);
  const [isCancellationRequested, setIsCancellationRequested] = useState<boolean>(false);
  const [activePipelineRunId, setActivePipelineRunId] = useState<string | null>(null);
  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [activeProjectPath, setActiveProjectPath] = useState<string>('');
  const [draftTask, setDraftTask] = useState<string>('');
  const [draftLabel, setDraftLabel] = useState<string>('');
  const [audioEnabled, setAudioEnabled] = useState<boolean>(false);
  const [isCommandMenuOpen, setIsCommandMenuOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState('');
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  // Lifted from InspectionPanel so ReviewRail's "View diff" button can
  // switch to the Changes tab — it used to be a no-op (onShowChanges={() => {}}).
  const [inspectionActiveTab, setInspectionActiveTab] = useState<'activity' | 'tests' | 'changes' | 'review'>('activity');
  // Mobile hamburger menu used to have no state to open — Header's
  // onOpenSidebar prop was never even passed, and .desktop-sidebar is
  // display:none below 860px with no mobile equivalent rendered anywhere.
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  // Deployed-code version visibility: surfaces is_stale/warning from
  // /api/projects (which now embeds get_version_info()'s output) so a
  // Syncthing-synced-but-not-restarted bum-agent-flow service is visible
  // in the UI before a run gets burned on stale code.
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);

  const activeRunIdRef = useRef<string | null>(null);
  const prevRunStatusRef = useRef<string | null>(null);
  activeRunIdRef.current = activePipelineRunId;

  // Sound Chime Generator using Web Audio API
  const playChime = useCallback((type: 'success' | 'failure') => {
    if (!audioEnabled) return;
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === 'success') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, ctx.currentTime);
        osc.frequency.setValueAtTime(880, ctx.currentTime + 0.12);
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.start();
        osc.stop(ctx.currentTime + 0.4);
      } else {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(329.63, ctx.currentTime);
        osc.frequency.setValueAtTime(220, ctx.currentTime + 0.15);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
        osc.start();
        osc.stop(ctx.currentTime + 0.45);
      }
    } catch {
      // Audio autoplay policy
    }
  }, [audioEnabled]);

  // Load available workspace projects
  const loadProjects = useCallback(async () => {
    try {
      const data = await fetchProjects();
      setProjects(data.projects);
      setActiveProjectPath(data.active_path);
      setVersionInfo(data.version || null);
    } catch {
      // non-fatal
    }
  }, []);

  const handleSelectProject = async (pathOrId: string) => {
    try {
      const data = await selectProject(pathOrId);
      setProjects(data.projects);
      setActiveProjectPath(data.active_path);
      await loadRuns();
    } catch (err: any) {
      setErrorMsg(`Failed to switch project: ${err.message}`);
    }
  };

  // Check pipeline execution status
  const checkPipelineStatus = useCallback(async () => {
    try {
      const status = await fetchPipelineStatus();
      setIsPipelineRunning(status.running);
      setIsCancellationRequested(Boolean(status.cancellation_requested));
      setActivePipelineRunId(status.run_id);

      if (status.running && status.run_id && status.run_id !== selectedRunId) {
        setSelectedRunId(status.run_id);
      }
    } catch {
      // non-fatal
    }
  }, [selectedRunId]);

  // Load runs list
  const loadRuns = useCallback(async () => {
    try {
      const data = await fetchRuns();
      setRuns(data);
      if (data.length > 0 && !selectedRunId) {
        setSelectedRunId(data[0].run_id);
      }
      setErrorMsg(null);
    } catch (err: any) {
      setErrorMsg(`Cannot connect to BUM API: ${err.message}`);
    }
  }, [selectedRunId]);

  // Load specific run details
  const loadRunState = useCallback(async (runId: string) => {
    try {
      const state = await fetchRunDetails(runId);
      const newStatus = (state.status || '').toLowerCase();
      const prevStatus = prevRunStatusRef.current;

      if (prevStatus && prevStatus !== newStatus) {
        if (newStatus === 'awaiting_human_approval' || newStatus === 'approved') {
          playChime('success');
        } else if (newStatus === 'failed' || newStatus === 'blocked' || newStatus === 'interrupted') {
          playChime('failure');
        }
      }
      prevRunStatusRef.current = newStatus;

      setCurrentRunState(state);
      setErrorMsg(null);
    } catch (err: any) {
      setErrorMsg(`Failed to load run ${runId}: ${err.message}`);
    }
  }, [playChime]);

  useEffect(() => {
    loadProjects();
    loadRuns();
    checkPipelineStatus();
  }, [loadProjects, loadRuns, checkPipelineStatus]);

  useEffect(() => {
    const interval = setInterval(() => {
      checkPipelineStatus();
      loadRuns();
    }, 3000);

    const onFocus = () => {
      checkPipelineStatus();
      loadRuns();
    };

    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, [checkPipelineStatus, loadRuns]);

  useEffect(() => {
    if (selectedRunId) {
      loadRunState(selectedRunId);
    }
  }, [selectedRunId, loadRunState]);

  useEffect(() => {
    if (!selectedRunId) return;

    const isFinished =
      currentRunState?.status &&
      currentRunState.status !== 'running' &&
      currentRunState.status !== 'awaiting_human_approval' &&
      currentRunState.status !== 'empty';

    if (isFinished) {
      setIsConnected(false);
      return;
    }

    const unsubscribe = subscribeToRunEvents(
      selectedRunId,
      () => {
        loadRunState(selectedRunId);
        loadRuns();
        checkPipelineStatus();
      },
      () => {
        setIsConnected(false);
        checkPipelineStatus();
      },
      () => {
        setIsConnected(false);
      }
    );

    setIsConnected(true);
    return () => {
      unsubscribe();
      setIsConnected(false);
    };
  }, [selectedRunId, currentRunState?.status, loadRunState, loadRuns, checkPipelineStatus]);

  // Global Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandMenuOpen((open) => !open);
      }
      if (e.key === '/' && !e.metaKey && !e.ctrlKey && !(e.target instanceof HTMLElement && (e.target.matches('input,textarea,select') || e.target.isContentEditable))) {
        e.preventDefault();
        document.getElementById('task-prompt')?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleDeleteRun = async (runId: string) => {
    try {
      await deleteSingleRun(runId);
      if (selectedRunId === runId) {
        setSelectedRunId(null);
        setCurrentRunState(null);
      }
      await loadRuns();
    } catch (err: any) {
      setErrorMsg(`Failed to delete run: ${err.message}`);
    }
  };

  const handlePurgeRuns = async () => {
    try {
      await purgeRuns();
      setSelectedRunId(null);
      setCurrentRunState(null);
      await loadRuns();
    } catch (err: any) {
      setErrorMsg(`Failed to purge runs: ${err.message}`);
    }
  };

  const handleLaunchTask = async (task: string, label?: string) => {
    try {
      const res = await launchPipeline(task, label);
      if (res.run_id) {
        setSelectedRunId(res.run_id);
        setIsPipelineRunning(true);
        setIsCancellationRequested(false);
        setActivePipelineRunId(res.run_id);
        setSelectedStage('planner');
        setSelectedAttemptIndex(null);
        await loadRuns();
        await loadRunState(res.run_id);
      }
    } catch (err: any) {
      if (err.status === 409) {
        setErrorMsg(`Pipeline is already running (Run: ${err.run_id || 'in progress'}).`);
        if (err.run_id) {
          setSelectedRunId(err.run_id);
        }
      } else {
        setErrorMsg(`Failed to launch pipeline: ${err.message}`);
      }
      throw err;
    }
  };

  const handleStopPipeline = async () => {
    try {
      await stopPipeline(activePipelineRunId);
      setIsCancellationRequested(true);
      await checkPipelineStatus();
    } catch (err: any) {
      setErrorMsg(`Failed to stop pipeline: ${err.message}`);
      throw err;
    }
  };

  const handleRetryRun = async () => {
    if (!selectedRunId) return;
    try {
      const res = await retryPipelineRun(selectedRunId);
      if (res.run_id) {
        setSelectedRunId(res.run_id);
        setIsPipelineRunning(true);
        setIsCancellationRequested(false);
        setActivePipelineRunId(res.run_id);
        setSelectedStage('planner');
        setSelectedAttemptIndex(null);
        await loadRuns();
        await loadRunState(res.run_id);
      }
    } catch (err: any) {
      if (err.status === 409) {
        setErrorMsg(`Pipeline is already running (Run: ${err.run_id || 'in progress'}).`);
        if (err.run_id) {
          setSelectedRunId(err.run_id);
        }
      } else {
        setErrorMsg(`Failed to retry run: ${err.message}`);
      }
      throw err;
    }
  };

  const handleResumeRun = async () => {
    if (!selectedRunId) return;
    try {
      const res = await resumePipelineRun(selectedRunId);
      if (res.run_id) {
        setSelectedRunId(res.run_id);
        setIsPipelineRunning(true);
        setIsCancellationRequested(false);
        setActivePipelineRunId(res.run_id);
        setSelectedStage('tester');
        setSelectedAttemptIndex(null);
        await loadRuns();
        await loadRunState(res.run_id);
      }
    } catch (err: any) {
      if (err.status === 409) {
        setErrorMsg(`Pipeline is already running (Run: ${err.run_id || 'in progress'}).`);
        if (err.run_id) {
          setSelectedRunId(err.run_id);
        }
      } else {
        setErrorMsg(`Failed to resume run: ${err.message}`);
      }
      throw err;
    }
  };

  const handleApproveRun = async () => {
    if (!selectedRunId) return;
    try {
      await approveRun(selectedRunId);
      await loadRunState(selectedRunId);
      await loadRuns();
    } catch (err: any) {
      setErrorMsg(`Failed to approve run: ${err.message}`);
      throw err;
    }
  };

  const handleRejectRun = async (reason?: string) => {
    if (!selectedRunId) return;
    try {
      await rejectRun(selectedRunId, reason);
      await loadRunState(selectedRunId);
      await loadRuns();
    } catch (err: any) {
      setErrorMsg(`Failed to reject run: ${err.message}`);
      throw err;
    }
  };

  const handleSelectStage = (stageName: string, attemptIndex?: number) => {
    setSelectedStage(stageName);
    setSelectedAttemptIndex(attemptIndex !== undefined ? attemptIndex : null);
  };

  const selectedRunSummary = runs.find((r) => r.run_id === selectedRunId);
  const summaryStatus = (selectedRunSummary?.final_status || '').toLowerCase();
  const runStatus = (currentRunState?.status || '').toLowerCase();

  const isAwaitingApproval =
    runStatus === 'awaiting_human_approval' ||
    summaryStatus === 'awaiting_human_approval' ||
    runStatus === 'approve' ||
    summaryStatus === 'approve';

  const isHumanDecisionEligible = Boolean(
    selectedRunId &&
    !isPipelineRunning &&
    isAwaitingApproval
  );

  const isRetryEligible = Boolean(
    selectedRunId &&
    !isPipelineRunning &&
    !isHumanDecisionEligible &&
    ['failed', 'blocked', 'cancelled', 'canceled', 'interrupted', 'stale', 'empty', 'rejected'].some(
      (s) => runStatus === s || summaryStatus === s
    )
  );

  const activeWorkspace = projects.find((p) => p.path === activeProjectPath) || {
    id: 'bum',
    name: 'BUM orchestrator',
    path: activeProjectPath || '~/projects/bum',
    exists: true,
    is_active: true,
    type: 'workspace',
  };

  const formatDuration = (sec?: number | null) => {
    if (sec === undefined || sec === null) return '--';
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const m = Math.floor(sec / 60);
    const rem = Math.floor(sec % 60).toString().padStart(2, '0');
    return `${m}m ${rem}s`;
  };

  const formatTime = (ts: number | null) => {
    if (!ts) return 'Ready to build';
    const d = new Date(ts * 1000);
    return `Started ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}`;
  };

  const commandsList = [
    {
      id: 'new',
      label: 'New development task',
      detail: 'Focus the task composer',
      run: () => document.getElementById('task-prompt')?.focus(),
    },
    {
      id: 'audio',
      label: audioEnabled ? 'Disable audio chimes' : 'Enable audio chimes',
      detail: 'Play a chime when a run needs approval',
      run: () => setAudioEnabled(!audioEnabled),
    },
    ...runs.map((r) => ({
      id: r.run_id,
      label: r.label || r.task || r.run_id,
      detail: `Jump to #${r.run_id.split('_').pop()}`,
      run: () => {
        setSelectedRunId(r.run_id);
        setSelectedStage('planner');
      },
    })),
  ];

  const filteredCommands = commandsList.filter((cmd) =>
    `${cmd.label} ${cmd.detail}`.toLowerCase().includes(commandQuery.toLowerCase())
  );

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">Skip to execution console</a>

      <Header
        run={currentRunState}
        selectedRunId={selectedRunId}
        isConnected={isConnected}
        projects={projects}
        activeProjectPath={activeProjectPath}
        onSelectProject={handleSelectProject}
        audioEnabled={audioEnabled}
        onToggleAudio={() => setAudioEnabled(!audioEnabled)}
        onNewTask={() => document.getElementById('task-prompt')?.focus()}
        onCommandMenu={() => setIsCommandMenuOpen(true)}
        onOpenSidebar={() => setIsMobileSidebarOpen(true)}
        onRefresh={() => {
          if (selectedRunId) loadRunState(selectedRunId);
          loadProjects();
          loadRuns();
          checkPipelineStatus();
        }}
      />

      {errorMsg && (
        <div className="toast toast-error" role="alert">
          <span>⚠ {errorMsg}</span>
          <button type="button" className="icon-button" onClick={() => setErrorMsg(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      {versionInfo?.is_stale && (
        <div className="toast toast-error" role="alert" title={versionInfo.warning || undefined}>
          <span>
            ⚠ Stale orchestrator code running — boot commit {versionInfo.boot_commit?.slice(0, 7) || '?'}, disk has{' '}
            {versionInfo.current_commit_on_disk?.slice(0, 7) || '?'} ({versionInfo.current_commit_message || 'newer commit'}).
            Restart bum-agent-flow to pick it up.
          </span>
        </div>
      )}

      <div className="app-body">
        <div className="desktop-sidebar">
          <Sidebar
            runs={runs}
            selectedRunId={selectedRunId}
            onSelectRun={(runId) => {
              setSelectedRunId(runId);
              setSelectedStage('planner');
              setSelectedAttemptIndex(null);
            }}
            onStop={handleStopPipeline}
            onRetry={handleRetryRun}
            onResume={handleResumeRun}
            onClone={(task, label) => {
              setDraftTask(task);
              setDraftLabel(label || '');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            onApprove={handleApproveRun}
            onReject={handleRejectRun}
            onDeleteRun={handleDeleteRun}
            onPurgeRuns={handlePurgeRuns}
            isPipelineRunning={isPipelineRunning}
            isCancellationRequested={isCancellationRequested}
            isRetryEligible={isRetryEligible}
            isHumanDecisionEligible={isHumanDecisionEligible}
            workspace={activeWorkspace}
          />
        </div>

        {isMobileSidebarOpen && (
          <div
            className="mobile-sidebar-overlay"
            onClick={() => setIsMobileSidebarOpen(false)}
            role="presentation"
          >
            <div
              className="mobile-sidebar-panel"
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-modal="true"
              aria-label="Run history"
            >
              <button
                type="button"
                className="icon-button mobile-sidebar-close"
                aria-label="Close run history"
                onClick={() => setIsMobileSidebarOpen(false)}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
              <Sidebar
                runs={runs}
                selectedRunId={selectedRunId}
                onSelectRun={(runId) => {
                  setSelectedRunId(runId);
                  setSelectedStage('planner');
                  setSelectedAttemptIndex(null);
                  setIsMobileSidebarOpen(false);
                }}
                onStop={handleStopPipeline}
                onRetry={handleRetryRun}
                onResume={handleResumeRun}
                onClone={(task, label) => {
                  setDraftTask(task);
                  setDraftLabel(label || '');
                  setIsMobileSidebarOpen(false);
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                onApprove={handleApproveRun}
                onReject={handleRejectRun}
                onDeleteRun={handleDeleteRun}
                onPurgeRuns={handlePurgeRuns}
                isPipelineRunning={isPipelineRunning}
                isCancellationRequested={isCancellationRequested}
                isRetryEligible={isRetryEligible}
                isHumanDecisionEligible={isHumanDecisionEligible}
                workspace={activeWorkspace}
              />
            </div>
          </div>
        )}

        <main className="main-content" id="main-content" tabIndex={-1}>
          {/* Run Header */}
          <div className="run-header">
            <div className="run-heading">
              <div className="run-breadcrumb">
                Runs
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m9 18 6-6-6-6" />
                </svg>
                <span className="mono" title={selectedRunId || ''}>
                  #{selectedRunId ? selectedRunId.split('_').pop() : 'Workspace'}
                </span>
                <span className="run-start-time">
                  {formatTime(currentRunState?.started_at || null)}
                </span>
              </div>

              <div className="run-title-row">
                <h1>{currentRunState?.label || currentRunState?.task || 'Start your next development task'}</h1>
                {currentRunState && (
                  <span className={`status-badge tone-${isAwaitingApproval ? 'warning' : currentRunState.status === 'approved' ? 'success' : currentRunState.status === 'running' ? 'accent' : 'neutral'}`}>
                    {currentRunState.status.toUpperCase()}
                  </span>
                )}
              </div>
            </div>

            {currentRunState && (
              <div className="run-header-actions">
                <button
                  type="button"
                  className="quiet-button"
                  onClick={() => {
                    setDraftTask(currentRunState.task || '');
                    setDraftLabel(currentRunState.label || '');
                    document.getElementById('task-prompt')?.focus();
                  }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
                    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                  </svg>
                  <span>View prompt</span>
                </button>

                {isPipelineRunning ? (
                  <button
                    type="button"
                    className="button button-small"
                    onClick={handleStopPipeline}
                    disabled={isCancellationRequested}
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect width="18" height="18" x="3" y="3" rx="2" />
                    </svg>
                    Cancel run
                  </button>
                ) : (
                  <button
                    type="button"
                    className="icon-button"
                    title="Retry in a new run"
                    aria-label="Retry selected run"
                    onClick={handleRetryRun}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                      <path d="M3 3v5h5" />
                    </svg>
                  </button>
                )}
              </div>
            )}
          </div>

          <TaskInputBar
            onLaunch={handleLaunchTask}
            onStop={handleStopPipeline}
            isPipelineRunning={isPipelineRunning}
            isCancellationRequested={isCancellationRequested}
            activeRunId={activePipelineRunId}
            initialTask={draftTask}
            initialLabel={draftLabel}
            onClearInitial={() => {
              setDraftTask('');
              setDraftLabel('');
            }}
          />

          <PipelineFlow
            run={currentRunState}
            selectedStage={selectedStage}
            selectedAttemptIndex={selectedAttemptIndex}
            onSelectStage={handleSelectStage}
          />

          <div className="evidence-layout">
            <InspectionPanel
              run={currentRunState}
              selectedStage={selectedStage}
              selectedAttemptIndex={selectedAttemptIndex}
              onSelectStage={handleSelectStage}
              activeTab={inspectionActiveTab}
              onActiveTabChange={setInspectionActiveTab}
            />

            <ReviewRail
              run={currentRunState}
              disabled={isPipelineRunning}
              onApprove={handleApproveRun}
              onReject={handleRejectRun}
              onResume={handleResumeRun}
              onRetry={handleRetryRun}
              onShowChanges={() => setInspectionActiveTab('changes')}
              activeProjectPath={activeProjectPath}
            />
          </div>
        </main>
      </div>

      <footer className="app-statusbar">
        <span>
          <i className={`status-dot ${isConnected ? '' : 'connection-offline'}`} />
          {isConnected ? 'Agent engine' : 'Offline'}
          <span className="statusbar-separator">/</span>
          {runs.filter((r) => r.final_status.toLowerCase() === 'running').length} running
          <span className="statusbar-separator">/</span>
          {runs.filter((r) => ['awaiting_human_approval', 'awaiting approval', 'approve'].includes(r.final_status.toLowerCase())).length} awaiting review
        </span>

        <span>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="6" x2="6" y1="3" y2="15" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <path d="M18 9a9 9 0 0 1-9 9" />
          </svg>
          main
          <span className="statusbar-separator">/</span>
          {formatDuration(currentRunState?.total_duration_sec)}
          <button type="button" onClick={() => setIsCommandMenuOpen(true)}>
            <kbd>⌘ / Ctrl K</kbd>
            Commands
          </button>
        </span>
      </footer>

      {isCommandMenuOpen && (
        <div className="modal-overlay" onClick={() => setIsCommandMenuOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Command menu</h2>
              <button type="button" className="icon-button" onClick={() => setIsCommandMenuOpen(false)} aria-label="Close dialog">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>
            <div className="command-menu">
              <label className="command-search">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <input
                  autoFocus
                  placeholder="Search commands or jump to a run…"
                  value={commandQuery}
                  onChange={(e) => {
                    setCommandQuery(e.target.value);
                    setSelectedCommandIndex(0);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      setSelectedCommandIndex((i) => (i + 1) % filteredCommands.length);
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      setSelectedCommandIndex((i) => (i - 1 + filteredCommands.length) % filteredCommands.length);
                    } else if (e.key === 'Enter') {
                      e.preventDefault();
                      if (filteredCommands[selectedCommandIndex]) {
                        filteredCommands[selectedCommandIndex].run();
                        setIsCommandMenuOpen(false);
                      }
                    } else if (e.key === 'Escape') {
                      setIsCommandMenuOpen(false);
                    }
                  }}
                />
              </label>

              <div className="command-results" role="listbox">
                {filteredCommands.length === 0 ? (
                  <p className="muted">No matching commands.</p>
                ) : (
                  filteredCommands.map((cmd, idx) => (
                    <button
                      key={cmd.id}
                      type="button"
                      className={idx === selectedCommandIndex ? 'is-active' : ''}
                      onClick={() => {
                        cmd.run();
                        setIsCommandMenuOpen(false);
                      }}
                      onMouseEnter={() => setSelectedCommandIndex(idx)}
                    >
                      <span>
                        {cmd.label}
                        <small>{cmd.detail}</small>
                      </span>
                      {idx === selectedCommandIndex && (
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="9 10 4 15 9 20" />
                          <path d="M20 4v7a4 4 0 0 1-4 4H4" />
                        </svg>
                      )}
                    </button>
                  ))
                )}
              </div>

              <div className="command-menu-footer">
                <span>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m5 12 7-7 7 7" />
                    <path d="M12 19V5" />
                  </svg>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 5v14" />
                    <path d="m19 12-7 7-7-7" />
                  </svg>
                  to navigate
                </span>
                <span>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="9 10 4 15 9 20" />
                    <path d="M20 4v7a4 4 0 0 1-4 4H4" />
                  </svg>
                  to select
                </span>
                <span>
                  <kbd>esc</kbd>
                  to close
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default App;
