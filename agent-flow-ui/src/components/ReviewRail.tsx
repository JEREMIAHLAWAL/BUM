import React, { useState } from 'react';
import type { RunState } from '../types';

interface ReviewRailProps {
  run: RunState | null;
  disabled?: boolean;
  onApprove?: () => Promise<void>;
  onReject?: (reason?: string) => Promise<void>;
  onResume?: () => Promise<void>;
  onRetry?: () => Promise<void>;
  onShowChanges?: () => void;
  activeProjectPath?: string;
}

export const ReviewRail: React.FC<ReviewRailProps> = ({
  run,
  disabled = false,
  onApprove,
  onReject,
  onResume,
  onRetry,
  onShowChanges,
}) => {
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);

  if (!run) return null;

  const runStatus = (run.status || '').toLowerCase();
  const isAwaitingApproval = runStatus === 'awaiting_human_approval' || runStatus === 'approve';
  const isApproved = runStatus === 'approved';
  const isFailed = runStatus === 'failed' || runStatus === 'blocked';
  const isRunning = runStatus === 'running';

  const totalTests = run.tests?.reduce((acc, t) => acc + t.commands.length, 0) || 0;
  const passedTests = run.tests?.reduce((acc, t) => acc + t.commands.filter((c) => c.returncode === 0).length, 0) || 0;
  const filesCount =
    (run.files_changed?.created?.length || 0) +
    (run.files_changed?.modified?.length || 0) +
    (run.files_changed?.deleted?.length || 0);

  const formatDuration = (sec?: number | null) => {
    if (sec === undefined || sec === null) return '--';
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const m = Math.floor(sec / 60);
    const rem = Math.floor(sec % 60).toString().padStart(2, '0');
    return `${m}m ${rem}s`;
  };

  return (
    <aside className="review-rail" aria-label="Human review and run summary">
      <section className={`approval-card ${isAwaitingApproval ? 'needs-approval' : ''}`}>
        <div className="approval-heading">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          <h2>Human review</h2>
          <span className={`mini-tag ${isAwaitingApproval ? 'tone-warning' : ''}`}>
            {isAwaitingApproval ? 'Action needed' : isApproved ? 'Approved' : 'Overview'}
          </span>
        </div>

        <div className="approval-icon">
          {isRunning ? (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
          ) : isAwaitingApproval ? (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          ) : isApproved ? (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          ) : (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16.5 12" />
            </svg>
          )}
        </div>

        <h3>
          {isAwaitingApproval
            ? 'Ready for your review'
            : isApproved
            ? 'Decision recorded'
            : isRunning
            ? 'Agents are working'
            : isFailed
            ? 'Verification needs attention'
            : 'Run standby'}
        </h3>

        <p>
          {isAwaitingApproval
            ? 'The reviewer approved this implementation. Inspect the evidence and make the final call.'
            : isApproved
            ? 'This run has been approved by the operator.'
            : isRunning
            ? 'The pipeline will pause here when the implementation is ready.'
            : 'Inspect the output, then resume a repair cycle or start a new attempt.'}
        </p>

        <div className="approval-checks">
          <span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={passedTests === totalTests && totalTests > 0 ? 'tone-success' : 'muted'}>
              <path d="M20 6 9 17l-5-5" />
            </svg>
            {totalTests > 0 ? `${passedTests}/${totalTests} checks passed` : 'Verification pending'}
          </span>
          <span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="6" x2="6" y1="3" y2="15" />
              <circle cx="18" cy="6" r="3" />
              <circle cx="6" cy="18" r="3" />
              <path d="M18 9a9 9 0 0 1-9 9" />
            </svg>
            {filesCount} files changed
          </span>
          <span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            Cycle {run.current_cycle || 1} of {run.max_review_cycles || 3}
          </span>
        </div>

        {isAwaitingApproval && (
          <div className="gate-actions">
            <button
              type="button"
              className="button button-primary"
              disabled={disabled || isSubmittingDecision}
              onClick={async () => {
                if (!onApprove) return;
                setIsSubmittingDecision(true);
                try {
                  await onApprove();
                } finally {
                  setIsSubmittingDecision(false);
                }
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 6 9 17l-5-5" />
              </svg>
              Approve & merge
            </button>
            <button
              type="button"
              className="button"
              disabled={disabled || isSubmittingDecision}
              onClick={() => setShowRejectModal(true)}
            >
              Request changes
            </button>
          </div>
        )}

        {!isAwaitingApproval && !isRunning && onResume && (
          <button
            type="button"
            className="button button-primary full-width"
            disabled={disabled}
            onClick={onResume}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="6 3 20 12 6 21 6 3" />
            </svg>
            Resume pipeline
          </button>
        )}

        {!isAwaitingApproval && !isRunning && onRetry && (
          <button
            type="button"
            className="button full-width"
            style={{ marginTop: '6px' }}
            disabled={disabled}
            onClick={onRetry}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            Retry in a new run
          </button>
        )}

        <span className="gate-footnote">
          {isAwaitingApproval ? 'No merge happens until you approve.' : `Total execution ${formatDuration(run.total_duration_sec)}`}
        </span>
      </section>

      <section className="rail-section">
        <div className="section-heading">
          <h2>Run summary</h2>
          <button type="button" className="quiet-button" onClick={onShowChanges}>
            View diff <span aria-hidden="true">↗</span>
          </button>
        </div>
        <dl className="summary-list">
          <div>
            <dt>Branch</dt>
            <dd className="mono" title="main">main</dd>
          </div>
          <div>
            <dt>Changes</dt>
            <dd className="diff-stat mono">
              <span className="tone-success">+{(run.files_changed?.created?.length || 0) * 12}</span>
              <span className="tone-error">-{(run.files_changed?.deleted?.length || 0) * 5}</span>
            </dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd className="mono">{formatDuration(run.total_duration_sec)}</dd>
          </div>
        </dl>
      </section>

      <section className="rail-section timeline-section">
        <div className="section-heading">
          <h2>Execution timeline</h2>
        </div>
        <ol className="execution-timeline">
          <li>
            <span className="timeline-dot tone-success" aria-hidden="true" />
            <div>
              <strong>Task planned</strong>
              <span>Scope and acceptance criteria defined</span>
            </div>
            <time className="mono">00:03</time>
          </li>
          <li>
            <span className="timeline-dot tone-success" aria-hidden="true" />
            <div>
              <strong>Implementation complete</strong>
              <span>Frontend + backend · {filesCount} files changed</span>
            </div>
            <time className="mono">01:07</time>
          </li>
          <li>
            <span className={`timeline-dot ${isFailed ? 'tone-error' : isRunning ? 'tone-neutral' : 'tone-success'}`} aria-hidden="true" />
            <div>
              <strong>{isFailed ? 'Verification failed' : isRunning ? 'Backend running' : 'Verification passed'}</strong>
              <span>Pytest · TypeScript · Lint</span>
            </div>
            <time className="mono">01:37</time>
          </li>
          {isAwaitingApproval && (
            <li>
              <span className="timeline-dot tone-success" aria-hidden="true" />
              <div>
                <strong>Reviewer approved</strong>
                <span>No blocking issues found</span>
              </div>
              <time className="mono">01:44</time>
            </li>
          )}
        </ol>
      </section>

      {showRejectModal && (
        <div className="modal-overlay" onClick={() => setShowRejectModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Request changes</h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setShowRejectModal(false)}
                aria-label="Close dialog"
              >
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18" />
                  <path d="m6 6 12 12" />
                </svg>
              </button>
            </div>
            <form
              className="dialog-body"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!onReject || !rejectReason.trim()) return;
                setIsSubmittingDecision(true);
                try {
                  await onReject(rejectReason.trim());
                  setShowRejectModal(false);
                  setRejectReason('');
                } finally {
                  setIsSubmittingDecision(false);
                }
              }}
            >
              <p>Describe what should change. The decision is recorded, and you can resume a repair cycle from the review rail.</p>
              <label htmlFor="change-request">Change request</label>
              <textarea
                id="change-request"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="What needs to be fixed?"
                required
                rows={5}
                disabled={isSubmittingDecision}
              />
              <div className="modal-actions">
                <button
                  type="button"
                  className="button"
                  disabled={isSubmittingDecision}
                  onClick={() => setShowRejectModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="button button-primary"
                  disabled={!rejectReason.trim() || isSubmittingDecision}
                >
                  Request changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
};
