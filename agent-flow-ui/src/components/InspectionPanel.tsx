import React, { useState } from 'react';
import { copyToClipboard } from '../utils/clipboard';
import type { RunState } from '../types';

interface InspectionPanelProps {
  run: RunState | null;
  selectedStage: string | null;
  selectedAttemptIndex: number | null;
  onSelectStage: (stageName: string, attemptIndex?: number) => void;
  activeTab?: 'activity' | 'tests' | 'changes' | 'review';
  onActiveTabChange?: (tab: 'activity' | 'tests' | 'changes' | 'review') => void;
}

export const InspectionPanel: React.FC<InspectionPanelProps> = ({
  run,
  selectedStage,
  selectedAttemptIndex,
  onSelectStage,
  activeTab: controlledActiveTab,
  onActiveTabChange,
}) => {
  // Supports an optional controlled mode (App.tsx lifts this to wire up the
  // ReviewRail "View diff" button, which used to be a no-op with nowhere to
  // switch to). Falls back to fully-internal state when uncontrolled.
  const [internalActiveTab, setInternalActiveTab] = useState<'activity' | 'tests' | 'changes' | 'review'>('activity');
  const activeTab = controlledActiveTab ?? internalActiveTab;
  const setActiveTab = onActiveTabChange ?? setInternalActiveTab;
  const [followLog, setFollowLog] = useState(true);
  const [logFilter, setLogFilter] = useState('');
  const [copiedLog, setCopiedLog] = useState(false);
  const [selectedFilePath, setSelectedFilePath] = useState<string>('');

  if (!run) {
    return (
      <section className="inspection-panel">
        <div className="panel-empty">
          <strong>No active run selected</strong>
          <span>Select a run from the history sidebar to inspect.</span>
        </div>
      </section>
    );
  }

  const { stages, files_changed, tests, review, git } = run;
  const currentStageName = selectedStage || 'planner';
  const stageKey = currentStageName as keyof typeof stages;
  const stageData = stages[stageKey];

  let attempts: any[] = [];
  let currentAttempt: any = null;

  if (currentStageName === 'planner' || currentStageName === 'preflight') {
    currentAttempt = stageData;
    attempts = stageData ? [stageData] : [];
  } else if (stageData && 'attempts' in stageData) {
    attempts = stageData.attempts || [];
    if (selectedAttemptIndex !== null && attempts[selectedAttemptIndex]) {
      currentAttempt = attempts[selectedAttemptIndex];
    } else if (attempts.length > 0) {
      currentAttempt = attempts[attempts.length - 1];
    }
  }

  const rawOutput = currentAttempt?.output || '';
  const isRunning = currentAttempt?.status === 'running';

  const filesList = [
    ...(files_changed?.created || []).map((f) => ({ path: f, op: 'created' })),
    ...(files_changed?.modified || []).map((f) => ({ path: f, op: 'modified' })),
    ...(files_changed?.deleted || []).map((f) => ({ path: f, op: 'deleted' })),
  ];

  const currentFile = filesList.find((f) => f.path === selectedFilePath) || filesList[0];

  const handleCopyLog = async () => {
    if (!rawOutput) return;
    const ok = await copyToClipboard(rawOutput);
    if (ok) {
      setCopiedLog(true);
      setTimeout(() => setCopiedLog(false), 1800);
    }
  };

  return (
    <section className="inspection-panel" aria-label="Execution inspector">
      <div className="inspection-tabs" role="tablist" aria-label="Inspect run evidence">
        <button
          type="button"
          role="tab"
          id="tab-activity"
          aria-selected={activeTab === 'activity'}
          className={activeTab === 'activity' ? 'is-active' : ''}
          onClick={() => setActiveTab('activity')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" x2="20" y1="19" y2="19" />
          </svg>
          <span>Agent log</span>
        </button>

        <button
          type="button"
          role="tab"
          id="tab-tests"
          aria-selected={activeTab === 'tests'}
          className={activeTab === 'tests' ? 'is-active' : ''}
          onClick={() => setActiveTab('tests')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2" />
            <path d="M6.453 15h11.094" />
            <path d="M8.5 2h7" />
          </svg>
          <span>Tests & shell</span>
          {tests?.length > 0 && <span className="count">{tests.length}</span>}
        </button>

        <button
          type="button"
          role="tab"
          id="tab-changes"
          aria-selected={activeTab === 'changes'}
          className={activeTab === 'changes' ? 'is-active' : ''}
          onClick={() => setActiveTab('changes')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
            <path d="M9 10h6" />
            <path d="M12 13V7" />
            <path d="M9 17h6" />
          </svg>
          <span>Changes</span>
          {filesList.length > 0 && <span className="count">{filesList.length}</span>}
        </button>

        <button
          type="button"
          role="tab"
          id="tab-review"
          aria-selected={activeTab === 'review'}
          className={activeTab === 'review' ? 'is-active' : ''}
          onClick={() => setActiveTab('review')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
          <span>Review</span>
        </button>
      </div>

      <div className="inspection-content">
        {/* Tab 1: Agent Log */}
        {activeTab === 'activity' && (
          <div className="activity-panel">
            <div className="inspector-toolbar">
              <div className="inspector-agent">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="4 17 10 11 4 5" />
                  <line x1="12" x2="20" y1="19" y2="19" />
                </svg>
                <strong>{currentStageName.toUpperCase()}</strong>
                <span className="muted">/</span>
                <span className="muted">Agent output</span>
                {attempts.length > 1 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: '6px' }}>
                    <span className="muted" style={{ fontSize: '10px' }}>Attempt:</span>
                    {attempts.map((att, idx) => {
                      const isCurrent = (selectedAttemptIndex === null && idx === attempts.length - 1) || selectedAttemptIndex === idx;
                      return (
                        <button
                          key={idx}
                          type="button"
                          className="quiet-button"
                          style={{
                            padding: '1px 5px',
                            minHeight: '20px',
                            fontSize: '10px',
                            borderRadius: '3px',
                            background: isCurrent ? 'var(--surface-hover)' : 'transparent',
                            color: isCurrent ? 'var(--accent)' : 'var(--text-muted)',
                            border: isCurrent ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
                          }}
                          onClick={() => onSelectStage(currentStageName, idx)}
                          title={`Cycle ${att.cycle ?? idx} (${att.type || 'attempt'})`}
                        >
                          #{idx + 1}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="toolbar-actions">
                <button
                  type="button"
                  className={`quiet-button ${followLog ? 'is-active' : ''}`}
                  onClick={() => setFollowLog(!followLog)}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 17V3" />
                    <path d="m6 11 6 6 6-6" />
                    <path d="M19 21H5" />
                  </svg>
                  Follow
                </button>
                <button
                  type="button"
                  className="quiet-button copy-button"
                  onClick={handleCopyLog}
                >
                  {copiedLog ? '✓ Copied' : '📋 Copy log'}
                </button>
              </div>
            </div>

            <div className="agent-metrics">
              <span>{currentAttempt?.model || 'google/gemini-2.5-flash'}</span>
              <span className="mono">
                {currentAttempt?.duration_sec !== undefined && currentAttempt?.duration_sec !== null
                  ? `${currentAttempt.duration_sec.toFixed(1)}s`
                  : '--'}
              </span>
              <span>{currentAttempt?.provider || 'openrouter'}</span>
              <label className="log-search">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <input
                  value={logFilter}
                  onChange={(e) => setLogFilter(e.target.value)}
                  placeholder="Filter output"
                />
              </label>
            </div>

            <div className="terminal-view" tabIndex={0} role="log">
              {rawOutput ? (
                rawOutput
                  .split('\n')
                  .filter((line: string) => !logFilter || line.toLowerCase().includes(logFilter.toLowerCase()))
                  .map((line: string, idx: number) => (
                    <div key={idx} className="terminal-line log-info">
                      <time className="terminal-time">00:00:{idx < 10 ? `0${idx}` : idx}</time>
                      <span className="terminal-level">❯</span>
                      <pre>{line}</pre>
                    </div>
                  ))
              ) : (
                <div className="panel-empty">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="4 17 10 11 4 5" />
                    <line x1="12" x2="20" y1="19" y2="19" />
                  </svg>
                  <strong>Waiting for agent output</strong>
                  <span>The {currentStageName} stream will appear here.</span>
                </div>
              )}
              {isRunning && (
                <div className="terminal-line">
                  <span className="terminal-time">streaming</span>
                  <span className="terminal-level" />
                  <span className="terminal-cursor" />
                </div>
              )}
            </div>

            <div className="terminal-footer">
              <span>{rawOutput ? rawOutput.split('\n').length : 0} events</span>
              <span className={isRunning ? 'live-indicator' : ''}>
                {isRunning ? <><i /> Receiving events</> : 'Stage snapshot'}
              </span>
            </div>
          </div>
        )}

        {/* Tab 2: Tests & Shell */}
        {activeTab === 'tests' && (
          <div className="tests-panel">
            <div className="inspector-toolbar">
              <strong>Verification suite</strong>
              <span className="muted">
                {tests?.reduce((acc, t) => acc + t.commands.filter((c) => c.returncode === 0).length, 0)}/
                {tests?.reduce((acc, t) => acc + t.commands.length, 0)} checks passed · Cycle {run.current_cycle}
              </span>
            </div>

            {(!tests || tests.length === 0) ? (
              <div className="panel-empty">
                <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2" />
                  <path d="M6.453 15h11.094" />
                  <path d="M8.5 2h7" />
                </svg>
                <strong>No checks in this cycle yet</strong>
                <span>Commands and exit codes appear after the tester runs.</span>
              </div>
            ) : (
              tests.flatMap((t) => t.commands).map((cmd, idx) => (
                <details key={idx} className={`command-card command-${cmd.returncode === 0 ? 'passed' : 'failed'}`} open={cmd.returncode !== 0}>
                  <summary>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="details-chevron">
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                    <span className={`command-status ${cmd.returncode === 0 ? 'tone-success' : 'tone-error'}`}>
                      {cmd.returncode === 0 ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10" />
                          <line x1="12" x2="12" y1="8" y2="12" />
                          <line x1="12" x2="12.01" y1="16" y2="16" />
                        </svg>
                      )}
                    </span>
                    <code>{cmd.command}</code>
                    <span className={`exit-code ${cmd.returncode === 0 ? 'tone-success' : 'tone-error'}`}>
                      {cmd.timed_out ? 'TIMEOUT' : `${cmd.returncode}: ${cmd.returncode === 0 ? 'PASS' : 'FAIL'}`}
                    </span>
                  </summary>
                  <div className="command-output">
                    {cmd.stdout && (
                      <div>
                        <span>stdout</span>
                        <pre>{cmd.stdout}</pre>
                      </div>
                    )}
                    {cmd.stderr && (
                      <div className="tone-error">
                        <span>stderr</span>
                        <pre className="stderr-output">{cmd.stderr}</pre>
                      </div>
                    )}
                  </div>
                </details>
              ))
            )}
          </div>
        )}

        {/* Tab 3: Changes */}
        {activeTab === 'changes' && (
          <div className="changes-panel">
            <div className="inspector-toolbar">
              <span className="inspector-agent">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="6" x2="6" y1="3" y2="15" />
                  <circle cx="18" cy="6" r="3" />
                  <circle cx="6" cy="18" r="3" />
                  <path d="M18 9a9 9 0 0 1-9 9" />
                </svg>
                <span className="mono branch-name">agent/task-run</span>
              </span>
              <span className="diff-stat mono">
                <span className="tone-success">+{files_changed?.created?.length || 0}</span>
                <span className="tone-error">-{files_changed?.deleted?.length || 0}</span>
                <span className="muted">{filesList.length} files</span>
              </span>
            </div>

            {filesList.length > 0 ? (
              <div className="diff-layout">
                <nav className="file-tree" aria-label="Changed files">
                  <div className="file-tree-heading">Files changed</div>
                  {filesList.map((f) => (
                    <button
                      key={f.path}
                      type="button"
                      className={(currentFile?.path === f.path) ? 'is-active' : ''}
                      onClick={() => setSelectedFilePath(f.path)}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4" />
                        <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                      </svg>
                      <span>
                        <strong>{f.path.split('/').pop()}</strong>
                        <small>{f.path.split('/').slice(0, -1).join('/')}</small>
                      </span>
                      <span className={`file-operation operation-${f.op}`}>
                        {f.op === 'created' ? 'A' : f.op === 'deleted' ? 'D' : 'M'}
                      </span>
                    </button>
                  ))}
                </nav>

                <section className="diff-view" aria-label={`Diff for ${currentFile?.path}`}>
                  <div className="diff-title">
                    <span>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="m9 18 6-6-6-6" />
                      </svg>
                      <code>{currentFile?.path}</code>
                    </span>
                    <button
                      type="button"
                      className="quiet-button copy-button"
                      onClick={() => navigator.clipboard?.writeText(currentFile?.path || '')}
                    >
                      📋 Copy
                    </button>
                  </div>
                  <div className="diff-code" tabIndex={0}>
                    {git?.diff_stat ? (
                      <pre style={{ padding: '12px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                        {git.diff_stat}
                      </pre>
                    ) : (
                      <div className="diff-excerpt">Sample diff view · verified modified file</div>
                    )}
                  </div>
                </section>
              </div>
            ) : (
              <div className="panel-empty">
                <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 7h-3a2 2 0 0 1-2-2V2" />
                  <path d="M9 18a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h7l4 4v10a2 2 0 0 1-2 2Z" />
                </svg>
                <strong>No file operations yet</strong>
                <span>Created, modified, and deleted files will appear here.</span>
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Review */}
        {activeTab === 'review' && (
          <div className="review-panel">
            <div className="review-result">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
              <div>
                <span className="eyebrow">AUTOMATED VERDICT</span>
                <h3>
                  {review?.verdict === 'APPROVE'
                    ? 'Acceptance criteria satisfied'
                    : review?.verdict === 'CHANGES REQUIRED'
                    ? 'Changes required'
                    : 'Review pending'}
                </h3>
                <p>
                  {review?.verdict === 'APPROVE'
                    ? 'All requirements satisfied. Verified and ready for operator gate.'
                    : 'Awaiting completion of tester and automated reviewer evaluation.'}
                </p>
              </div>
            </div>

            <div className="review-findings">
              <h4>
                Structured repair requirements <span className="count">{review?.frontend_fix_required || review?.backend_fix_required || review?.dependency_fix_required ? 1 : 0}</span>
              </h4>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    border: '1px solid var(--border)',
                    background: review?.frontend_fix_required ? 'rgba(237, 149, 151, 0.1)' : 'var(--surface-raised)',
                    color: review?.frontend_fix_required ? 'var(--error)' : 'var(--text-muted)',
                  }}
                >
                  Frontend fix: <strong>{review?.frontend_fix_required ? 'REQUIRED' : 'NO'}</strong>
                </span>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    border: '1px solid var(--border)',
                    background: review?.backend_fix_required ? 'rgba(237, 149, 151, 0.1)' : 'var(--surface-raised)',
                    color: review?.backend_fix_required ? 'var(--error)' : 'var(--text-muted)',
                  }}
                >
                  Backend fix: <strong>{review?.backend_fix_required ? 'REQUIRED' : 'NO'}</strong>
                </span>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    border: '1px solid var(--border)',
                    background: review?.dependency_fix_required ? 'rgba(223, 186, 126, 0.1)' : 'var(--surface-raised)',
                    color: review?.dependency_fix_required ? 'var(--warning)' : 'var(--text-muted)',
                  }}
                >
                  Dependency fix: <strong>{review?.dependency_fix_required ? 'REQUIRED' : 'NO'}</strong>
                </span>
              </div>

              {(!review?.frontend_fix_required && !review?.backend_fix_required && !review?.dependency_fix_required) ? (
                <p className="muted">No repair flags triggered by reviewer.</p>
              ) : (
                <div className="review-finding">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="tone-warning">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" x2="12" y1="8" y2="12" />
                    <line x1="12" x2="12.01" y1="16" y2="16" />
                  </svg>
                  <div>
                    <span className="finding-target">
                      Repair loop required <span className="tone-warning">Open</span>
                    </span>
                    <p>
                      {review?.frontend_fix_required && 'Frontend code modifications requested by reviewer. '}
                      {review?.backend_fix_required && 'Backend service or endpoint updates required. '}
                      {review?.dependency_fix_required && 'Dependency resolution or package install needed.'}
                    </p>
                  </div>
                </div>
              )}
            </div>

            <p className="review-footnote">
              The automated verdict and the operator’s decision are recorded separately. Approval actions are available in the review rail.
            </p>
          </div>
        )}
      </div>
    </section>
  );
};
