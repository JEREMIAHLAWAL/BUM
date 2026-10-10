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
import type { WorkspaceProject } from './api';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { TaskInputBar } from './components/TaskInputBar';
import { PipelineFlow } from './components/PipelineFlow';
import { StageDetailPanel } from './components/StageDetailPanel';
import { TestsPanel } from './components/TestsPanel';
import { GitFilesPanel } from './components/GitFilesPanel';
import { ReviewTimelinePanel } from './components/ReviewTimelinePanel';
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

  const activeRunIdRef = useRef<string | null>(null);
  const prevRunStatusRef = useRef<string | null>(null);
  activeRunIdRef.current = activePipelineRunId;

  // Sound Chime Generator using Web Audio API
  const playChime = useCallback((type: 'success' | 'failure') => {
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
        osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
        osc.frequency.setValueAtTime(880, ctx.currentTime + 0.12); // A5
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.start();
        osc.stop(ctx.currentTime + 0.4);
      } else {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(329.63, ctx.currentTime); // E4
        osc.frequency.setValueAtTime(220, ctx.currentTime + 0.15); // A3
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.45);
        osc.start();
        osc.stop(ctx.currentTime + 0.45);
      }
    } catch {
      // Audio autoplay policy may block in unfocused tabs until user interaction
    }
  }, []);

  // Load available workspace projects
  const loadProjects = useCallback(async () => {
    try {
      const data = await fetchProjects();
      setProjects(data.projects);
      setActiveProjectPath(data.active_path);
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

      // Auto-recovery / discovery: if a pipeline is running and not selected, auto-select it
      if (status.running && status.run_id && status.run_id !== selectedRunId) {
        setSelectedRunId(status.run_id);
      }
    } catch {
      // Background check failure is non-fatal
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

  // Initial load
  useEffect(() => {
    loadProjects();
    loadRuns();
    checkPipelineStatus();
  }, [loadProjects, loadRuns, checkPipelineStatus]);

  // Periodic polling for status & discovery (every 3s when idle/active, and window focus)
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

  // When selected run ID changes, fetch details
  useEffect(() => {
    if (selectedRunId) {
      loadRunState(selectedRunId);
    }
  }, [selectedRunId, loadRunState]);

  // SSE Real-time Subscription for active runs
  useEffect(() => {
    if (!selectedRunId) return;

    // Check if the current run is finished
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
        // When any event arrives, refresh state and status
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
        // Immediate selection and subscription
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
    summaryStatus === 'awaiting_human_approval';

  const isHumanDecisionEligible = Boolean(
    selectedRunId &&
    !isPipelineRunning &&
    isAwaitingApproval
  );

  const isRetryEligible = Boolean(
    selectedRunId &&
    !isPipelineRunning &&
    !isHumanDecisionEligible &&
    ['failed', 'blocked', 'cancelled', 'interrupted', 'stale', 'empty', 'rejected'].some(
      (s) => runStatus === s || summaryStatus === s
    )
  );

  return (
    <div className="agent-flow-app">
      <Header
        run={currentRunState}
        selectedRunId={selectedRunId}
        isConnected={isConnected}
        projects={projects}
        activeProjectPath={activeProjectPath}
        onSelectProject={handleSelectProject}
        onClone={(task, label) => {
          setDraftTask(task);
          setDraftLabel(label || '');
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }}
        onRefresh={() => {
          if (selectedRunId) loadRunState(selectedRunId);
          loadProjects();
          loadRuns();
          checkPipelineStatus();
        }}
      />

      {errorMsg && (
        <div className="global-error-toast">
          <span>⚠ {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)}>Dismiss</button>
        </div>
      )}

      <div className="main-layout">
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
        />

        <main className="dashboard-content">
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

          {selectedStage && currentRunState && (
            <StageDetailPanel
              run={currentRunState}
              selectedStage={selectedStage}
              selectedAttemptIndex={selectedAttemptIndex}
              onClose={() => setSelectedStage(null)}
            />
          )}

          <div className="details-two-col-grid">
            <TestsPanel run={currentRunState} />
            <GitFilesPanel run={currentRunState} />
          </div>

          <ReviewTimelinePanel run={currentRunState} />
        </main>
      </div>
    </div>
  );
};

export default App;
