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
          <span className="section-tag">0 EXECUTIONS</span>
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
        <div className="title-with-badge">
          <span className="section-title">🧪 TEST & TYPE-CHECK SUITE</span>
          <span className="section-badge">{run.tests.length} RUNS</span>
        </div>
      </div>

      <div className="tests-list">
        {run.tests.map((testEntry, entryIdx) => (
          <div key={entryIdx} className="test-entry-group">
            <div className="test-entry-header">
              <span className="stage-label">
                Stage: <strong>{testEntry.stage.toUpperCase()}</strong>
              </span>
              {testEntry.cycle !== null && (
                <span className="cycle-label">Cycle {testEntry.cycle}</span>
              )}
            </div>

            <div className="commands-list">
              {testEntry.commands.map((cmd, cmdIdx) => {
                const uniqueKey = entryIdx * 100 + cmdIdx;
                const isPass = cmd.returncode === 0 && !cmd.timed_out;
                const isExpanded = expandedIndex === uniqueKey;

                return (
                  <div
                    key={cmdIdx}
                    className={`command-item ${isPass ? 'pass' : 'fail'}`}
                    onClick={() => toggleExpand(uniqueKey)}
                  >
                    <div className="cmd-summary-row">
                      <div className="cmd-left">
                        <span className={`cmd-badge ${isPass ? 'pass' : 'fail'}`}>
                          {isPass ? 'PASS' : 'FAIL'}
                        </span>
                        <code className="cmd-text">{cmd.command}</code>
                      </div>
                      <div className="cmd-right">
                        <span className="ret-code">exit: {cmd.returncode}</span>
                        {cmd.timed_out && <span className="timeout-tag">TIMEOUT</span>}
                        <span className="expand-indicator">{isExpanded ? '▲' : '▼'}</span>
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="cmd-details" onClick={(e) => e.stopPropagation()}>
                        {cmd.stdout && (
                          <div className="cmd-log-block">
                            <span className="log-title">STDOUT:</span>
                            <pre className="log-pre">{cmd.stdout}</pre>
                          </div>
                        )}
                        {cmd.stderr && (
                          <div className="cmd-log-block error-block">
                            <span className="log-title">STDERR:</span>
                            <pre className="log-pre">{cmd.stderr}</pre>
                          </div>
                        )}
                        {!cmd.stdout && !cmd.stderr && (
                          <div className="cmd-log-block empty">No stdout or stderr output.</div>
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
