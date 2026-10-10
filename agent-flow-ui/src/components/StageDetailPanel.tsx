import React, { useState } from 'react';
import type { RunState, StageAttempt, SingleStageState } from '../types';

import { copyToClipboard } from '../utils/clipboard';

interface StageDetailPanelProps {
  run: RunState | null;
  selectedStage: string | null;
  selectedAttemptIndex: number | null;
  onClose: () => void;
}

export const StageDetailPanel: React.FC<StageDetailPanelProps> = ({
  run,
  selectedStage,
  selectedAttemptIndex,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);

  if (!run || !selectedStage) return null;

  const stageKey = selectedStage as keyof typeof run.stages;
  const stageData = run.stages[stageKey];

  let currentAttempt: StageAttempt | SingleStageState | null = null;
  let title = selectedStage.toUpperCase();
  let attemptLabel = 'Single Execution';

  if (selectedStage === 'planner' || selectedStage === 'preflight') {
    currentAttempt = stageData as SingleStageState;
  } else if ('attempts' in stageData) {
    const attempts = stageData.attempts;
    if (selectedAttemptIndex !== null && attempts[selectedAttemptIndex]) {
      currentAttempt = attempts[selectedAttemptIndex];
      attemptLabel =
        'type' in currentAttempt && currentAttempt.type === 'repair'
          ? `Repair (Cycle ${currentAttempt.cycle})`
          : `Cycle ${'cycle' in currentAttempt ? currentAttempt.cycle : 0}`;
    } else if (attempts.length > 0) {
      currentAttempt = attempts[attempts.length - 1];
      attemptLabel = 'Latest Attempt';
    }
  }

  const rawOutput = currentAttempt ? ('output' in currentAttempt ? currentAttempt.output : '') : '';
  const errorMsg = currentAttempt ? ('error' in currentAttempt ? currentAttempt.error : '') : '';

  const handleCopy = async () => {
    if (!rawOutput) return;
    const ok = await copyToClipboard(rawOutput);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="stage-detail-panel">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-title">STAGE INSPECTION: {title}</span>
          <span className="panel-subtitle">{attemptLabel}</span>
        </div>
        <button className="panel-close-btn" onClick={onClose}>
          ✕ Close
        </button>
      </div>

      <div className="panel-meta-grid">
        <div className="meta-card">
          <span className="meta-k">Status:</span>
          <span className={`meta-v status-text ${currentAttempt?.status}`}>
            {currentAttempt?.status?.toUpperCase() || '--'}
          </span>
        </div>
        <div className="meta-card">
          <span className="meta-k">Duration:</span>
          <span className="meta-v">
            {currentAttempt?.duration_sec !== undefined && currentAttempt?.duration_sec !== null
              ? `${currentAttempt.duration_sec.toFixed(2)}s`
              : '--'}
          </span>
        </div>
        <div className="meta-card">
          <span className="meta-k">Provider:</span>
          <span className="meta-v">
            {('provider' in (currentAttempt || {}) && currentAttempt?.provider) || '--'}
          </span>
        </div>
        <div className="meta-card">
          <span className="meta-k">Model:</span>
          <span className="meta-v">
            {('model' in (currentAttempt || {}) && currentAttempt?.model) || '--'}
          </span>
        </div>
      </div>

      {errorMsg && (
        <div className="error-banner">
          <span className="error-title">⚠ STAGE ERROR:</span>
          <pre>{errorMsg}</pre>
        </div>
      )}

      <div className="panel-output-section">
        <div className="output-header">
          <span>RAW AGENT OUTPUT / LOGS</span>
          <div className="output-header-actions">
            <span className="output-len">
              {rawOutput ? `${rawOutput.length} characters` : 'No output'}
            </span>
            {rawOutput && (
              <button
                className={`copy-btn ${copied ? 'copied' : ''}`}
                onClick={handleCopy}
                title="Copy raw output to clipboard"
              >
                {copied ? '✓ Copied' : '📋 Copy'}
              </button>
            )}
          </div>
        </div>
        <div className="output-body">
          {rawOutput ? (
            <pre className="output-pre">{rawOutput}</pre>
          ) : (
            <div className="output-placeholder">No raw output recorded for this stage/attempt.</div>
          )}
        </div>
      </div>
    </div>
  );
};
