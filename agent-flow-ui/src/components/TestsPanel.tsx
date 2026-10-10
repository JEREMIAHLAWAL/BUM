import React, { useState } from 'react';
import type { RunState } from '../types';

interface TestsPanelProps {
  run: RunState | null;
}

export const TestsPanel: React.FC<TestsPanelProps> = ({ run }) => {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  if (!run || !run.tests || run.tests.length === 0) {
    return (
      <div className="section-card tests-panel">
        <div className="section-header">
          <span className="section-title">🧪 TEST & TYPE-CHECK SUITE</span>
          <span className="count">0</span>
        </div>
        <div className="section-empty">No test or typecheck commands recorded yet.</div>
      </div>
    );
  }

  const toggleExpand = (idx: number) => {
    setExpandedIndex(expandedIndex === idx ? null : idx);
  };

  return (
    <div className="section-card tests-panel">
      <div className="section-header">
        <span className="section-title">🧪 TEST & TYPE-CHECK SUITE</span>
        <span className="count">{run.tests.length} RUNS</span>
      </div>

      <div style={{ padding: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {run.tests.map((testEntry, entryIdx) => (
          <div key={entryIdx} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-muted)' }}>
              <span>
                Stage: <strong>{testEntry.stage.toUpperCase()}</strong>
              </span>
              {testEntry.cycle !== null && <span>Cycle {testEntry.cycle}</span>}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {testEntry.commands.map((cmd, cmdIdx) => {
                const uniqueKey = entryIdx * 100 + cmdIdx;
                const isPass = cmd.returncode === 0 && !cmd.timed_out;
                const isExpanded = expandedIndex === uniqueKey;

                return (
                  <div
                    key={cmdIdx}
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: '4px',
                      background: 'var(--surface-raised)',
                      overflow: 'hidden',
                      cursor: 'pointer',
                    }}
                    onClick={() => toggleExpand(uniqueKey)}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 10px',
                        gap: '8px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                        <span className={`status-badge ${isPass ? 'approved' : 'failed'}`}>
                          {isPass ? 'PASS' : 'FAIL'}
                        </span>
                        <code style={{ fontSize: '11px', color: 'var(--text)' }}>{cmd.command}</code>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0, fontSize: '10px', color: 'var(--text-muted)' }}>
                        <span className="mono">exit: {cmd.returncode}</span>
                        {cmd.timed_out && <span className="status-badge failed">TIMEOUT</span>}
                        <span>{isExpanded ? '▲' : '▼'}</span>
                      </div>
                    </div>

                    {isExpanded && (
                      <div
                        style={{
                          padding: '8px 10px',
                          background: '#0d1015',
                          borderTop: '1px solid var(--border)',
                          fontSize: '11px',
                        }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {cmd.stdout && (
                          <div style={{ marginBottom: cmd.stderr ? '8px' : '0' }}>
                            <span className="eyebrow" style={{ display: 'block', marginBottom: '2px' }}>STDOUT</span>
                            <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--text-secondary)' }}>{cmd.stdout}</pre>
                          </div>
                        )}
                        {cmd.stderr && (
                          <div>
                            <span className="eyebrow" style={{ display: 'block', marginBottom: '2px', color: 'var(--error)' }}>STDERR</span>
                            <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--error)' }}>{cmd.stderr}</pre>
                          </div>
                        )}
                        {!cmd.stdout && !cmd.stderr && (
                          <span className="muted">No stdout or stderr output.</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
