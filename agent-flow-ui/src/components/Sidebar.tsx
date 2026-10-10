import React, { useState, useMemo } from 'react';
import type { RunSummary } from '../types';

interface SidebarProps {
  runs: RunSummary[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  onStop?: () => Promise<void>;
  onRetry?: () => Promise<void>;
  onResume?: () => Promise<void>;
  onClone?: (task: string, label?: string) => void;
  onApprove?: () => Promise<void>;
  onReject?: (reason?: string) => Promise<void>;
  onDeleteRun?: (runId: string) => Promise<void>;
  onPurgeRuns?: () => Promise<void>;
  isPipelineRunning?: boolean;
  isCancellationRequested?: boolean;
  isRetryEligible?: boolean;
  isHumanDecisionEligible?: boolean;
}

const PAGE_SIZE = 8;

export const Sidebar: React.FC<SidebarProps> = ({
  runs,
  selectedRunId,
  onSelectRun,
  onStop,
  onRetry,
  onResume,
  onClone,
  onApprove,
  onReject,
  onDeleteRun,
  onPurgeRuns,
  isPipelineRunning,
  isCancellationRequested,
  isRetryEligible,
  isHumanDecisionEligible,
}) => {
  const [showRejectModal, setShowRejectModal] = React.useState(false);
  const [rejectReason, setRejectReason] = React.useState('');
  const [isSubmittingDecision, setIsSubmittingDecision] = React.useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [currentPage, setCurrentPage] = useState<number>(1);

  const filteredRuns = useMemo(() => {
    if (statusFilter === 'ALL') return runs;
    if (statusFilter === 'APPROVED') return runs.filter((r) => r.final_status.toLowerCase() === 'approved');
    if (statusFilter === 'FAILED') return runs.filter((r) => ['failed', 'interrupted', 'stale', 'blocked'].includes(r.final_status.toLowerCase()));
    if (statusFilter === 'RUNNING') return runs.filter((r) => ['running', 'awaiting_human_approval', 'awaiting approval'].includes(r.final_status.toLowerCase()));
    return runs;
  }, [runs, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRuns.length / PAGE_SIZE));
  const paginatedRuns = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredRuns.slice(start, start + PAGE_SIZE);
  }, [filteredRuns, currentPage]);

  const formatTime = (ts: number | null) => {
    if (!ts) return '--';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
        return 'running';
      case 'awaiting_human_approval':
      case 'awaiting approval':
      case 'approve':
        return 'awaiting';
      case 'approved':
        return 'approved';
      case 'rejected':
        return 'rejected';
      case 'blocked':
      case 'dependency_action_required':
      case 'dependency_required':
        return 'blocked';
      case 'failed':
        return 'failed';
      case 'interrupted':
      case 'stale':
        return 'interrupted';
      case 'cancelled':
      case 'canceled':
        return 'cancelled';
      default:
        return 'other';
    }
  };

  return (
    <aside className="runs-sidebar">
      {/* Controls Area at the Top */}
      <div className="controls-placeholder-area">
        <div className="controls-title">
          <span>PIPELINE CONTROLS</span>
          <span className="coming-tag">Control Room</span>
        </div>
        <div className="control-btn-grid">
          <button className="ctrl-btn run-btn" disabled title="Use Main Task Input to Run">
            ▶ Run
          </button>
          <button
            className={`ctrl-btn stop-btn ${isPipelineRunning ? 'active-stop' : ''}`}
            disabled={!isPipelineRunning || isCancellationRequested}
            onClick={onStop}
            title={
              isPipelineRunning
                ? isCancellationRequested
                  ? 'Stop requested...'
                  : 'Stop active pipeline'
                : 'Stop disabled (no active run)'
            }
          >
            {isCancellationRequested ? '⏹ Stopping...' : '⏹ Stop'}
          </button>
          <button
            className={`ctrl-btn retry-btn ${isRetryEligible && !isPipelineRunning ? 'active-retry' : ''}`}
            disabled={!isRetryEligible || isPipelineRunning}
            onClick={onRetry}
            title={
              isPipelineRunning
                ? 'Retry disabled (pipeline active)'
                : isRetryEligible
                ? 'Retry this task as a new pipeline run'
                : 'Retry not eligible for this run'
            }
          >
            ⟳ Retry
          </button>
          <button
            className={`ctrl-btn resume-btn ${isRetryEligible && !isPipelineRunning ? 'active-resume' : ''}`}
            disabled={!isRetryEligible || isPipelineRunning}
            onClick={onResume}
            title={
              isPipelineRunning
                ? 'Resume disabled (pipeline active)'
                : isRetryEligible
                ? 'Resume from Tester/Reviewer stage'
                : 'Resume not eligible for this run'
            }
          >
            ▶ Resume
          </button>
          <button
            className={`ctrl-btn approve-btn ${isHumanDecisionEligible ? 'active-approve' : ''}`}
            disabled={!isHumanDecisionEligible || isSubmittingDecision}
            onClick={async () => {
              if (!onApprove || !isHumanDecisionEligible) return;
              setIsSubmittingDecision(true);
              try {
                await onApprove();
              } finally {
                setIsSubmittingDecision(false);
              }
            }}
            title={
              isHumanDecisionEligible
                ? 'Approve this implementation'
                : 'Approve disabled (not awaiting human approval)'
            }
          >
            ✔ Approve
          </button>
          <button
            className={`ctrl-btn reject-btn ${isHumanDecisionEligible ? 'active-reject' : ''}`}
            disabled={!isHumanDecisionEligible || isSubmittingDecision}
            onClick={() => {
              if (!isHumanDecisionEligible) return;
              setShowRejectModal(true);
            }}
            title={
              isHumanDecisionEligible
                ? 'Reject this implementation'
                : 'Reject disabled (not awaiting human approval)'
            }
          >
            ✖ Reject
          </button>
        </div>
      </div>

      <div className="sidebar-header">
        <span className="sidebar-title">RUN HISTORY</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className="runs-count-badge">{runs.length}</span>
          <button
            type="button"
            className="btn-purge-runs"
            title="Purge all completed/stale runs from disk"
            disabled={isPipelineRunning}
            onClick={async () => {
              if (window.confirm('Purge all inactive pipeline runs from disk?')) {
                if (onPurgeRuns) {
                  await onPurgeRuns();
                } else {
                  const { purgeRuns } = await import('../api');
                  await purgeRuns();
                  window.location.reload();
                }
              }
            }}
          >
            🗑
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="sidebar-filter-tabs">
        {[
          { key: 'ALL', label: 'ALL' },
          { key: 'RUNNING', label: 'ACTIVE' },
          { key: 'APPROVED', label: 'PASSED' },
          { key: 'FAILED', label: 'FAILED' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`filter-tab-btn ${statusFilter === tab.key ? 'active' : ''}`}
            onClick={() => {
              setStatusFilter(tab.key);
              setCurrentPage(1);
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="runs-list">
        {paginatedRuns.length === 0 ? (
          <div className="no-runs">No pipeline runs found.</div>
        ) : (
          paginatedRuns.map((r) => {
            const isSelected = r.run_id === selectedRunId;
            return (
              <div
                key={r.run_id}
                className={`run-card ${isSelected ? 'selected' : ''}`}
                onClick={() => onSelectRun(r.run_id)}
              >
                <div className="run-card-top">
                  <div className="run-card-title-group">
                    {r.label && <span className="run-label-badge">{r.label}</span>}
                    <span className="run-id-text">{r.run_id}</span>
                  </div>
                  <span className={`run-status-pill ${getStatusBadgeClass(r.final_status)}`}>
                    {r.final_status.toUpperCase()}
                  </span>
                </div>
                <div className="run-task-text" title={r.task || ''}>
                  {r.task || 'No task specified'}
                </div>
                <div className="run-card-meta">
                  <span>⏱ {formatTime(r.started_at)}</span>
                  <span>Cycles: {r.cycles_used}</span>
                  {r.retry_of && (
                    <span className="lineage-tag" title={`Retry of ${r.retry_of}`}>
                      ⟳ RETRY
                    </span>
                  )}
                  {r.total_duration_sec && (
                    <span>{r.total_duration_sec.toFixed(1)}s</span>
                  )}
                  {onClone && r.task && (
                    <button
                      type="button"
                      className="btn-clone-run"
                      title="Clone prompt and settings into task bar"
                      onClick={(e) => {
                        e.stopPropagation();
                        onClone(r.task || '', r.label || undefined);
                      }}
                    >
                      📋 Clone
                    </button>
                  )}
                  {onDeleteRun && !isPipelineRunning && (
                    <button
                      type="button"
                      className="btn-delete-single-run"
                      title="Delete this run from disk"
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (window.confirm(`Delete run ${r.run_id}?`)) {
                          await onDeleteRun(r.run_id);
                        }
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Pagination Bar */}
      {totalPages > 1 && (
        <div className="sidebar-pagination">
          <button
            type="button"
            className="pagination-btn"
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
          >
            ◀ Prev
          </button>
          <span className="pagination-text">
            {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            className="pagination-btn"
            disabled={currentPage >= totalPages}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
          >
            Next ▶
          </button>
        </div>
      )}

      {showRejectModal && (
        <div className="modal-overlay" onClick={() => setShowRejectModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">REJECT IMPLEMENTATION</span>
              <button className="modal-close-btn" onClick={() => setShowRejectModal(false)}>✕</button>
            </div>
            <div className="modal-body">
              <p className="modal-desc">
                Provide an optional rejection reason for historical context. Rejecting will mark the run as REJECTED without modifying repository files.
              </p>
              <textarea
                className="modal-textarea"
                placeholder="Reason (e.g., 'The layout works but this is not the UI direction I want.')..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={4}
              />
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-modal-cancel"
                onClick={() => setShowRejectModal(false)}
                disabled={isSubmittingDecision}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-modal-reject"
                disabled={isSubmittingDecision}
                onClick={async () => {
                  if (!onReject) return;
                  setIsSubmittingDecision(true);
                  try {
                    await onReject(rejectReason.trim() || undefined);
                    setShowRejectModal(false);
                    setRejectReason('');
                  } finally {
                    setIsSubmittingDecision(false);
                  }
                }}
              >
                {isSubmittingDecision ? 'Rejecting...' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
