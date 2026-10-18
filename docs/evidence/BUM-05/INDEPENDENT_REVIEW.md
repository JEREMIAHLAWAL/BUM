# BUM-05 independent review record

Date: October 18, 2026. **Disposition: bounded console-code/tooling review PASS.** This is auxiliary independent review, not execution or sign-off by the configured FS-011 Reviewer stage. Reviewers were read-only; the coordinator performed the actual tests and live readbacks.

## Exact identities

- Combined comparison base: saved WIP `000e76afb8f2cef53f2639f3a299a633c80feb8f`.
- BUM-05 parent: `14ea6a493266294db7014966286984080e58321c`. BUM-04 had already passed independent bounded review.
- Reviewed tree `3a06ee6c37761f9c20eba3c49bd02754366785a8` became commit `37436552690ad3f308421805c326c32e8e7a12fb` without changes. Two final reviewers separately covered combined production/regressions and verification tooling.
- Reviewed Windows-runtime follow-up tree `37ae4b0016bc52599bd2935a9e66a6097cfb9ca6` became commit `4ed2d1c8b500beb53d987d50c8cb5943ddb3e3c1` without changes.
- Reviewed read-only capture/tooling tree `f9bf55d5716e3ead086dce3a85dc980439ca522d` became commit `396ff0a4ff713714c1c4b963767dfb7d58e7bc1d` without changes. Production console code, parser, role configuration and instructions are unchanged from the preceding two checkpoints. Final exact-head suite and loaded-console HTTP readback ran on this commit.
- Later evidence/documentation publication is a successor, not an assertion that its future commit was already tested or reviewed.

## Findings and dispositions

| Finding | Disposition and real verification |
| --- | --- |
| Unsafe API prompt fixture writes/deletes beneath real AGENTS_ROOT; historical project/event/cancellation/architecture fixtures leak canonical state | Scratch fixtures and explicit roots/provenance now preserve canonical state; full audited suite passes. Existing WIP provider-key mocks retained. |
| Offline runner lacked enforced isolation, provenance, retained setup failures and nonzero aggregate failure | Pre-import deny-default audit; exact executable inventory including HEAD-only deletions and index additions; before/after hashes/status/diff; setup-failure JSON; negative probes. Trusted native Git/Python fixtures explicitly bounded, not broadly bypassed. |
| Staged-added Python inputs caused missing HEAD blob lookup before the prerequisite gate | HEAD inventory is distinguished from index/discovered files; regression covers both deletions and additions. |
| Retained run ID could trigger existing worktree/branch destruction before artifact rejection (P1) | Ownership/query preflight and atomic run-ID reservation precede create/teardown. Four added tests cover six owned-state scenarios, query failures, unrelated sibling preservation, and public-wrapper cancellation/context restoration. Review found no preexisting mutation on rejection. |
| Exact-head inventory omitted deleted executable helpers/entrypoints | Complete HEAD/index/discovered union; missing hashes remain explicit and dirty. Regression plus independent in-memory HEAD-only/index-only probes pass. |
| HTTP verifier expected nonexistent active_repo response field | Uses actual active_path schema; test extracts actual get_projects handler and checks positive/wrong-project/writable-authority cases. |
| Readiness declared success before bind; actual app exposed implementation routes; role/version/manifest fields merely recorded | Probe never declares standalone readiness. External GET/path-only guard blocks implementation and secret-preview routes. Exact expected HEAD, module/project/manifest identity, baseline roles/instructions and post-checks enforced. Independent PID/socket/HTTP session/version/artifact/idle/denial proof passed. |
| Bare pnpm could not launch Windows pnpm.CMD | Approved resolved executable paths checked within runtime, shell remains false. Actual node/pnpm/pnpm-executed-node version commands and regression pass. Initial failed attempt occurred before dotenv/provider use. |
| Read-only probe incorrectly required an executable writable contract | Now requires valid text with **zero write authority**, rejecting writable grants. Production authorization parser is unchanged. Original actual Planner response remains hash-pinned with its failed harness report intact; no new provider result is synthesized. |
| Single authorized Planner invocation already consumed before that harness correction | Separate current-console revalidation reads the genuine report/artifact and checks hashes, unchanged production code/instructions/identities, metadata and source prompt. Records genuine call HEAD/PID, original failure, and explicitly no new provider/dotenv invocation. Independent review accepted this only as read-only revalidation, never a fresh live call or implementation authorization. |

## Review execution handles

These local transcript handles identify the independent work; the published record above preserves its scope, exact trees, findings and dispositions rather than asserting an unsupported blanket sign-off.

- `deleg_7b36bb26`: initial combined production and full-tooling review; blocking findings, not acceptance.
- `deleg_40478778`: tooling corrections PASS at tree `e522524b57d59ff497b3aa3a5df1d51cfce2749a`.
- `deleg_dfcd44a0`: production P1 and final-tooling follow-ups PASS at tree `3a06ee6c37761f9c20eba3c49bd02754366785a8`.
- `deleg_1eec5e64`: resolved Windows executable follow-up PASS at tree `37ae4b0016bc52599bd2935a9e66a6097cfb9ca6`.
- `deleg_bd39d55d`: zero-authority correction/genuine capture revalidation PASS at tree `f9bf55d5716e3ead086dce3a85dc980439ca522d`, conditional on committed execution and independent real HTTP readback. Both conditions were subsequently exercised.

Local transcripts reside under `C:/Users/2880441/AppData/Local/hermes/cache/delegation/live/<delegation>/`. They are supplemental local history, not required to locate the tested commits or published evidence.

## Accepted limits

- Reviewers did not independently rerun the full suite, live service or provider. Coordinator execution records are separate and must not be attributed to them.
- Native Git is trusted with reviewed argv/path/config/environment controls and post-execution descendant validation; this is not hostile native-code OS confinement. Python children audit before workloads.
- Atomic run-ID reservation protects cooperating callers. Failures can retain a reserved ID slot; an untrusted external Git/filesystem race is outside the boundary.
- Windows sharing violations can outlast bounded cleanup retries. The actual preparation attempt failed closed on cleanup; later scoped recovery and exact readback passed. The failed report is retained.
- Current-console readiness used a historical **genuine** zero-authority Planner capture, not a second live invocation. It supplies no executable FS-011 contract and grants no implementation authority.
- Read-only browser preview blocks historical/stream/mutation routes. UI Offline/Not configured/Queued/main/default-model labels are not evidence of backend liveness, Git branch, loaded identities or actual execution. Exact API/PID/Git/config/artifact evidence is authoritative for this bounded proof.
