import React, { useState, useMemo } from 'react';
import type { RunSummary } from '../types';
import type { WorkspaceProject } from '../api';

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
  workspace?: WorkspaceProject | null;
}

export const Sidebar: React.FC<SidebarProps> = ({
  runs,
  selectedRunId,
  onSelectRun,
  onRetry,
  onDeleteRun,
  onPurgeRuns,
  isPipelineRunning,
  workspace,
}) => {
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [collapsedDays, setCollapsedDays] = useState<Record<string, boolean>>({});
  const [isRunsCollapsed, setIsRunsCollapsed] = useState<boolean>(false);

  const toggleDayCollapse = (day: string) => {
    setCollapsedDays((prev) => ({
      ...prev,
      [day]: !prev[day],
    }));
  };

  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      const matchSearch =
        !searchQuery ||
        `${r.run_id} ${r.label || ''} ${r.task || ''}`.toLowerCase().includes(searchQuery.toLowerCase());
      if (!matchSearch) return false;

      const s = r.final_status.toLowerCase();
      if (statusFilter === 'all') return true;
      if (statusFilter === 'active') return ['running', 'awaiting_human_approval', 'awaiting approval', 'approve'].includes(s);
      if (statusFilter === 'failed') return ['failed', 'interrupted', 'stale', 'blocked'].includes(s);
      return true;
    });
  }, [runs, statusFilter, searchQuery]);

  const formatDay = (ts: number | null) => {
    if (!ts) return 'Today';
    const d = new Date(ts * 1000);
    const isToday = d.toDateString() === new Date().toDateString();
    return isToday ? 'Today' : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const days = useMemo(() => {
    return Array.from(new Set(filteredRuns.map((r) => formatDay(r.started_at))));
  }, [filteredRuns]);

  const formatTime = (ts: number | null) => {
    if (!ts) return '--';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  };

  const formatDuration = (sec?: number | null) => {
    if (sec === undefined || sec === null) return '--';
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const m = Math.floor(sec / 60);
    const rem = Math.floor(sec % 60).toString().padStart(2, '0');
    return `${m}m ${rem}s`;
  };

  const getStatusBadgeTone = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
        return 'accent';
      case 'awaiting_human_approval':
      case 'awaiting approval':
      case 'approve':
        return 'warning';
      case 'approved':
        return 'success';
      case 'rejected':
        return 'warning';
      case 'blocked':
      case 'dependency_action_required':
      case 'dependency_required':
      case 'failed':
        return 'error';
      case 'cancelled':
      case 'canceled':
      case 'interrupted':
      case 'stale':
      default:
        return 'neutral';
    }
  };

  const getStatusDisplayText = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
        return 'Running';
      case 'awaiting_human_approval':
      case 'awaiting approval':
      case 'approve':
        return 'Awaiting approval';
      case 'approved':
        return 'Approved';
      case 'rejected':
        return 'Changes requested';
      case 'failed':
        return 'Failed';
      case 'cancelled':
      case 'canceled':
        return 'Cancelled';
      default:
        return status;
    }
  };

  const activeCount = runs.filter((r) =>
    ['running', 'awaiting_human_approval', 'awaiting approval', 'approve'].includes(r.final_status.toLowerCase())
  ).length;

  return (
    <aside className="sidebar" aria-label="Run history">
      <div className="sidebar-heading">
        <span
          onClick={() => setIsRunsCollapsed(!isRunsCollapsed)}
          style={{ cursor: 'pointer', userSelect: 'none' }}
          title={isRunsCollapsed ? 'Expand runs' : 'Collapse runs'}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            style={{
              transform: isRunsCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s ease',
            }}
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
            <path d="M12 7v5l4 2" />
          </svg>
          Runs
          <span className="count">{runs.length}</span>
        </span>
        <button
          type="button"
          className="icon-button"
          title="Purge completed run history"
          aria-label="Purge completed run history"
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
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18" />
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
            <line x1="10" x2="10" y1="11" y2="17" />
            <line x1="14" x2="14" y1="11" y2="17" />
          </svg>
        </button>
      </div>

      {!isRunsCollapsed && (
        <>
          <label className="search-field">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <span className="sr-only">Search runs</span>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search runs…"
            />
          </label>

          <div className="run-filters" aria-label="Filter runs">
            {['all', 'active', 'failed'].map((tab) => (
              <button
                key={tab}
                type="button"
                aria-pressed={statusFilter === tab}
                className={statusFilter === tab ? 'is-active' : ''}
                onClick={() => setStatusFilter(tab)}
              >
                {tab === 'all' ? 'All runs' : tab === 'active' ? 'Active' : 'Failed'}
                {tab === 'active' && activeCount > 0 && <span>{activeCount}</span>}
              </button>
            ))}
          </div>

          <nav className="run-list" aria-label="Select a run">
            {filteredRuns.length === 0 ? (
              <div className="sidebar-empty">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <p>No matching runs</p>
                <button
                  type="button"
                  className="quiet-button"
                  onClick={() => {
                    setSearchQuery('');
                    setStatusFilter('all');
                  }}
                >
                  Clear filters
                </button>
              </div>
            ) : (
              days.map((day) => {
                const isCollapsed = Boolean(collapsedDays[day]);
                const dayRuns = filteredRuns.filter((r) => formatDay(r.started_at) === day);

                return (
                  <section key={day} aria-label={day}>
                    <div
                      className="run-day"
                      onClick={() => toggleDayCollapse(day)}
                      style={{
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        userSelect: 'none',
                      }}
                      title={isCollapsed ? `Show ${day} runs` : `Hide ${day} runs`}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <svg
                          width="10"
                          height="10"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.5"
                          style={{
                            transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
                            transition: 'transform 0.15s ease',
                          }}
                        >
                          <path d="m6 9 6 6 6-6" />
                        </svg>
                        {day}
                      </span>
                      <span className="count" style={{ fontSize: '9px', minWidth: '15px', height: '15px' }}>
                        {dayRuns.length}
                      </span>
                    </div>

                    {!isCollapsed && (
                      <ul>
                        {dayRuns.map((r) => {
                          const isSelected = r.run_id === selectedRunId;
                          const tone = getStatusBadgeTone(r.final_status);
                          const isRunning = r.final_status.toLowerCase() === 'running';

                          return (
                            <li key={r.run_id} className={`run-item ${isSelected ? 'is-selected' : ''}`}>
                              <button
                                type="button"
                                className="run-select"
                                aria-current={isSelected ? 'true' : undefined}
                                onClick={() => onSelectRun(r.run_id)}
                              >
                                <span className="run-title">
                                  {isRunning ? (
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tone-accent spin" aria-hidden="true">
                                      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                                    </svg>
                                  ) : tone === 'success' ? (
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tone-success" aria-hidden="true">
                                      <path d="M20 6 9 17l-5-5" />
                                    </svg>
                                  ) : tone === 'warning' ? (
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tone-warning" aria-hidden="true">
                                      <circle cx="12" cy="12" r="10" />
                                      <polyline points="12 6 12 12 16.5 12" />
                                    </svg>
                                  ) : tone === 'error' ? (
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tone-error" aria-hidden="true">
                                      <circle cx="12" cy="12" r="10" />
                                      <line x1="12" x2="12" y1="8" y2="12" />
                                      <line x1="12" x2="12.01" y1="16" y2="16" />
                                    </svg>
                                  ) : (
                                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tone-neutral" aria-hidden="true">
                                      <rect width="18" height="18" x="3" y="3" rx="2" />
                                    </svg>
                                  )}
                                  <span>{r.label || r.task || r.run_id}</span>
                                </span>

                                <span className="run-meta">
                                  <span className="mono" title={r.run_id}>
                                    #{r.run_id.split('_').slice(-1)[0] || r.run_id}
                                  </span>
                                  <span>{formatTime(r.started_at)}</span>
                                  <span className="run-time mono">{formatDuration(r.total_duration_sec)}</span>
                                </span>

                                <span className="run-bottom">
                                  <span className={`tone-${tone}`}>{getStatusDisplayText(r.final_status)}</span>
                                  <span className="mono">C{r.cycles_used}/3</span>
                                </span>
                              </button>

                              <div className="run-quick-actions" onClick={(e) => e.stopPropagation()}>
                                {onRetry && (
                                  <button
                                    type="button"
                                    className="icon-button"
                                    aria-label={`Retry ${r.label || r.run_id}`}
                                    title="Retry in a new run"
                                    onClick={onRetry}
                                  >
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                                      <path d="M3 3v5h5" />
                                    </svg>
                                  </button>
                                )}
                                {onDeleteRun && !isPipelineRunning && (
                                  <button
                                    type="button"
                                    className="icon-button"
                                    aria-label={`Delete ${r.label || r.run_id}`}
                                    title="Delete run"
                                    onClick={async () => {
                                      if (window.confirm(`Delete run ${r.run_id}?`)) {
                                        await onDeleteRun(r.run_id);
                                      }
                                    }}
                                  >
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                      <path d="M3 6h18" />
                                      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                                      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                                    </svg>
                                  </button>
                                )}
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </section>
                );
              })
            )}
          </nav>
        </>
      )}

      <div className="workspace-footer">
        <div>
          <span className="workspace-avatar">{workspace?.name ? workspace.name[0] : 'B'}</span>
          <span>
            <strong>{workspace?.name || 'BUM orchestrator'}</strong>
            <span title={workspace?.path || '~/projects/bum'}>{workspace?.path || '~/projects/bum'}</span>
          </span>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="m9 18 6-6-6-6" />
          </svg>
        </div>
        <span className="branch-label">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="6" x2="6" y1="3" y2="15" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <path d="M18 9a9 9 0 0 1-9 9" />
          </svg>
          main
          <span>v1.0</span>
        </span>
      </div>
    </aside>
  );
};
