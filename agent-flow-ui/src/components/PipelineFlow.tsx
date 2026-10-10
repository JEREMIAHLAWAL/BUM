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
      <div className="flow-empty-state">
        <p>No active run selected. Select a run from the history sidebar.</p>
      </div>
    );
  }

  const { stages } = run;
  const fileOperations = run.files_changed?.operations || [];
  const latestOps = fileOperations.slice(-4);

  // Compute overall progress & active stage index
  const stageOrder = ['planner', 'frontend', 'backend', 'tester', 'reviewer'];
  let activeStepIndex = 0;
  if (stages.reviewer.status === 'running' || stages.reviewer.status === 'complete') activeStepIndex = 4;
  else if (stages.tester.status === 'running' || stages.tester.status === 'complete') activeStepIndex = 3;
  else if (stages.backend.status === 'running' || stages.backend.status === 'complete') activeStepIndex = 2;
  else if (stages.frontend.status === 'running' || stages.frontend.status === 'complete') activeStepIndex = 1;
  else if (stages.planner.status === 'running' || stages.planner.status === 'complete') activeStepIndex = 0;

  const progressPercent = Math.min(100, Math.round(((activeStepIndex + (stages[stageOrder[activeStepIndex] as keyof typeof stages].status === 'complete' ? 1 : 0.5)) / stageOrder.length) * 100));

  const renderStatusIcon = (status: StageStatus) => {
    switch (status) {
      case 'running':
        return <span className="stage-status-icon running">⏳</span>;
      case 'complete':
        return <span className="stage-status-icon complete">✔</span>;
      case 'failed':
        return <span className="stage-status-icon failed">⚠</span>;
      case 'blocked':
        return <span className="stage-status-icon blocked">✖</span>;
      case 'cancelled':
        return <span className="stage-status-icon cancelled">⏹</span>;
      default:
        return <span className="stage-status-icon waiting">○</span>;
    }
  };

  const formatDuration = (sec?: number | null) => {
    if (sec === undefined || sec === null) return '--';
    return `${sec.toFixed(1)}s`;
  };

  return (
    <div className="pipeline-flow-container">
      <div className="flow-title-bar">
        <div className="flow-title-left">
          <span className="flow-title">PIPELINE EXECUTION GRAPH</span>
          <span className="flow-subtitle">Planner → Frontend → Backend → Tester → Reviewer</span>
        </div>
        <div className="flow-progress-meta">
          <span className="flow-cycle-badge">
            Cycle: {run.current_cycle || 1}/{run.max_review_cycles}
          </span>
          <span className="flow-percent-text">{progressPercent}% Completed</span>
        </div>
      </div>

      {/* Stage Progress Bar & Real-Time Indicator */}
      <div className="stage-progress-bar-container">
        <div
          className="stage-progress-bar-fill"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Real-Time File Stream / Activity Badges */}
      {latestOps.length > 0 && (
        <div className="active-file-stream-bar">
          <div className="file-stream-label">
            <span className="stream-pulse-dot" />
            <span>REAL-TIME FILE OPERATIONS:</span>
          </div>
          <div className="file-stream-pills">
            {latestOps.map((op, idx) => (
              <span
                key={idx}
                className={`file-stream-pill ${op.status} ${op.op}`}
                title={`Stage: ${op.stage} | ${op.status}`}
              >
                <span className="file-op-icon">{op.status === 'in_progress' ? '⚡' : '✔'}</span>
                <span className="file-op-type">{op.op.toUpperCase()}:</span>
                <span className="file-op-path">{op.path}</span>
                {op.bytes !== undefined && op.bytes > 0 && (
                  <span className="file-op-bytes">({(op.bytes / 1024).toFixed(1)} KB)</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flow-stages-row">
        {/* 1. PLANNER */}
        <div
          className={`stage-card ${stages.planner.status} ${
            selectedStage === 'planner' ? 'selected' : ''
          }`}
          onClick={() => onSelectStage('planner')}
        >
          <div className="stage-card-header">
            <span className="stage-num">[1]</span>
            <span className="stage-name">Planner</span>
            {renderStatusIcon(stages.planner.status)}
          </div>
          <div className="stage-card-body">
            <div className="stage-info-row">
              <span className="info-key">Model:</span>
              <span className="info-val" title={stages.planner.model || 'gemini-2.5-flash'}>
                {stages.planner.model ? stages.planner.model.split('/').pop() : 'gemini-2.5-flash'}
              </span>
            </div>
            <div className="stage-info-row">
              <span className="info-key">Provider:</span>
              <span className="info-val">{stages.planner.provider || 'openrouter'}</span>
            </div>
            <div className="stage-info-row">
              <span className="info-key">Time:</span>
              <span className="info-val">{formatDuration(stages.planner.duration_sec)}</span>
            </div>
          </div>
          <div className="stage-card-footer">
            <span className={`status-pill ${stages.planner.status}`}>
              {stages.planner.status.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="stage-connector">➔</div>

        {/* 2. FRONTEND */}
        <div
          className={`stage-card ${stages.frontend.status} ${
            selectedStage === 'frontend' ? 'selected' : ''
          }`}
          onClick={() => onSelectStage('frontend')}
        >
          <div className="stage-card-header">
            <span className="stage-num">[2]</span>
            <span className="stage-name">Frontend</span>
            {renderStatusIcon(stages.frontend.status)}
          </div>
          <div className="stage-card-body">
            <div className="stage-info-row">
              <span className="info-key">Model:</span>
              <span className="info-val" title={stages.frontend.attempts[0]?.model || 'gemini-2.5-pro'}>
                {stages.frontend.attempts[0]?.model
                  ? stages.frontend.attempts[0].model.split('/').pop()
                  : 'gemini-2.5-pro'}
              </span>
            </div>
            <div className="stage-info-row">
              <span className="info-key">Attempts:</span>
              <span className="info-val">{stages.frontend.attempts.length || 0}</span>
            </div>
            {/* Multiple Attempts List */}
            {stages.frontend.attempts.length > 0 && (
              <div className="attempts-pill-list">
                {stages.frontend.attempts.map((att, idx) => (
                  <div
                    key={idx}
                    className={`attempt-pill ${att.status} ${
                      selectedStage === 'frontend' && selectedAttemptIndex === idx ? 'active' : ''
                    }`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectStage('frontend', idx);
                    }}
                  >
                    <span>{att.type === 'repair' ? `Repair C${att.cycle}` : 'Initial'}</span>
                    <span className="att-time">{formatDuration(att.duration_sec)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="stage-card-footer">
            <span className={`status-pill ${stages.frontend.status}`}>
              {stages.frontend.status.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="stage-connector">➔</div>

        {/* 3. BACKEND */}
        <div
          className={`stage-card ${stages.backend.status} ${
            selectedStage === 'backend' ? 'selected' : ''
          }`}
          onClick={() => onSelectStage('backend')}
        >
          <div className="stage-card-header">
            <span className="stage-num">[3]</span>
            <span className="stage-name">Backend</span>
            {renderStatusIcon(stages.backend.status)}
          </div>
          <div className="stage-card-body">
            <div className="stage-info-row">
              <span className="info-key">Model:</span>
              <span className="info-val" title={stages.backend.attempts[0]?.model || 'gemini-2.5-pro'}>
                {stages.backend.attempts[0]?.model
                  ? stages.backend.attempts[0].model.split('/').pop()
                  : 'gemini-2.5-pro'}
              </span>
            </div>
            <div className="stage-info-row">
              <span className="info-key">Attempts:</span>
              <span className="info-val">{stages.backend.attempts.length || 0}</span>
            </div>
            {stages.backend.attempts.length > 0 && (
              <div className="attempts-pill-list">
                {stages.backend.attempts.map((att, idx) => (
                  <div
                    key={idx}
                    className={`attempt-pill ${att.status} ${
                      selectedStage === 'backend' && selectedAttemptIndex === idx ? 'active' : ''
                    }`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectStage('backend', idx);
                    }}
                  >
                    <span>{att.type === 'repair' ? `Repair C${att.cycle}` : 'Initial'}</span>
                    <span className="att-time">{formatDuration(att.duration_sec)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="stage-card-footer">
            <span className={`status-pill ${stages.backend.status}`}>
              {stages.backend.status.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="stage-connector">➔</div>

        {/* 4. TESTER */}
        <div
          className={`stage-card ${stages.tester.status} ${
            selectedStage === 'tester' ? 'selected' : ''
          }`}
          onClick={() => onSelectStage('tester')}
        >
          <div className="stage-card-header">
            <span className="stage-num">[4]</span>
            <span className="stage-name">Tester</span>
            {renderStatusIcon(stages.tester.status)}
          </div>
          <div className="stage-card-body">
            <div className="stage-info-row">
              <span className="info-key">Model:</span>
              <span className="info-val" title={stages.tester.attempts[0]?.model || 'deepseek-v4-flash'}>
                {stages.tester.attempts[0]?.model
                  ? stages.tester.attempts[0].model.split('/').pop()
                  : 'deepseek-v4-flash'}
              </span>
            </div>
            <div className="stage-info-row">
              <span className="info-key">Runs:</span>
              <span className="info-val">{stages.tester.attempts.length || 0}</span>
            </div>
            {stages.tester.attempts.length > 0 && (
              <div className="attempts-pill-list">
                {stages.tester.attempts.map((att, idx) => (
                  <div
                    key={idx}
                    className={`attempt-pill ${att.status} ${
                      selectedStage === 'tester' && selectedAttemptIndex === idx ? 'active' : ''
                    }`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectStage('tester', idx);
                    }}
                  >
                    <span>Cycle {att.cycle}</span>
                    <span className="att-time">{formatDuration(att.duration_sec)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="stage-card-footer">
            <span className={`status-pill ${stages.tester.status}`}>
              {stages.tester.status.toUpperCase()}
            </span>
          </div>
        </div>

        <div className="stage-connector">➔</div>

        {/* 5. REVIEWER */}
        <div
          className={`stage-card ${stages.reviewer.status} ${
            selectedStage === 'reviewer' ? 'selected' : ''
          }`}
          onClick={() => onSelectStage('reviewer')}
        >
          <div className="stage-card-header">
            <span className="stage-num">[5]</span>
            <span className="stage-name">Reviewer</span>
            {renderStatusIcon(stages.reviewer.status)}
          </div>
          <div className="stage-card-body">
            <div className="stage-info-row">
              <span className="info-key">Model:</span>
              <span className="info-val" title={stages.reviewer.attempts[0]?.model || 'claude-sonnet-5'}>
                {stages.reviewer.attempts[0]?.model
                  ? stages.reviewer.attempts[0].model.split('/').pop()
                  : 'claude-sonnet-5'}
              </span>
            </div>
            <div className="stage-info-row">
              <span className="info-key">Verdict:</span>
              <span className="info-val verdict-tag">{run.review?.verdict || '--'}</span>
            </div>
            {stages.reviewer.attempts.length > 0 && (
              <div className="attempts-pill-list">
                {stages.reviewer.attempts.map((att, idx) => (
                  <div
                    key={idx}
                    className={`attempt-pill ${att.status} ${
                      selectedStage === 'reviewer' && selectedAttemptIndex === idx ? 'active' : ''
                    }`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectStage('reviewer', idx);
                    }}
                  >
                    <span>Cycle {att.cycle}</span>
                    <span className="att-time">{formatDuration(att.duration_sec)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="stage-card-footer">
            <span className={`status-pill ${stages.reviewer.status}`}>
              {stages.reviewer.status.toUpperCase()}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
