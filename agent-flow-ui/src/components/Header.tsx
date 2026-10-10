import React from 'react';
import type { WorkspaceProject } from '../api';

interface HeaderProps {
  run?: any;
  selectedRunId?: string | null;
  isConnected: boolean;
  projects?: WorkspaceProject[];
  activeProjectPath?: string;
  onSelectProject?: (pathOrId: string) => void;
  onRefresh?: () => void;
  onClone?: (task: string, label?: string) => void;
  audioEnabled?: boolean;
  onToggleAudio?: () => void;
  onOpenSidebar?: () => void;
  onNewTask?: () => void;
  onCommandMenu?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  isConnected,
  projects = [],
  activeProjectPath = '',
  onSelectProject,
  audioEnabled = false,
  onToggleAudio,
  onOpenSidebar,
  onNewTask,
  onCommandMenu,
}) => {
  return (
    <header className="app-header">
      <div className="brand">
        <button
          type="button"
          className="icon-button mobile-menu"
          aria-label="Open run history"
          onClick={onOpenSidebar}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="4" x2="20" y1="12" y2="12" />
            <line x1="4" x2="20" y1="6" y2="6" />
            <line x1="4" x2="20" y1="18" y2="18" />
          </svg>
        </button>
        <span className="brand-mark" aria-hidden="true">
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M2 10v3" />
            <path d="M6 6v11" />
            <path d="M10 3v18" />
            <path d="M14 8v7" />
            <path d="M18 5v13" />
            <path d="M22 10v3" />
          </svg>
        </span>
        <span>
          BUM
          <span className="brand-caption">CONSOLE</span>
        </span>
      </div>

      <div className="header-workspace">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="muted">
          <path d="M9 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v5" />
          <circle cx="13" cy="12" r="2" />
          <path d="M18 19c-2.8 0-5-2.2-5-5v8" />
          <circle cx="20" cy="19" r="2" />
        </svg>

        <div className="select-wrap">
          <label className="sr-only" htmlFor="workspace">Project workspace</label>
          <select
            id="workspace"
            value={activeProjectPath}
            onChange={(e) => onSelectProject?.(e.target.value)}
          >
            {projects.length > 0 ? (
              projects.map((p) => (
                <option key={p.id} value={p.path}>
                  {p.name}
                </option>
              ))
            ) : (
              <option value="">BUM orchestrator</option>
            )}
          </select>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </div>

        <span className="header-slash">/</span>
        <span className="header-location">Engineering</span>
      </div>

      <div className="header-actions">
        <span className={`connection ${isConnected ? 'connection-connected' : 'connection-offline'}`} role="status">
          <i aria-hidden="true" />
          {isConnected ? 'Connected' : 'Offline'}
        </span>

        <span className="header-divider" />

        <button
          type="button"
          className="icon-button"
          aria-label={audioEnabled ? 'Disable audio chimes' : 'Enable audio chimes'}
          aria-pressed={audioEnabled}
          onClick={onToggleAudio}
        >
          {audioEnabled ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z" />
              <path d="M16 9a5 5 0 0 1 0 6" />
              <path d="M19.364 18.364a9 9 0 0 0 0-12.728" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z" />
              <line x1="22" x2="16" y1="9" y2="15" />
              <line x1="16" x2="22" y1="9" y2="15" />
            </svg>
          )}
        </button>

        <button
          type="button"
          className="icon-button command-trigger"
          aria-label="Open command menu"
          title="Command menu · Ctrl/⌘ K"
          onClick={onCommandMenu}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3" />
          </svg>
        </button>

        <button
          type="button"
          className="button button-small header-new"
          onClick={onNewTask}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14" />
            <path d="M12 5v14" />
          </svg>
          New task
        </button>
      </div>
    </header>
  );
};
