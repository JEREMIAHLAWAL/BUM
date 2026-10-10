import React, { useState } from 'react';
import { fetchPromptPreview } from '../api';
import { PromptPreviewModal } from './PromptPreviewModal';

interface TaskInputBarProps {
  onLaunch: (task: string, label?: string) => Promise<void>;
  onStop?: () => Promise<void>;
  isPipelineRunning: boolean;
  isCancellationRequested?: boolean;
  activeRunId: string | null;
  initialTask?: string;
  initialLabel?: string;
  onClearInitial?: () => void;
}

export const TaskInputBar: React.FC<TaskInputBarProps> = ({
  onLaunch,
  onStop,
  isPipelineRunning,
  isCancellationRequested,
  activeRunId,
  initialTask = '',
  initialLabel = '',
  onClearInitial,
}) => {
  const [taskText, setTaskText] = useState(initialTask);
  const [taskLabel, setTaskLabel] = useState(initialLabel);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);

  React.useEffect(() => {
    if (initialTask) {
      setTaskText(initialTask);
    }
    if (initialLabel) {
      setTaskLabel(initialLabel);
    }
  }, [initialTask, initialLabel]);

  // Prompt Preview Modal state
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewFilePath, setPreviewFilePath] = useState<string | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanTask = taskText.trim();
    if (!cleanTask) {
      setInputError('Please enter a task description before running the pipeline.');
      return;
    }

    setInputError(null);
    setIsSubmitting(true);
    try {
      await onLaunch(cleanTask, taskLabel.trim() || undefined);
      // UX Choice: Clear prompt textarea upon successful launch
      setTaskText('');
      setTaskLabel('');
      if (onClearInitial) onClearInitial();
    } catch (err: any) {
      setInputError(err.message || 'Failed to submit task to pipeline.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePreviewPrompt = async () => {
    const cleanTask = taskText.trim();
    if (!cleanTask) {
      setInputError('Please enter prompt text or an @file:path reference to preview.');
      return;
    }

    // Check if task contains an @file: reference
    const fileMatch = cleanTask.match(/@file:([^\s]+)/);
    if (fileMatch) {
      const referencedPath = fileMatch[1];
      setIsLoadingPreview(true);
      try {
        const data = await fetchPromptPreview(referencedPath);
        setPreviewTitle(taskLabel.trim() || referencedPath);
        setPreviewFilePath(data.resolved_path || referencedPath);
        setPreviewContent(data.content);
        setPreviewModalOpen(true);
        setInputError(null);
      } catch (err: any) {
        setInputError(`Could not load @file prompt (${referencedPath}): ${err.message}`);
      } finally {
        setIsLoadingPreview(false);
      }
    } else {
      setPreviewTitle(taskLabel.trim() || 'Custom Task Prompt');
      setPreviewFilePath(null);
      setPreviewContent(cleanTask);
      setPreviewModalOpen(true);
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
    <div className="task-input-section">
      <div className="task-input-header">
        <div className="task-input-title-group">
          <span className="task-input-icon">⚡</span>
          <span className="task-input-title">NEW DEVELOPMENT TASK</span>
        </div>
        {isPipelineRunning && (
          <div className={`pipeline-running-badge ${isCancellationRequested ? 'stopping' : ''}`}>
            <span className="pulse-dot"></span>
            <span>
              {isCancellationRequested
                ? `STOP REQUESTED (${activeRunId || 'stopping...'})`
                : `PIPELINE ACTIVE (${activeRunId || 'in progress'})`}
            </span>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="task-input-form">
        <div className="task-label-input-row">
          <label className="task-label-input-label">Run Label (Optional):</label>
          <input
            type="text"
            className="task-label-input"
            placeholder="e.g., Feature 3 - History Screen, or Bugfix - Dark Mode"
            value={taskLabel}
            onChange={(e) => setTaskLabel(e.target.value)}
            disabled={isPipelineRunning || isSubmitting}
          />
        </div>

        <textarea
          className="task-textarea"
          placeholder="Enter detailed development task specification or '@file:pipeline/prompts/task.md'..."
          value={taskText}
          onChange={(e) => {
            setTaskText(e.target.value);
            if (inputError) setInputError(null);
          }}
          rows={3}
          disabled={isPipelineRunning || isSubmitting}
        />

        {inputError && <div className="task-input-error-msg">⚠ {inputError}</div>}

        <div className="task-input-actions">
          <span className="task-input-hint">
            Preserves full line breaks. Supports <code>@file:pipeline/prompts/task.md</code> references.
          </span>
          <div className="task-actions-btn-group">
            <button
              type="button"
              className="btn-preview-prompt"
              onClick={handlePreviewPrompt}
              disabled={!taskText.trim() || isLoadingPreview}
              title="Preview prompt markdown content"
            >
              {isLoadingPreview ? '🔍 Loading...' : '👁 Preview Prompt'}
            </button>
            {isPipelineRunning && (
              <button
                type="button"
                className="btn-stop-pipeline"
                onClick={handleStopClick}
                disabled={isCancellationRequested || isStopping}
                title="Request cooperative pipeline stop at next safe boundary"
              >
                {isStopping || isCancellationRequested ? '⏹ Stopping...' : '⏹ STOP PIPELINE'}
              </button>
            )}
            <button
              type="submit"
              className={`btn-run-pipeline ${isPipelineRunning ? 'running' : ''}`}
              disabled={isButtonDisabled}
            >
              {isSubmitting
                ? 'Starting...'
                : isPipelineRunning
                ? isCancellationRequested
                  ? '⏹ Stopping...'
                  : '▶ Pipeline Running...'
                : '▶ RUN PIPELINE'}
            </button>
          </div>
        </div>
      </form>

      {previewModalOpen && (
        <PromptPreviewModal
          title={previewTitle}
          filePath={previewFilePath}
          content={previewContent}
          onClose={() => setPreviewModalOpen(false)}
        />
      )}
    </div>
  );
};
