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
  const title = selectedStage.toUpperCase();
  let attemptLabel = 'Execution Output';

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
    <section className="inspection-panel" aria-label={`Stage inspection for ${selectedStage}`}>
      <div className="inspector-toolbar">
        <div className="inspector-agent">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" x2="20" y1="19" y2="19" />
          </svg>
          <strong>STAGE INSPECTION: {title}</strong>
          <span className="muted">/</span>
          <span className="muted">{attemptLabel}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {rawOutput && (
            <button
              type="button"
              className="quiet-button"
              onClick={handleCopy}
              title="Copy output to clipboard"
            >
              {copied ? '✓ Copied' : '📋 Copy log'}
            </button>
          )}
          <button type="button" className="quiet-button" onClick={onClose} title="Close inspection">
            ✕ Close
          </button>
        </div>
      </div>

      <div className="agent-metrics">
        <span>Model: {('model' in (currentAttempt || {}) && currentAttempt?.model) || '--'}</span>
        <span className="mono">
          Duration:{' '}
          {currentAttempt?.duration_sec !== undefined && currentAttempt?.duration_sec !== null
            ? `${currentAttempt.duration_sec.toFixed(2)}s`
            : '--'}
        </span>
        <span>Provider: {('provider' in (currentAttempt || {}) && currentAttempt?.provider) || '--'}</span>
        <span className={`status-badge ${(currentAttempt?.status || 'waiting').toLowerCase()}`}>
          {currentAttempt?.status?.toUpperCase() || 'QUEUED'}
        </span>
      </div>

      {errorMsg && (
        <div className="inline-error" style={{ padding: '8px 12px', background: '#331c22', borderRadius: '4px' }}>
          <strong>⚠ ERROR:</strong>
          <pre style={{ marginTop: '4px' }}>{errorMsg}</pre>
        </div>
      )}

      <div className="terminal-view">
        {rawOutput ? (
          <pre>{rawOutput}</pre>
        ) : (
          <div className="section-empty">No raw output recorded for this stage/attempt.</div>
        )}
      </div>
    </section>
  );
};
