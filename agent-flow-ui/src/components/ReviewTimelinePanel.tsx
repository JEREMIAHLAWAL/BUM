import React from 'react';
import type { RunState } from '../types';

interface ReviewTimelinePanelProps {
  run: RunState | null;
}

export const ReviewTimelinePanel: React.FC<ReviewTimelinePanelProps> = ({ run }) => {
  if (!run) return null;

  const { review, retries, stages } = run;
  const verdict = review?.verdict || 'PENDING';
  const isApprove = verdict === 'APPROVE';
  const isChangesRequired = verdict === 'CHANGES REQUIRED';
  const humanDecision = review?.human_decision;

  return (
    <div className="section-card review-timeline-panel">
      <div className="section-header">
        <span className="section-title">⚖ REVIEWER VERDICT & HUMAN DECISION</span>
      </div>

      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="eyebrow">AUTOMATED REVIEW:</span>
            <span
              className={`status-badge ${
                isApprove ? 'approved' : isChangesRequired ? 'failed' : 'waiting'
              }`}
            >
              {verdict}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="eyebrow">OPERATOR DECISION:</span>
            {humanDecision ? (
              <span
                className={`status-badge ${
                  humanDecision.decision === 'APPROVE' ? 'approved' : 'failed'
                }`}
              >
                {humanDecision.decision === 'APPROVE' ? '✔ APPROVED' : '✖ REJECTED'}
              </span>
            ) : run.status === 'awaiting_human_approval' ? (
              <span className="status-badge awaiting">
                <span className="pulse-dot" /> AWAITING OPERATOR APPROVAL
              </span>
            ) : (
              <span className="status-badge waiting">N/A</span>
            )}
          </div>
        </div>

        {humanDecision && humanDecision.reason && (
          <div style={{ padding: '8px 10px', background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: '4px', fontSize: '11px' }}>
            <span className="eyebrow" style={{ color: 'var(--warning)', display: 'block', marginBottom: '2px' }}>REJECTION REASON:</span>
            <span>{humanDecision.reason}</span>
          </div>
        )}

        {isChangesRequired && (
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '11px' }}>
            <div className={`status-badge ${review.frontend_fix_required ? 'failed' : 'waiting'}`}>
              Frontend Fix: {review.frontend_fix_required ? 'YES' : 'NO'}
            </div>
            <div className={`status-badge ${review.backend_fix_required ? 'failed' : 'waiting'}`}>
              Backend Fix: {review.backend_fix_required ? 'YES' : 'NO'}
            </div>
            <div className={`status-badge ${review.dependency_fix_required ? 'failed' : 'waiting'}`}>
              Dependency Fix: {review.dependency_fix_required ? 'YES' : 'NO'}
            </div>
          </div>
        )}

        {/* Execution Timeline */}
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
          <span className="eyebrow" style={{ display: 'block', marginBottom: '8px' }}>EXECUTION & REPAIR TIMELINE</span>
          <ol className="execution-timeline">
            {/* Initial Implementation Step */}
            <li>
              <span className="timeline-dot tone-success" />
              <div>
                <strong>Initial Implementation</strong>
                <span>
                  Planner → Frontend ({stages.frontend.attempts[0]?.duration_sec?.toFixed(1) || '--'}s) & Backend ({stages.backend.attempts[0]?.duration_sec?.toFixed(1) || '--'}s)
                </span>
              </div>
            </li>

            {/* Cycles */}
            {stages.reviewer.attempts.map((revAtt, idx) => {
              const cycleNum = revAtt.cycle || idx + 1;
              const testerAtt = stages.tester.attempts[idx];
              const retryInfo = retries.find((r) => r.from_cycle === cycleNum);

              return (
                <React.Fragment key={idx}>
                  <li>
                    <span className="timeline-dot tone-accent" />
                    <div>
                      <strong>Review Cycle {cycleNum}</strong>
                      <span>
                        Tester: {testerAtt?.status === 'complete' ? 'Evaluated' : 'Running'} | Reviewer: {revAtt.status === 'complete' ? 'Evaluated' : 'Pending'}
                      </span>
                    </div>
                  </li>

                  {retryInfo && (
                    <li>
                      <span className="timeline-dot tone-warning" />
                      <div>
                        <strong>
                          Repair Triggered (Cycle {retryInfo.from_cycle} ➔ {retryInfo.to_cycle})
                        </strong>
                        <span>
                          Target Agents: {retryInfo.target_agents.join(', ').toUpperCase()}
                        </span>
                      </div>
                    </li>
                  )}
                </React.Fragment>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
};
