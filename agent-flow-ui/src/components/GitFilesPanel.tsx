import React, { useState } from 'react';
import type { RunState } from '../types';

interface GitFilesPanelProps {
  run: RunState | null;
}

export const GitFilesPanel: React.FC<GitFilesPanelProps> = ({ run }) => {
  const [activeTab, setActiveTab] = useState<'files' | 'git'>('files');
  const [showFullGit, setShowFullGit] = useState<boolean>(false);

  if (!run) return null;

  const { files_changed, git } = run;
  const created = files_changed?.created || [];
  const modified = files_changed?.modified || [];
  const deleted = files_changed?.deleted || [];
  const operations = files_changed?.operations || [];
  const totalFiles = created.length + modified.length + deleted.length;

  return (
    <div className="section-card git-files-panel">
      <div className="section-header" style={{ padding: '4px 8px' }}>
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            type="button"
            className={`quiet-button ${activeTab === 'files' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('files')}
          >
            📁 Files Changed ({totalFiles})
          </button>
          <button
            type="button"
            className={`quiet-button ${activeTab === 'git' ? 'is-active' : ''}`}
            onClick={() => setActiveTab('git')}
          >
            🌿 Git Diff & Untracked
          </button>
        </div>
      </div>

      <div style={{ padding: '10px 12px' }}>
        {activeTab === 'files' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Real-time file ops */}
            {operations.length > 0 && (
              <div style={{ padding: '8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--surface-raised)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                  <span>⚡ REAL-TIME FILE MODIFICATION LOG</span>
                  <span>{operations.length} operations</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {operations.map((op, idx) => (
                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px' }}>
                      <span className={`status-badge ${op.status === 'in_progress' ? 'running' : 'approved'}`}>
                        {op.status === 'in_progress' ? 'WRITING' : 'VERIFIED'}
                      </span>
                      <span className="mono" style={{ color: 'var(--text-muted)' }}>{op.stage.toUpperCase()}</span>
                      <code style={{ color: 'var(--text-secondary)' }}>{op.path}</code>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {totalFiles === 0 && operations.length === 0 ? (
              <div className="section-empty">No file modifications recorded in this run.</div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                {/* Created */}
                <div style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--surface-raised)' }}>
                  <div style={{ fontSize: '10px', fontWeight: 650, color: 'var(--success)', marginBottom: '4px' }}>
                    CREATED ({created.length})
                  </div>
                  {created.length > 0 ? (
                    <ul style={{ listStyle: 'none', padding: 0 }}>
                      {created.map((f, i) => (
                        <li key={i} style={{ marginBottom: '2px' }}>
                          <code style={{ fontSize: '10px' }}>{f}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="muted" style={{ fontSize: '10px' }}>None</span>
                  )}
                </div>

                {/* Modified */}
                <div style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--surface-raised)' }}>
                  <div style={{ fontSize: '10px', fontWeight: 650, color: 'var(--warning)', marginBottom: '4px' }}>
                    MODIFIED ({modified.length})
                  </div>
                  {modified.length > 0 ? (
                    <ul style={{ listStyle: 'none', padding: 0 }}>
                      {modified.map((f, i) => (
                        <li key={i} style={{ marginBottom: '2px' }}>
                          <code style={{ fontSize: '10px' }}>{f}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="muted" style={{ fontSize: '10px' }}>None</span>
                  )}
                </div>

                {/* Deleted */}
                <div style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--surface-raised)' }}>
                  <div style={{ fontSize: '10px', fontWeight: 650, color: 'var(--error)', marginBottom: '4px' }}>
                    DELETED ({deleted.length})
                  </div>
                  {deleted.length > 0 ? (
                    <ul style={{ listStyle: 'none', padding: 0 }}>
                      {deleted.map((f, i) => (
                        <li key={i} style={{ marginBottom: '2px' }}>
                          <code style={{ fontSize: '10px' }}>{f}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="muted" style={{ fontSize: '10px' }}>None</span>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--surface-raised)' }}>
              <span className="eyebrow">GIT DIFF STAT</span>
              <pre className="mono" style={{ fontSize: '10px', marginTop: '4px', color: 'var(--text-secondary)' }}>
                {git?.diff_stat || 'No diff stat available.'}
              </pre>
            </div>

            {/* Interactive code diff */}
            <div style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: '#0d1015' }}>
              <span className="eyebrow">INTERACTIVE CODE DIFF</span>
              {(() => {
                const diffCmd = git?.git_results?.find((g) => g.command && g.command.includes('git diff') && !g.command.includes('--stat'));
                const diffText = diffCmd?.stdout || '';
                if (!diffText || !diffText.trim()) {
                  return <div className="section-empty">No code changes in diff.</div>;
                }
                const lines = diffText.split('\n');
                return (
                  <div style={{ maxHeight: '200px', overflow: 'auto', marginTop: '6px' }}>
                    {lines.map((line, idx) => {
                      let color = 'var(--text-secondary)';
                      let bg = 'transparent';
                      if (line.startsWith('+') && !line.startsWith('+++')) {
                        color = 'var(--success)';
                        bg = 'rgba(138, 210, 173, 0.08)';
                      } else if (line.startsWith('-') && !line.startsWith('---')) {
                        color = 'var(--error)';
                        bg = 'rgba(237, 149, 151, 0.08)';
                      } else if (line.startsWith('@@')) {
                        color = 'var(--accent)';
                        bg = 'rgba(138, 217, 189, 0.06)';
                      }

                      return (
                        <div key={idx} style={{ background: bg, padding: '1px 4px', fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                          <span style={{ color: 'var(--text-muted)', marginRight: '6px', userSelect: 'none' }}>{idx + 1}</span>
                          <span style={{ color }}>{line}</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>

            {git?.untracked_files && git.untracked_files.length > 0 && (
              <div style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: 'var(--surface-raised)' }}>
                <span className="eyebrow" style={{ color: 'var(--warning)' }}>UNTRACKED FILES</span>
                <ul style={{ listStyle: 'none', padding: 0, marginTop: '4px' }}>
                  {git.untracked_files.map((uf, idx) => (
                    <li key={idx}>
                      <code style={{ fontSize: '10px' }}>{uf}</code>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {git?.git_results && git.git_results.length > 0 && (
              <div>
                <button
                  type="button"
                  className="quiet-button"
                  onClick={() => setShowFullGit(!showFullGit)}
                >
                  {showFullGit ? '▲ Hide Full Git Output' : '▼ Show Full Git Command Output'}
                </button>

                {showFullGit && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                    {git.git_results.map((gres, i) => (
                      <div key={i} style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: '4px', background: '#0d1015' }}>
                        <span className="mono" style={{ fontSize: '10px', color: 'var(--accent)' }}>$ {gres.command}</span>
                        <pre style={{ fontSize: '10px', marginTop: '4px', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                          {gres.stdout || gres.stderr || '(empty)'}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
