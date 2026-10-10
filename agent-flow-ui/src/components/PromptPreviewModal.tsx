import React, { useState } from 'react';
import { copyToClipboard } from '../utils/clipboard';

interface PromptPreviewModalProps {
  title: string;
  filePath?: string | null;
  content: string;
  onClose: () => void;
}

export const PromptPreviewModal: React.FC<PromptPreviewModalProps> = ({
  title,
  filePath,
  content,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!content) return;
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card prompt-preview-modal-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div className="prompt-modal-title-group">
            <span className="modal-title">PROMPT INSPECTOR</span>
            <span className="prompt-modal-subtitle">{title}</span>
            {filePath && <span className="prompt-modal-path">{filePath}</span>}
          </div>
          <div className="prompt-modal-header-actions">
            <button
              type="button"
              className={`copy-btn ${copied ? 'copied' : ''}`}
              onClick={handleCopy}
              title="Copy prompt text to clipboard"
            >
              {copied ? '✓ Copied' : '📋 Copy Prompt'}
            </button>
            <button className="modal-close-btn" onClick={onClose} title="Close Modal">
              ✕
            </button>
          </div>
        </div>

        <div className="modal-body prompt-preview-body">
          <div className="prompt-meta-info">
            <span>Size: {content.length} characters</span>
            <span>Lines: {content.split('\n').length}</span>
          </div>
          <pre className="prompt-preview-content">{content}</pre>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn-modal-cancel" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
