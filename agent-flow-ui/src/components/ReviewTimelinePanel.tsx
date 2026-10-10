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

      <div className="review-summary-box">
        <div className="verdict-banner-row">
          <div className="verdict-pair">
            <span className="verdict-label">AUTOMATED REVIEW:</span>
            <span
              className={`verdict-badge ${
                isApprove ? 'approve' : isChangesRequired ? 'changes-req' : 'pending'
              }`}
            >
              {verdict}
            </span>
          </div>

          <div className="verdict-pair">
            <span className="verdict-label">OPERATOR DECISION:</span>
            {humanDecision ? (
              <span
                className={`verdict-badge ${
                  humanDecision.decision === 'APPROVE' ? 'approve' : 'changes-req'
                }`}
              >
                {humanDecision.decision === 'APPROVE' ? '✔ APPROVED' : '✖ REJECTED'}
              </span>
            ) : run.status === 'awaiting_human_approval' ? (
              <span className="verdict-badge awaiting">
                ⏳ AWAITING OPERATOR APPROVAL
              </span>
            ) : (
              <span className="verdict-badge pending">
                N/A
              </span>
            )}
          </div>
        </div>

        {humanDecision && humanDecision.reason && (
          <div className="human-reason-box">
            <span className="human-reason-label">REJECTION REASON:</span>
            <span className="human-reason-text">{humanDecision.reason}</span>
          </div>
        )}

        {isChangesRequired && (
          <div className="required-fixes-grid">
            <div className={`fix-tag ${review.frontend_fix_required ? 'required' : 'none'}`}>
              Frontend Fix: {review.frontend_fix_required ? 'YES' : 'NO'}
            </div>
            <div className={`fix-tag ${review.backend_fix_required ? 'required' : 'none'}`}>
              Backend Fix: {review.backend_fix_required ? 'YES' : 'NO'}
            </div>
            <div className={`fix-tag ${review.dependency_fix_required ? 'required' : 'none'}`}>
              Dependency Fix: {review.dependency_fix_required ? 'YES' : 'NO'}
            </div>
          </div>
        )}
      </div>

      {/* Cycle Transition Timeline */}
      <div className="timeline-container">
        <span className="timeline-title">EXECUTION & REPAIR TIMELINE</span>
        <div className="timeline-items">
          {/* Initial Execution Node */}
          <div className="timeline-step">
            <div className="step-marker initial">0</div>
            <div className="step-content">
              <span className="step-heading">Initial Implementation</span>
              <p className="step-desc">
                Planner → Frontend ({stages.frontend.attempts[0]?.duration_sec?.toFixed(1) || '--'}s)
                & Backend ({stages.backend.attempts[0]?.duration_sec?.toFixed(1) || '--'}s)
              </p>
            </div>
          </div>

          {/* Tester & Reviewer Cycles */}
          {stages.reviewer.attempts.map((revAtt, idx) => {
            const cycleNum = revAtt.cycle || idx + 1;
            const testerAtt = stages.tester.attempts[idx];
            const retryInfo = retries.find((r) => r.from_cycle === cycleNum);

            return (
              <React.Fragment key={idx}>
                <div className="timeline-step">
                  <div className={`step-marker cycle-${cycleNum}`}>{cycleNum}</div>
                  <div className="step-content">
                    <span className="step-heading">Review Cycle {cycleNum}</span>
                    <p className="step-desc">
                      Tester: {testerAtt?.status === 'complete' ? 'Evaluated' : 'Running'} | Reviewer: {revAtt.status === 'complete' ? 'Evaluated' : 'Pending'}
                    </p>
                  </div>
                </div>

                {retryInfo && (
                  <div className="timeline-step repair-step">
                    <div className="step-marker repair">⟳</div>
                    <div className="step-content repair-box">
                      <span className="step-heading">
                        Repair Triggered (Cycle {retryInfo.from_cycle} ➔ {retryInfo.to_cycle})
                      </span>
                      <p className="step-desc">
                        Target Agents: {retryInfo.target_agents.join(', ').toUpperCase()}
                      </p>
                    </div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};
