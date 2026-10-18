# BUM-04 — Tester operation-batch preflight

**Checkpoint:** October 18, 2026. **State:** BUM-04 complete; stop after publication. This handoff does not authorize a successor.

## Preserved refs and startup

- BUM branch `fix/fs-011-console-compatibility`, initially clean at BUM-03 publication `019ba0905d1b55f12885999db883d68eaedb5161`.
- Exact tested code/test/audit-runner commit: `ad18c636c2bab8a2cb86da9b732bb8f6f871bde6`. Later publication changes documentation/evidence only.
- Saved WIP ancestor `000e76afb8f2cef53f2639f3a299a633c80feb8f`, BUM-01 tested code `8d1b35799e1612e1384325194e52d569bb57d866`, BUM-02 tested code `44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb`, and BUM-03 tested code `44da6a57f72fa62e17456e4fdb0f8dc58d397e63` preserved.
- FinderShip branch `fs-011/authentication`, startup/preservation HEAD `4473a6351e11510074bdec48240cbd3865b9c26b`. Four existing untracked transfer inputs preserved byte-for-byte; see baseline [evidence/BUM-04/preservation-before.json](evidence/BUM-04/preservation-before.json).
- Freshly fetched GitHub main `7fce3d341e8bd007e7c413fb5082923adfe9c3df`: read current AGENTS/status, shared guide, manifest, published brief, relevant continuations, task-branch work status, resume TODO. All 15 manifest hashes verified. Canonical source snapshots unchanged.
- Owner: Hermes coordinator with bounded auxiliary infrastructure workers. Existing five-role configuration unchanged, SHA-256 `3c1f8032a3bcb0df09ec1c1ca98bf060c4dc792af9f0700b27cbf27c04abff4b`. This is not external FS-011 Tester/Reviewer execution or combined console readiness.

## Completed scope

- `orchestrator/pipeline.py`: `_preflight_tester_path_state` and `_validate_tester_file_operations` simulate sequential path operations before the first filesystem mutation.
- Predictable failure conditions reject before writing:
  - Missing deletes: attempting to delete a file that does not exist or was already deleted raises `FileNotFoundError` before earlier writes execute.
  - Directory targets: attempting to write or delete a directory raises `IsADirectoryError` before earlier writes execute.
  - Parent-file conflicts: attempting to write a child path when an ancestor path is a file (on disk or earlier in the batch) raises `NotADirectoryError` before earlier writes execute.
  - Contract and manifest boundaries: out-of-contract writes, writes to reference files, and writes escaping test roots raise `PermissionError` before any writes execute.
- Valid sequential operations succeed: write-then-delete of transient files and delete-then-write of replaced files work correctly.
- Unexpected I/O limits: unpredicted mid-batch disk/OS errors (e.g. disk full, EACCES) propagate honestly without asserting false transactional rollback.
- `orchestrator/test_artifact_scope_and_batch.py`: comprehensive tests covering predictable invalid operations, parent-file conflicts, sequential write-then-delete / delete-then-write, double deletes, contract/manifest boundary guards, and unpredicted I/O error propagation.

## Exact verification

Environment: Windows, Python 3.14.7. Dotenv disabled and mocked before real repository/provider imports. TEMP/TMP/TMPDIR resolve to Hermes scratch; fixture filesystem mutations stay there.

| Check | Actual result |
| --- | --- |
| Initial standalone prerequisite: `python -B -m unittest orchestrator.test_legacy_import_safety -v` | 3 tests OK, 0.024s; before broader tests |
| Committed-head command: `python -B docs/evidence/BUM-04/run_offline.py --output C:/Users/2880441/AppData/Local/hermes/cache/scratch/bum04_exact_head.json` | Exit 0 at `ad18c63`; import-safety first, 3 tests OK, 0.024s; then 15 batch/artifact/source tests OK, 0.275s; zero failures/errors/skips |
| Side-effect audit | Zero denied attempts; zero allowed stdlib socketpair exceptions |
| `git diff --check` | Exit 0 |
| Preservation before intentional handoff edits | FinderShip HEAD/status/worktree registry unchanged at `4473a63`; all 15 source hashes, four untracked input hashes and five-role configuration hash unchanged |
| Worktree registries | Only canonical BUM and FinderShip checkouts; no probe/worktree created |

Raw captured logs and counts: [exact-head-results.json](evidence/BUM-04/exact-head-results.json).

## Limits and next owner

This is a sequential operation-batch preflight simulator, not an ACID transactional filesystem. Unexpected I/O or OS-level write failures propagate honestly. No production permission widening or console restart is claimed.

No BUM-05, console restart, real worktree lifecycle, provider invocation, full offline discovery, CI, authentication implementation/cases, Supabase/email, credential inspection, schema migration, main merge or deployment. FS-011 remains paused until BUM-05.

## Ready-to-paste next-chat prompt

> Do BUM-05 only. Read current GitHub FinderShip AGENTS.md and docs/WORK_STATUS.md, then BUM docs/BUM-04_HANDOFF.md and docs/FS011_CONSOLE_TODO.md on fix/fs-011-console-compatibility. Preserve saved WIP ancestor 000e76afb8f2cef53f2639f3a299a633c80feb8f and completed BUM-01/02/03/04 tested commits 8d1b35799e1612e1384325194e52d569bb57d866, 44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb, 44da6a57f72fa62e17456e4fdb0f8dc58d397e63, and ad18c636c2bab8a2cb86da9b732bb8f6f871bde6. Consolidate console compatibility fixes across BUM-01 through BUM-04, run import-safety gate followed by full offline console test suite with exact results, obtain independent review, run real isolated FinderShip preparation smoke with full cleanup, and prove console readiness without implementing FS-011 authentication. Publish exact evidence and handoffs, then stop.
