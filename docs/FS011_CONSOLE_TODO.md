# Console repair TODO — one bounded task per new chat

**State:** Paused by founder request. Do not continue this session's implementation.
**Repository:** `JEREMIAHLAWAL/BUM`.
**Branch:** `fix/fs-011-console-compatibility`.
**Original base:** `2c9740fc2c0423bb22f1055503a633c2a1e19e8a`.
**Snapshot:** the WIP commit containing this file, plus any explicitly recorded later residual edits. This is preservation, not acceptance or a green final head.
**Consumer:** FinderShip `fs-011/authentication`; auth implementation has not started.

## Startup and stop rules for every chat

- Read current GitHub FinderShip `AGENTS.md`, `docs/WORK_STATUS.md`, the task-branch handoff and this backlog before work. Follow the current source manifest/brief, not stale chat assumptions. Shared source snapshots remain read-only.
- Inspect both repositories' branch, exact HEAD, status, existing worktrees and active owners. Preserve the mixed WIP; do not discard it or start competing writers. Use serial chats because some issues share `pipeline.py`.
- Do **one numbered task only**, verify its acceptance criteria, update this checklist and FinderShip work status, commit/push an honest checkpoint, then stop. New blockers go onto this backlog; they do not silently expand the chat.
- Preserve the existing five configured roles. Auxiliary console engineering is not execution of the FS-011 Tester/Reviewer. No model substitution, replacement auth builders, credential-file inspection, main merge, deployment, live Supabase/email, purchases or FS-012.
- The old local console process was stopped for this pause. Do not assume port 8900 is running or its loaded code matches disk. Restart only when the relevant task authorizes it.

## Known evidence and limits

- Early integrated console suite: 115 offline tests passed **before** the latest artifact/contract fixes.
- Later targeted `orchestrator.test_worktree_bootstrap` + `orchestrator.test_legacy_import_safety`: 30 tests passed.
- Real isolated pnpm bootstrap, workspace typecheck and lint passed on Node24.22.0/pnpm10.9.0. Root dependencies were not shared and canonical FinderShip state was preserved.
- Historical at the saved WIP: a fresh parent probe failed cleanup with Windows sharing violation `WinError 32`; branch/registration were correctly preserved despite the 30-test pass. BUM-01 later removed it with bounded retries; see the completed handoff below.
- Historical residual probe: `run_fs011_bootstrap_20261018T065158Z_1a3963`, under `BUM/.bum/worktrees/`, belonged to the **FinderShip repository's** worktree registry. BUM-01 verified its path/registration/branch absent. Always inspect the owning registry; do not confuse it with BUM's own worktree list.
- Independent review identified cross-project artifact contamination, contract reference promotion, and predictable partial Tester batches. Partial fixes/new tests for those are preserved, but final combined results/review are pending.
- Existing Planner, unchanged identity, returned a proposed contract on a planning-only readiness call with low reasoning effort. This does not prove a full five-stage run works.
- Legacy capability scripts are now import-safe. Require the import-safety regression before broad discovery; patch all provider/command/Git/filesystem boundaries in the module actually invoked, including legacy resume helpers. Never run manual capability scripts against an unrelated default project.

## BUM-01 — Windows worktree cleanup and sharing violations

- [x] Reproduce/inspect the remaining exact managed worktree without altering canonical FinderShip.
- [x] Diagnose sharing violations after process completion; use bounded safe cleanup/retry only where justified. Do not kill unrelated processes, traverse junction targets, suppress errors or change global Git/OS settings.
- [x] Add regressions for temporary sharing violations and persistent failure; preserve branch/registration until removal actually succeeds.
- [x] Verify a real fresh isolated worktree can install, typecheck/lint and be completely removed, with canonical HEAD/status unchanged. Report any residual directory/registration explicitly.

**Completed October 18, 2026:** tested code `8d1b35799e1612e1384325194e52d569bb57d866`; import-safety 3/3 and targeted suite 35/35 passed. Old residual removed on retry attempt 3; final fresh real probe installed/typechecked/linted and was completely removed. Both canonical registries read back clean of probes; FinderShip HEAD/status preserved during verification. Actual external lock owner was not identified. Full evidence, limitations and next-chat prompt: [BUM-01 handoff](BUM-01_HANDOFF.md). BUM-02 onward and auth remain pending; stop here.

**Owned paths:** `orchestrator/worktree_tools.py`, `orchestrator/test_worktree_bootstrap.py`; evidence/docs. Read-only dependencies elsewhere.

**Kickoff:**
> Work only on BUM-01 from docs/FS011_CONSOLE_TODO.md in the BUM repository. Read current FinderShip GitHub AGENTS.md and docs/WORK_STATUS.md first. Preserve the WIP compatibility branch. Finish Windows cleanup/sharing-violation handling with targeted regressions and a real isolated cleanup read-back; do not start artifact, contract, batch or auth work. Publish evidence and stop.

## BUM-02 — Run-scoped artifacts and safe resume

- [x] Inspect preserved partial changes in `pipeline.py`, `agent_flow/server.py`, `resume_test_review.py` and `test_artifact_scope_and_batch.py`; do not assume they are complete.
- [x] Ensure a selected project/run cannot read another project's handoff/salvage. Initialize its artifact directory before writes, restore scope after failure, and publish provenance/path metadata.
- [x] Ensure legacy `/resume` cannot operate against shared artifacts or the wrong checkout. A useful refusal with safe retry guidance is acceptable until real run-scoped recovery exists.
- [x] Ensure canonical resolved task/brief reaches all existing tool-less stages, not only Planner. Test isolation without live provider or repository effects.

**Completed October 18, 2026:** exact tested code `44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb`. Audited import-safety prerequisite: 3 tests OK, 0.027s; then 18 scoped artifact/source/resume tests OK, 0.597s, zero denied side-effect attempts. All five roles, Planner retry and both implementation repairs retain original source. Foreign/missing-project retry refuses before a worker; legacy resume stays disabled. No batch/contract tests, real worktree/provider operations, console restart or auth. Evidence, limitations and next-chat prompt: [BUM-02 handoff](BUM-02_HANDOFF.md). BUM-03/04/05 remain pending; stop here.

**Exit:** real cross-project marker regression, scope restoration, resume guard and source propagation tests pass; no unrelated artifact contamination. Do not complete the batch task implicitly.

**Kickoff:**
> Work only on BUM-02 from docs/FS011_CONSOLE_TODO.md. Preserve partial edits and finish run-scoped artifacts/source propagation plus safe legacy resume behavior. Use offline side-effect-isolated regressions. Do not expand into Tester batch handling, contract parsing or auth. Push the handoff and stop.

## BUM-03 — Contract parsing and read-only ownership

- [x] Inspect partial `contract_tools.py` and `test_contract_section_ownership.py` work.
- [x] Parse writable/reference sections by real Markdown boundaries, including numbered/nested role headings and Next route-group paths.
- [x] Keep read-only references read-only and reject conflicting ownership; do not silently promote paths.
- [x] Prove this with the **real extractor feeding the actual Tester validator**, plus compatibility checks against the actual Planner readiness output.

**Completed October 18, 2026:** exact tested code/test/audit-runner `44da6a57f72fa62e17456e4fdb0f8dc58d397e63`. Import-safety first: 3 tests OK, 0.028s; then 30 contract tests OK, 0.774s; no failures/errors/skips or denied side-effect attempts. Real guarded scratch create/update/delete and reference rejection covered; nested sections, route groups/dynamic brackets, malformed-token truncation and filesystem-equivalent reference conflicts covered. Stored literal identifiers preserved. Planner fixture verified verbatim against publication. Existing five roles, pipeline/batch implementation and canonical source snapshots unchanged. Evidence, review findings/fixes, limits and BUM-04-only next-chat prompt: [BUM-03 handoff](BUM-03_HANDOFF.md). BUM-04/05 remain pending, FS-011 stays paused; stop here.

**Exit:** reference-write attack rejected end-to-end; valid owned paths remain usable; no production permission widening.

**Kickoff:**
> Work only on BUM-03 from docs/FS011_CONSOLE_TODO.md. Finish and verify the partial contract-section ownership fix. Test real extractor-to-Tester authorization, reference conflicts and route-group compatibility. No artifact, cleanup, batch or auth implementation. Publish exact results and stop.

## BUM-04 — Tester operation-batch preflight

- [ ] Inspect partial batch changes in `pipeline.py` and `test_artifact_scope_and_batch.py` after BUM-02's handoff.
- [ ] Reject predictable missing-delete, directory-target and parent-file conflicts before the first mutation.
- [ ] Simulate operation order correctly, including valid write-then-delete behavior. Do not weaken the manifest/contract/link guards.
- [ ] State unexpected IO/partial-write limitations honestly; avoid a broad transactional filesystem rewrite.

**Exit:** invalid later operations cause zero earlier writes in regressions; valid sequences work; all permission and failed-verification gates remain enforced.

**Kickoff:**
> Work only on BUM-04 from docs/FS011_CONSOLE_TODO.md. Finish predictable Tester-batch preflight with zero-write failure regressions and valid sequence checks. Preserve the run-scope and contract fixes. Do not launch auth or enlarge this task. Commit/push evidence and stop.

## BUM-05 — Consolidate, independently review and prove readiness

Depends on BUM-01 through BUM-04; do not treat earlier green subsets as this gate.

- [ ] Run import-safety gate, then the full offline console suite on an exact committed head. Record actual test counts/failures.
- [ ] Obtain independent review of the combined exact diff and fix only blocking findings through bounded follow-up tasks.
- [ ] Run a real isolated FinderShip preparation smoke, with verified Node24/pnpm10.9, frozen dependencies, actual checks and complete cleanup. Empty auth suites are expected to fail; do not hide them with an empty-suite success flag.
- [ ] Restart the same existing console and verify loaded revision, active FinderShip project, all five configured identities, artifact location and safe planning/readiness behavior. Do not start auth automatically.
- [ ] Push BUM code/test/review evidence and a FinderShip readiness handoff. Mark prerequisites ready only when verified.

**Kickoff:**
> Work only on BUM-05 from docs/FS011_CONSOLE_TODO.md after its four prerequisites are verified. Consolidate the existing console fixes, run exact-head regression and real isolated smoke/cleanup, obtain independent review, and publish readiness. Do not implement FS-011 in this chat; finish with its kickoff handoff.

## FS-011 — Separate authentication implementation chat

- [ ] After BUM-05, resume the existing FinderShip branch and published brief/addendum through the founder's external Planner → Frontend → Backend → Tester → Reviewer console.
- [ ] Implement the authorized auth slice, cover all 14 matrix cases, record browser/mock/live limits, run full required checks and independent review, and return a draft PR with exact-head evidence.
- [ ] No main merge, deployment, live email, migrations, purchases or FS-012. Founder acceptance remains pending.

**Kickoff:**
> Resume FS-011 only after BUM readiness is verified in the current GitHub work status. Read FinderShip AGENTS.md, docs/WORK_STATUS.md, docs/FS-011_RESUME_TODO.md, the published brief and integration addendum. Preserve the current branch/dependencies and use the existing external five-role console. Deliver authentication, all 14 cases and a verified draft PR; do not merge, deploy or start FS-012.
