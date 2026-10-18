# BUM-02 — Run-scoped artifacts, original source and safe resume

**Checkpoint:** October 18, 2026, 15:11 UTC. **State:** BUM-02 complete; stop after publication. No successor is authorized by this handoff.

## Preserved refs and startup

- BUM branch `fix/fs-011-console-compatibility`; clean startup at published BUM-01 handoff `ddbd8e9c85bf62877a6c491c397552b7b88f5e3e`.
- Exact tested code/test/audit-runner commit: `44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb`. Later publication changes documentation/evidence only.
- Saved mixed WIP `000e76afb8f2cef53f2639f3a299a633c80feb8f` and completed BUM-01 code `8d1b35799e1612e1384325194e52d569bb57d866` remain ancestors; no reset, cleanup sweep or discarded repair.
- FinderShip branch `fs-011/authentication` at startup/preservation check `b4fb750e21d7f44d279180c56eaf457f68ade14e`. Its four untracked transfer inputs were preserved, including byte hashes. Subsequent FinderShip documentation commits are intentional handoff changes, not test mutations.
- Freshly fetched GitHub main `7fce3d341e8bd007e7c413fb5082923adfe9c3df`: read AGENTS/status, shared guide, source manifest, published `FINDERSHIP/FS-011_IMPLEMENTATION_BRIEF.md`, current continuations and task-branch status/checklist. All 15 manifest hashes match publication. Source versions remain Discovery 40, Technical Plan 29, Master To-Do 30, section 01 v1 and section 07 v11. Canonical snapshots were not edited.
- Installed Hermes project-context loader selected FinderShip `.hermes.md` required markers at the root and `apps/web`; the startup skill was loaded. This verifies discovery, not an automatic network-fetch service.
- Owner: Hermes coordinator with a bounded infrastructure implementation worker. This is not execution of the external FS-011 five-stage console, its Tester/Reviewer, or BUM-05 combined readiness.

## Completed scope

- Preserved run wrapper creates `.bum/runs/<run_id>/pipeline` before implementation writes, records project/path/run/lineage metadata, and restores artifact/project contexts after implementation or setup failure. Existing-run directories cannot be overwritten. Retry lineage does not import previous artifacts.
- Handoff and salvage reads now fail closed for malformed/non-object provenance. Scoped reads require the canonical project plus matching artifact directory and run marker. Foreign/unprovenanced shared handoff/salvage do not load.
- Run details expose persisted artifact metadata. Retry refuses a different selected project or missing canonical project provenance before starting a worker. Same-project retry launches a new complete isolated pipeline with lineage only.
- Legacy HTTP `/resume` returns 409 with the exact retry route; manual `run_test_and_review()` refuses before artifact reads, repository inspection, provider calls, commands or Git. No production change was needed in the already-disabled manual helper.
- Original `@file:` content is resolved once, saved as `resolved_task.md`, and prefixed immutably to all five roles. Regression mutates the source after the first implementation stage and proves the original survives the Planner protocol retry, both Frontend/Backend repair stages, and repeated Tester/Reviewer stages.
- New production changes are restricted to artifact provenance in `orchestrator/pipeline.py` and project-safe retry in `orchestrator/agent_flow/server.py`. Tests: new `orchestrator/test_bum02_artifacts.py` and import/command isolation in the existing artifact/source test classes. `BatchPreflightTests` and contract implementation are unchanged and were not run.

## Exact verification

Environment: Windows, Python 3.14.7. Credential loading disabled before console imports. Fixture writes confined to Hermes scratch, with TEMP/TMP/TMPDIR explicitly resolved there.

| Check | Actual result |
| --- | --- |
| Startup prerequisite: `python -m unittest orchestrator.test_legacy_import_safety -v` | 3 tests OK, 0.217s; before broader tests |
| Worker narrow run | 18 tests OK, 0.499s; working diff only, not exact-head publication evidence |
| Exact `44a5e19` audit runner: `python -B docs/evidence/BUM-02/run_offline.py --output C:/Users/2880441/AppData/Local/hermes/cache/scratch/bum02-exact-head-audit.json` | Exit 0; prerequisite 3 tests OK, 0.027s, then BUM-02 18 tests OK, 0.597s; no skips, failures or errors |
| `git diff --check` | Exit 0 |
| FinderShip preservation before intentional handoff edits | HEAD/status unchanged at `b4fb750`; all four untracked input SHA-256 values unchanged |
| BUM and FinderShip worktree registries | Only their canonical checkouts; no real probe/worktree was created by these tests |

The 18-test selection is `orchestrator.test_bum02_artifacts`, `orchestrator.test_artifact_scope_and_batch.ArtifactScopeTests`, and `orchestrator.test_artifact_scope_and_batch.CanonicalSourceStageTests`. The runner executes import-safety first and stops on failure; it does not perform discovery. Machine-readable logs: [exact-head-results.json](evidence/BUM-02/exact-head-results.json). Its elapsed group fields include loading/runner overhead; unittest timings above come from the captured logs.

The audit denied credential-file opens, external subprocess/network calls and filesystem mutations outside scratch; the successful exact-head run recorded zero denied attempts. Six stdlib Windows asyncio self-pipe socketpair connections were explicitly identified and allowed, not general loopback/provider traffic. Provider/command/Git boundaries and repository/context resolution were mocked in the modules actually invoked. Real file reads/writes exercised only scratch fixture repositories and artifacts; command outputs were labeled fixtures, not claimed real command results.

### Failure/fix evidence

The implementation worker observed RED before production edits: malformed JSON objects raised `AttributeError`, mismatched scoped metadata still exposed handoff, and a foreign-project retry started instead of refusing. A separate missing-provenance retry regression failed with `HTTPException not raised`; both retry guards are now covered. These are worker observations, distinct from the coordinator's committed-head rerun.

The coordinator's first audit-runner attempt was overrestrictive: it blocked six stdlib Windows asyncio socketpair self-pipe connections, causing six test failures before the route coroutines ran. The harness was corrected to recognize only that exact stdlib caller/socket; no production workaround or general network exception was added. The corrected precommit run passed, then the committed-head run above passed. The initial harness failure was not a production regression.

## Bounded review

A separate read-only worker reported no blocking findings after inspecting the BUM-02 diff, artifact/provenance routing, immutable source/repair paths, resume/retry guards, execution manager and test isolation. Production/test changes were committed unchanged as `44a5e19`. This was static auxiliary BUM-02 review only: no runtime tests by that reviewer, no external FS-011 Reviewer stage and no combined BUM-05 readiness approval. Coordinator runtime evidence is recorded separately above.

## Limits and next owner

Historical retry events without canonical project provenance intentionally require selecting the intended project and starting a new full run with the original task. Legacy retained-worktree recovery is not implemented. Scoped provenance is a local correctness guard, not cryptographic protection against arbitrary local metadata tampering.

No live providers, real test commands/Git mutations/worktree lifecycle, console restart, broad discovery, full readiness pass, CI, auth cases, Supabase/email, credential inspection, migrations, main merge or deployment were performed. Existing role identities/configuration remain untouched. BUM-03 and BUM-04 partial work is preserved but unaccepted; BUM-05 combined verification and independent readiness review remain pending. FS-011 stays paused until BUM-05.

## Ready-to-paste next-chat kickoff

> Do BUM-03 only. Read current GitHub FinderShip AGENTS.md and docs/WORK_STATUS.md, then BUM docs/BUM-02_HANDOFF.md and docs/FS011_CONSOLE_TODO.md on fix/fs-011-console-compatibility. Preserve saved WIP ancestor 000e76afb8f2cef53f2639f3a299a633c80feb8f, completed BUM-01 code 8d1b35799e1612e1384325194e52d569bb57d866 and BUM-02 tested code 44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb; inspect current changes before editing. Finish only contract-section parsing and read-only ownership, with the real extractor feeding actual Tester authorization, reference conflicts and Next route-group compatibility. Run import-safety before broader tests and isolate provider, command, Git and filesystem side effects, including import-time dotenv loading. Do not start BUM-04, BUM-05, authentication or a console restart. Publish exact test results and both repositories' handoffs with the next-chat prompt, then stop.
