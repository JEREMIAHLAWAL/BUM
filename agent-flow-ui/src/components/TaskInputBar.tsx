import React, { useState } from 'react';
import { fetchPromptPreview } from '../api';
import { PromptPreviewModal } from './PromptPreviewModal';

interface TaskInputBarProps {
  onLaunch: (task: string, label?: string) => Promise<void>;
  onStop?: () => Promise<void>;
  isPipelineRunning: boolean;
  isCancellationRequested?: boolean;
  activeRunId?: string | null;
  initialTask?: string;
  initialLabel?: string;
  onClearInitial?: () => void;
}

export const TaskInputBar: React.FC<TaskInputBarProps> = ({
  onLaunch,
  onStop,
  isPipelineRunning,
  isCancellationRequested,
  initialTask = '',
  initialLabel = '',
  onClearInitial,
}) => {
  const [taskText, setTaskText] = useState(initialTask);
  const [taskLabel, setTaskLabel] = useState(initialLabel);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [maxCycles, setMaxCycles] = useState(3);
  const [selectedModel, setSelectedModel] = useState('inherit');

  // Prompt Preview Modal state
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  React.useEffect(() => {
    if (initialTask) {
      setTaskText(initialTask);
    }
    if (initialLabel) {
      setTaskLabel(initialLabel);
    }
  }, [initialTask, initialLabel]);

  // Extract file matches for badge tokens
  const fileMatches = Array.from(
    new Set(
      Array.from(taskText.matchAll(/@file:(?:"([^"\n]+)"|([^\s]+))/g)).map((m) => m[1] ?? m[2])
    )
  );

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanTask = taskText.trim();
    if (!cleanTask) {
      setInputError('Please enter a task description before running the pipeline.');
      return;
    }

    setInputError(null);
    setIsSubmitting(true);
    try {
      await onLaunch(cleanTask, taskLabel.trim() || undefined);
      setTaskText('');
      setTaskLabel('');
      if (onClearInitial) onClearInitial();
    } catch (err: any) {
      setInputError(err.message || 'Failed to submit task to pipeline.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePreviewFile = async (filePath: string) => {
    setIsLoadingPreview(true);
    try {
      const data = await fetchPromptPreview(filePath);
      setPreviewTitle(filePath.split('/').pop() || filePath);
      setPreviewFilePath(data.resolved_path || filePath);
      setPreviewContent(data.content);
      setPreviewModalOpen(true);
      setInputError(null);
    } catch (err: any) {
      setInputError(`Could not load @file (${filePath}): ${err.message}`);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleStopClick = async () => {
    if (!onStop || isStopping || isCancellationRequested) return;
    setIsStopping(true);
    try {
      await onStop();
    } catch (err: any) {
      setInputError(err.message || 'Failed to request pipeline stop.');
    } finally {
      setIsStopping(false);
    }
  };

  const isButtonDisabled = isPipelineRunning || isSubmitting || !taskText.trim();

  return (
    <section className={`task-composer ${isCollapsed ? 'is-collapsed' : ''}`} aria-label="Launch a development task">
      <div className="composer-heading">
        <span>
          <span className="composer-plus">+</span>
          New development task
        </span>
        <button
          type="button"
          className="quiet-button"
          aria-expanded={!isCollapsed}
          onClick={() => setIsCollapsed(!isCollapsed)}
        >
          {isCollapsed ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m6 9 6 6 6-6" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="m18 15-6-6-6 6" />
            </svg>
          )}
          <span>{isCollapsed ? 'Expand' : 'Collapse'}</span>
        </button>
      </div>

      {!isCollapsed && (
        <form
          onSubmit={handleSubmit}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              e.preventDefault();
              handleSubmit();
            }
          }}
        >
          <label className="sr-only" htmlFor="task-prompt">Task prompt or @file reference</label>
          <textarea
            id="task-prompt"
            placeholder="Describe what you want to build, fix, or refactor…"
            value={taskText}
            onChange={(e) => {
              setTaskText(e.target.value);
              if (inputError) setInputError(null);
            }}
            rows={2}
            disabled={isPipelineRunning || isSubmitting}
          />

          <div className="composer-toolbar">
            <div className="composer-config">
              <label className="label-field">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
                  <circle cx="7.5" cy="7.5" r=".5" fill="currentColor" />
                </svg>
                <span className="sr-only">Optional run label</span>
                <input
                  placeholder="Run label"
                  value={taskLabel}
                  onChange={(e) => setTaskLabel(e.target.value)}
                  disabled={isPipelineRunning || isSubmitting}
                />
              </label>

              <span className="config-divider" />

              <div className="model-field">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <line x1="21" x2="14" y1="4" y2="4" />
                  <line x1="10" x2="3" y1="4" y2="4" />
                  <line x1="21" x2="12" y1="12" y2="12" />
                  <line x1="8" x2="3" y1="12" y2="12" />
                  <line x1="21" x2="16" y1="20" y2="20" />
                  <line x1="12" x2="3" y1="20" y2="20" />
                  <line x1="14" x2="14" y1="2" y2="6" />
                  <line x1="8" x2="8" y1="10" y2="14" />
                  <line x1="16" x2="16" y1="18" y2="22" />
                </svg>
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  disabled={isPipelineRunning || isSubmitting}
                >
                  <option value="inherit">Workspace defaults</option>
                  <option value="claude-sonnet">Anthropic · Claude Sonnet</option>
                  <option value="gpt-4">OpenAI · GPT-4.1</option>
                  <option value="qwen3">Ollama · Qwen3</option>
                </select>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </div>

              <span className="config-divider" />

              <div className="cycle-counter">
                <span>Max cycles</span>
                <button
                  type="button"
                  aria-label="Decrease maximum review cycles"
                  disabled={isPipelineRunning || maxCycles <= 1}
                  onClick={() => setMaxCycles(maxCycles - 1)}
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M5 12h14" />
                  </svg>
                </button>
                <output className="mono">{maxCycles}</output>
                <button
                  type="button"
                  aria-label="Increase maximum review cycles"
                  disabled={isPipelineRunning || maxCycles >= 5}
                  onClick={() => setMaxCycles(maxCycles + 1)}
                >
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M5 12h14" />
                    <path d="M12 5v14" />
                  </svg>
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {isPipelineRunning && (
                <button
                  type="button"
                  className="button button-danger button-small"
                  onClick={handleStopClick}
                  disabled={isCancellationRequested || isStopping}
                >
                  {isStopping || isCancellationRequested ? '⏹ Stopping...' : '⏹ STOP PIPELINE'}
                </button>
              )}

              <button
                type="submit"
                className="button button-primary launch-button"
                disabled={isButtonDisabled}
              >
                {isSubmitting ? (
                  'Launching…'
                ) : isPipelineRunning ? (
                  isCancellationRequested ? '⏹ Stopping...' : '▶ Pipeline Running...'
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="9 10 4 15 9 20" />
                      <path d="M20 4v7a4 4 0 0 1-4 4H4" />
                    </svg>
                    <span>Launch task</span>
                    <kbd>⌘ / Ctrl ↵</kbd>
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="composer-hint">
            <span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4" />
                <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                <path d="m5 12-3 3 3 3" />
                <path d="m9 18 3-3-3-3" />
              </svg>
              {fileMatches.length > 0 ? (
                fileMatches.map((f, i) => (
                  <button
                    key={i}
                    type="button"
                    className="quiet-button"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '1px 6px',
                      height: '20px',
                      borderRadius: '3px',
                      background: 'var(--surface-raised)',
                      border: '1px solid var(--border-subtle)',
                      cursor: 'pointer',
                      fontSize: '10px',
                      color: 'var(--accent)',
                    }}
                    onClick={() => handlePreviewFile(f)}
                    title={`Click to preview @file:${f}`}
                  >
                    <code>@file:{f}</code>
                    <span style={{ fontSize: '9px', opacity: 0.8 }}>👁</span>
                  </button>
                ))
              ) : (
                <span>
                  Reference a prompt with <code>@file:prompts/task.md</code>
                </span>
              )}
            </span>
            <span className="mono">
              {isLoadingPreview ? 'Loading file…' : taskText.length ? `~${Math.ceil(taskText.length / 4)} tokens` : 'Markdown supported'}
            </span>
          </div>

          {inputError && <p className="inline-error" role="alert">{inputError}</p>}
        </form>
      )}

      {previewModalOpen && (
        <PromptPreviewModal
          title={previewTitle}
          filePath={previewFilePath}
          content={previewContent}
          onClose={() => setPreviewModalOpen(false)}
        />
      )}
    </section>
  );
};
