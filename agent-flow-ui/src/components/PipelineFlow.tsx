import React from 'react';
import type { RunState, StageStatus } from '../types';

interface PipelineFlowProps {
  run: RunState | null;
  selectedStage: string | null;
  selectedAttemptIndex: number | null;
  onSelectStage: (stageName: string, attemptIndex?: number) => void;
}

export const PipelineFlow: React.FC<PipelineFlowProps> = ({
  run,
  selectedStage,
  selectedAttemptIndex,
  onSelectStage,
}) => {
  if (!run) {
    return (
      <section className="pipeline-section">
        <div className="panel-empty">No active run selected. Select a run from the history sidebar.</div>
      </section>
    );
  }

  const { stages } = run;
  const stageOrder = ['planner', 'frontend', 'backend', 'tester', 'reviewer'] as const;

  const stageIcons: Record<string, React.ReactNode> = {
    planner: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z" />
        <path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12" />
        <path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17" />
      </svg>
    ),
    frontend: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="m18 16 4-4-4-4" />
        <path d="m6 8-4 4 4 4" />
        <path d="m14.5 4-5 16" />
      </svg>
    ),
    backend: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1" />
        <path d="M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1" />
      </svg>
    ),
    tester: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2" />
        <path d="M6.453 15h11.094" />
        <path d="M8.5 2h7" />
      </svg>
    ),
    reviewer: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
        <path d="m9 12 2 2 4-4" />
      </svg>
    ),
  };

  const stageLabels: Record<string, string> = {
    planner: 'Planner',
    frontend: 'Frontend',
    backend: 'Backend',
    tester: 'Tester',
    reviewer: 'Reviewer',
  };

  const getStageStatus = (stageName: typeof stageOrder[number]): StageStatus => {
    return stages[stageName]?.status || 'waiting';
  };

  const getStageModel = (stageName: typeof stageOrder[number]): string => {
    if (stageName === 'planner') {
      const s = stages.planner;
      return s?.model ? s.model.split('/').pop() || s.model : 'Gemini 2.5 Flash';
    }
    const ms = stages[stageName];
    if (ms?.attempts && ms.attempts.length > 0) {
      const targetAttempt =
        selectedAttemptIndex !== null && selectedStage === stageName && ms.attempts[selectedAttemptIndex]
          ? ms.attempts[selectedAttemptIndex]
          : ms.attempts[ms.attempts.length - 1];
      const m = targetAttempt?.model;
      if (m) return m.split('/').pop() || m;
    }
    return stageName === 'tester' ? 'DeepSeek V3' : stageName === 'reviewer' ? 'Claude Sonnet' : 'Gemini 2.5 Pro';
  };

  const getStageDuration = (stageName: typeof stageOrder[number]): number | null => {
    if (stageName === 'planner') {
      return stages.planner?.duration_sec ?? null;
    }
    const ms = stages[stageName];
    if (ms?.attempts && ms.attempts.length > 0) {
      const targetAttempt =
        selectedAttemptIndex !== null && selectedStage === stageName && ms.attempts[selectedAttemptIndex]
          ? ms.attempts[selectedAttemptIndex]
          : ms.attempts[ms.attempts.length - 1];
      return targetAttempt?.duration_sec ?? null;
    }
    return null;
  };

  const getAttemptsCount = (stageName: typeof stageOrder[number]): number => {
    if (stageName === 'planner') return 1;
    return stages[stageName]?.attempts?.length || 0;
  };

  const formatDuration = (sec?: number | null) => {
    if (sec === undefined || sec === null) return '—';
    return `${sec.toFixed(1)}s`;
  };

  const renderStatusBadge = (status: StageStatus) => {
    switch (status) {
      case 'running':
        return (
          <span className="stage-state stage-running">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin" aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            Running
          </span>
        );
      case 'complete':
        return (
          <span className="stage-state stage-complete">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            Complete
          </span>
        );
      case 'failed':
        return (
          <span className="stage-state stage-failed">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" x2="12" y1="8" y2="12" />
              <line x1="12" x2="12.01" y1="16" y2="16" />
            </svg>
            Failed
          </span>
        );
      case 'blocked':
        return (
          <span className="stage-state stage-blocked">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect width="18" height="18" x="3" y="3" rx="2" />
            </svg>
            Blocked
          </span>
        );
      default:
        return (
          <span className="stage-state stage-waiting">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
            </svg>
            Queued
          </span>
        );
    }
  };

  return (
    <section className="pipeline-section" aria-labelledby="pipeline-title">
      <div className="section-heading">
        <h2 id="pipeline-title">Execution pipeline</h2>
        <div className="cycle-picker">
          <span>Review cycle</span>
          {Array.from({ length: run.max_review_cycles || 3 }, (_, i) => i + 1).map((c) => (
            <button
              key={c}
              type="button"
              className={c === (run.current_cycle || 1) ? 'is-active' : ''}
              disabled={c > (run.current_cycle || 1)}
              title={`Inspect review cycle ${c}`}
            >
              {c < (run.current_cycle || 1) ? (
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              ) : (
                c
              )}
            </button>
          ))}
        </div>
      </div>

      <ol className="pipeline-flow">
        {stageOrder.map((stageName, idx) => {
          const status = getStageStatus(stageName);
          const isSelected = selectedStage === stageName;
          const model = getStageModel(stageName);
          const duration = getStageDuration(stageName);
          const attemptsCount = getAttemptsCount(stageName);

          return (
            <li key={stageName}>
              <button
                type="button"
                className={`pipeline-node node-${status} ${isSelected ? 'is-selected' : ''}`}
                onClick={() => onSelectStage(stageName)}
                aria-pressed={isSelected}
              >
                <div className="node-header">
                  <span className="node-icon">{stageIcons[stageName]}</span>
                  <span className="node-name">{stageLabels[stageName]}</span>
                  <span className="node-number mono">0{idx + 1}</span>
                </div>

                <span className="node-model" title={model}>{model}</span>

                <div className="node-bottom">
                  {renderStatusBadge(status)}
                  <span className="node-duration mono">{formatDuration(duration)}</span>
                </div>

                <div className="node-attempts">
                  {attemptsCount > 1 ? `${attemptsCount} attempts` : '1 attempt'}
                </div>
              </button>

              {idx < stageOrder.length - 1 && (
                <span className="flow-connector" aria-hidden="true">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M5 12h14" />
                    <path d="m12 5 7 7-7 7" />
                  </svg>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
};
