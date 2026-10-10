import React, { useState } from 'react';
import type { RunState } from '../types';
import type { WorkspaceProject } from '../api';
import { fetchPromptPreview } from '../api';
import { PromptPreviewModal } from './PromptPreviewModal';

interface HeaderProps {
  run: RunState | null;
  selectedRunId: string | null;
  isConnected: boolean;
  projects?: WorkspaceProject[];
  activeProjectPath?: string;
  onSelectProject?: (pathOrId: string) => void;
  onRefresh: () => void;
  onClone?: (task: string, label?: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  run,
  selectedRunId,
  isConnected,
  projects = [],
  activeProjectPath = '',
  onSelectProject,
  onRefresh,
  onClone,
}) => {
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const handleInspectPrompt = async () => {
    if (!run?.task) return;
    const taskText = run.task.trim();
    const fileMatch = taskText.match(/@file:([^\s]+)/);
    if (fileMatch) {
      const referencedPath = fileMatch[1];
      setIsLoadingPreview(true);
      try {
        const data = await fetchPromptPreview(referencedPath);
        setPreviewTitle(run.label || run.run_id || referencedPath);
        setPreviewFilePath(data.resolved_path || referencedPath);
        setPreviewContent(data.content);
        setPreviewModalOpen(true);
      } catch (err: any) {
        setPreviewTitle(run.label || run.run_id || 'Prompt');
        setPreviewFilePath(null);
        setPreviewContent(`[Failed to load @file (${referencedPath}): ${err.message}]\n\nFull Raw Task:\n${taskText}`);
        setPreviewModalOpen(true);
      } finally {
        setIsLoadingPreview(false);
      }
    } else {
      setPreviewTitle(run.label || run.run_id || 'Run Task');
      setPreviewFilePath(null);
      setPreviewContent(taskText);
      setPreviewModalOpen(true);
    }
  };
  const getStatusBadge = (status?: string) => {
    const s = (status || 'waiting').toLowerCase();
    switch (s) {
      case 'running':
        return <span className="status-badge running"><span className="pulse-dot"></span> RUNNING</span>;
      case 'awaiting_human_approval':
      case 'awaiting approval':
      case 'approve':
        return <span className="status-badge awaiting"><span className="pulse-dot"></span> AWAITING APPROVAL</span>;
      case 'approved':
        return <span className="status-badge approved">✔ APPROVED</span>;
      case 'rejected':
        return <span className="status-badge rejected">✖ REJECTED</span>;
      case 'blocked':
      case 'dependency_action_required':
      case 'dependency_required':
        return <span className="status-badge blocked">✖ BLOCKED</span>;
      case 'failed':
        return <span className="status-badge failed">⚠ FAILED</span>;
      case 'interrupted':
      case 'stale':
        return <span className="status-badge interrupted">⚠ INTERRUPTED / STALE</span>;
      case 'cancelled':
      case 'canceled':
        return <span className="status-badge cancelled">⏹ CANCELLED</span>;
      default:
        return <span className="status-badge waiting">IDLE / {s.toUpperCase()}</span>;
    }
  };

  const formatDuration = (sec?: number | null) => {
    if (sec === undefined || sec === null) return '--';
    if (sec < 60) return `${sec.toFixed(1)}s`;
    const m = Math.floor(sec / 60);
    const rem = (sec % 60).toFixed(1);
    return `${m}m ${rem}s`;
  };

  return (
    <header className="control-header">
      <div className="header-top">
        <div className="brand-group">
          <div className="brand-title">
            <span className="brand-icon">⬡</span>
            <span className="brand-name">TRAYNE AGENT FLOW</span>
            <span className="brand-tag">CONTROL ROOM</span>
          </div>
          <div className="connection-status">
            <span className={`conn-indicator ${isConnected ? 'online' : 'offline'}`} />
            <span className="conn-label">{isConnected ? 'LIVE (SSE)' : 'DISCONNECTED'}</span>
          </div>

          {projects.length > 0 && onSelectProject && (
            <div className="project-switcher-container">
              <span className="project-label">WORKSPACE:</span>
              <select
                className="project-select"
                value={activeProjectPath}
                onChange={(e) => onSelectProject(e.target.value)}
                title="Switch Target Project Workspace"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.path}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="header-meta">
          <button className="btn-refresh" onClick={onRefresh} title="Reload Run Data">
            ⟳ Refresh
          </button>
          {run && (
            <>
              <div className="meta-box">
                <span className="meta-label">CYCLE</span>
                <span className="meta-value">
                  {run.current_cycle} / {run.max_review_cycles}
                </span>
              </div>
              <div className="meta-box">
                <span className="meta-label">DURATION</span>
                <span className="meta-value">{formatDuration(run.total_duration_sec)}</span>
              </div>
              <div className="meta-box">
                <span className="meta-label">REVIEWER VERDICT</span>
                <span className={`meta-value ${run.review?.verdict === 'APPROVE' ? 'text-green' : ''}`}>
                  {run.review?.verdict || 'PENDING'}
                </span>
              </div>
              <div className="meta-box status-box">
                <span className="meta-label">HUMAN DECISION</span>
                {getStatusBadge(run.status)}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="header-task-bar">
        <div className="task-info">
          <span className="task-label">CURRENT RUN:</span>
          {run?.label && <span className="run-header-label-badge">{run.label}</span>}
          <span className="task-run-id">{selectedRunId || 'No run selected'}</span>
          {run?.retry_of && (
            <span className="lineage-tag" title={`Direct parent run: ${run.retry_of}`}>
              ⟳ RETRY OF: {run.retry_of}
            </span>
          )}
        </div>
        <div className="task-info task-desc-box">
          <span className="task-label">TASK:</span>
          <span className="task-text">{run?.task || 'No active task description'}</span>
          {run?.task && (
            <>
              <button
                type="button"
                className="btn-header-prompt-inspect"
                onClick={handleInspectPrompt}
                disabled={isLoadingPreview}
                title="Inspect full prompt specification"
              >
                {isLoadingPreview ? '🔍' : '👁 Inspect Prompt'}
              </button>
              {onClone && (
                <button
                  type="button"
                  className="btn-header-prompt-inspect"
                  onClick={() => onClone(run.task || '', run.label || undefined)}
                  title="Clone prompt and settings into task bar"
                >
                  📋 Clone & Edit
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {previewModalOpen && (
        <PromptPreviewModal
          title={previewTitle}
          filePath={previewFilePath}
          content={previewContent}
          onClose={() => setPreviewModalOpen(false)}
        />
      )}
    </header>
  );
};
