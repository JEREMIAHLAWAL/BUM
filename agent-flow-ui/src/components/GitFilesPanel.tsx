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
      <div className="section-header tabs-header">
        <div className="tab-buttons">
          <button
            className={`tab-btn ${activeTab === 'files' ? 'active' : ''}`}
            onClick={() => setActiveTab('files')}
          >
            📁 Files Changed ({totalFiles})
          </button>
          <button
            className={`tab-btn ${activeTab === 'git' ? 'active' : ''}`}
            onClick={() => setActiveTab('git')}
          >
            🌿 Git Diff & Untracked
          </button>
        </div>
      </div>

      <div className="tab-content-body">
        {activeTab === 'files' ? (
          <div className="files-breakdown">
            {/* Live Operations Activity Bar */}
            {operations.length > 0 && (
              <div className="live-file-ops-timeline">
                <div className="live-ops-header">
                  <span className="live-ops-title">⚡ REAL-TIME FILE MODIFICATION LOG</span>
                  <span className="live-ops-count">{operations.length} operations</span>
                </div>
                <div className="live-ops-list">
                  {operations.map((op, idx) => (
                    <div key={idx} className={`live-op-row ${op.status}`}>
                      <span className="live-op-status-badge">
                        {op.status === 'in_progress' ? '⏳ WRITING' : '✔ VERIFIED'}
                      </span>
                      <span className="live-op-stage-tag">{op.stage.toUpperCase()}</span>
                      <code className="live-op-path">{op.path}</code>
                      {op.bytes !== undefined && op.bytes > 0 && (
                        <span className="live-op-bytes">{(op.bytes / 1024).toFixed(1)} KB</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {totalFiles === 0 && operations.length === 0 ? (
              <div className="section-empty">No file modifications recorded in this run.</div>
            ) : (
              <div className="files-categories-grid">
                {/* Created */}
                <div className="file-category-block created-block">
                  <div className="cat-title">
                    <span className="cat-dot created" />
                    <span>CREATED ({created.length})</span>
                  </div>
                  {created.length > 0 ? (
                    <ul className="file-path-list">
                      {created.map((f, i) => (
                        <li key={i}>
                          <code>{f}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="empty-cat">None</span>
                  )}
                </div>

                {/* Modified */}
                <div className="file-category-block modified-block">
                  <div className="cat-title">
                    <span className="cat-dot modified" />
                    <span>MODIFIED ({modified.length})</span>
                  </div>
                  {modified.length > 0 ? (
                    <ul className="file-path-list">
                      {modified.map((f, i) => (
                        <li key={i}>
                          <code>{f}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="empty-cat">None</span>
                  )}
                </div>

                {/* Deleted */}
                <div className="file-category-block deleted-block">
                  <div className="cat-title">
                    <span className="cat-dot deleted" />
                    <span>DELETED ({deleted.length})</span>
                  </div>
                  {deleted.length > 0 ? (
                    <ul className="file-path-list">
                      {deleted.map((f, i) => (
                        <li key={i}>
                          <code>{f}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="empty-cat">None</span>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="git-diff-view">
            <div className="diff-stat-card">
              <span className="stat-label">GIT DIFF STAT:</span>
              <pre className="diff-pre">{git?.diff_stat || 'No diff stat available.'}</pre>
            </div>

            {/* Interactive Code Diff Viewer */}
            <div className="diff-stat-card">
              <span className="stat-label">INTERACTIVE CODE DIFF:</span>
              {(() => {
                const diffCmd = git?.git_results?.find((g) => g.command && g.command.includes('git diff') && !g.command.includes('--stat'));
                const diffText = diffCmd?.stdout || '';
                if (!diffText || !diffText.trim()) {
                  return <div className="section-empty">No code changes in diff.</div>;
                }
                const lines = diffText.split('\n');
                return (
                  <div className="interactive-diff-box">
                    {lines.map((line, idx) => {
                      let type = 'context';
                      if (line.startsWith('diff --git') || line.startsWith('index ')) type = 'header';
                      else if (line.startsWith('@@')) type = 'chunk';
                      else if (line.startsWith('+') && !line.startsWith('+++')) type = 'add';
                      else if (line.startsWith('-') && !line.startsWith('---')) type = 'del';

                      return (
                        <div key={idx} className={`diff-line diff-${type}`}>
                          <span className="diff-ln">{idx + 1}</span>
                          <span className="diff-content">{line}</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>

            {git?.untracked_files && git.untracked_files.length > 0 && (
              <div className="untracked-card">
                <span className="untracked-label">UNTRACKED FILES (??):</span>
                <ul className="untracked-list">
                  {git.untracked_files.map((uf, idx) => (
                    <li key={idx}>
                      <code>{uf}</code>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {git?.git_results && git.git_results.length > 0 && (
              <div className="full-git-toggle-area">
                <button
                  className="btn-toggle-git"
                  onClick={() => setShowFullGit(!showFullGit)}
                >
                  {showFullGit ? '▲ Hide Full Git Output' : '▼ Show Full Git Command Output'}
                </button>

                {showFullGit && (
                  <div className="full-git-list">
                    {git.git_results.map((gres, i) => (
                      <div key={i} className="raw-git-item">
                        <span className="git-cmd-title">$ {gres.command}</span>
                        <pre className="git-raw-pre">{gres.stdout || gres.stderr || '(empty)'}</pre>
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
