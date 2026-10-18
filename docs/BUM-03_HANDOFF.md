# BUM-03 — Contract sections and read-only ownership

**Checkpoint:** October 18, 2026, 15:41 UTC. **State:** BUM-03 complete; stop after publication. This handoff does not authorize a successor.

## Preserved refs and startup

- BUM branch `fix/fs-011-console-compatibility`, initially clean at BUM-02 publication `8f81d3368154aa8a0ac6c3e814100501ff51b31a`.
- Exact tested code/test/audit-runner commit: `44da6a57f72fa62e17456e4fdb0f8dc58d397e63`. Later publication changes documentation/evidence only.
- Saved WIP ancestor `000e76afb8f2cef53f2639f3a299a633c80feb8f`, BUM-01 tested code `8d1b35799e1612e1384325194e52d569bb57d866`, and BUM-02 tested code `44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb` preserved. Both contract files initially matched the saved WIP. No reset or discarded partial repairs.
- FinderShip branch `fs-011/authentication`, startup/preservation HEAD `b5b3bc1a3af182fbb473a309518a69436bf65dfa`. Four existing untracked transfer inputs preserved byte-for-byte; see [baseline](evidence/BUM-03/preservation-before.json).
- Freshly fetched GitHub main `7fce3d341e8bd007e7c413fb5082923adfe9c3df`: read current AGENTS/status, shared guide, manifest, published brief, relevant continuations, task-branch work status, resume TODO and published Planner readiness. All 15 manifest hashes verified. Canonical source snapshots unchanged.
- Owner: Hermes coordinator with bounded auxiliary infrastructure workers. Existing five-role configuration unchanged, SHA-256 `3c1f8032a3bcb0df09ec1c1ca98bf060c4dc792af9f0700b27cbf27c04abff4b`. This is not external FS-011 Tester/Reviewer execution or combined console readiness.

## Completed scope

- `orchestrator/contract_tools.py`: heading-stack parsing for ATX/setext and conventional plain/bold labels, numbered/nested role headings, correct sibling/shallow section termination. Fenced, quoted and indented examples cannot grant ownership. Nested reference sections cannot be promoted by writable-looking descendants.
- Whole-token path extraction preserves Next route groups and dynamic/catch-all brackets. Unsupported globs, malformed delimiter tokens and attached prefixes/suffixes cannot manufacture writable filename fragments.
- Writable/reference conflicts reject both section orders. Lexical `normpath` and platform `normcase` detect dot-segment/repeated-separator aliases and Windows case aliases solely as a conflict veto. Stored literal paths are never normalized into permission grants; no repository lookup is performed for identity comparison.
- Real extractor feeds actual Tester validation, apply parser, write/delete helpers and filesystem guards in scratch. Covered reference write/delete rejection with unchanged contents, valid owned create/update/delete, dynamic route writes, manifest restrictions and guard rejection. Authorization and filesystem helpers are not mocked.
- The preserved readiness fixture was not verbatim published output; replaced it with the exact published specification. Coordinator AST comparison verified equality to `FinderShip/pipeline/FS-011_PLANNER_READINESS.md` excluding only its publication wrapper. Fixture SHA-256: `65db0360ec6b6f07c79a4a1752058fe27a6bbacaf9aebe3c1c32b2389d28243d`.
- No changes to `pipeline.py`, batch preflight, providers, authentication, or role configuration. BUM-04 mixed-module tests were not run.

## Exact verification

Environment: Windows, Python 3.14.7. Dotenv disabled and mocked before real repository/provider imports. TEMP/TMP/TMPDIR resolve to Hermes scratch; fixture filesystem mutations stay there.

| Check | Actual result |
| --- | --- |
| Initial standalone prerequisite: `python -B -m unittest orchestrator.test_legacy_import_safety -v` | 3 tests OK, 0.342s; before broader tests |
| Committed-head command: `python -B docs/evidence/BUM-03/run_offline.py --output C:/Users/2880441/AppData/Local/hermes/cache/scratch/bum03-exact-head-audit.json` | Exit 0 at `44da6a5`; import-safety first, 3 tests OK, 0.028s; then 30 contract tests OK, 0.774s; zero failures/errors/skips |
| Side-effect audit | Zero denied attempts; zero allowed stdlib socketpair exceptions |
| `git diff --check` | Exit 0 |
| Preservation before intentional handoff edits | FinderShip HEAD/status/worktree registry unchanged at `b5b3bc1`; all 15 source hashes, four untracked input hashes and five-role configuration hash unchanged |
| Worktree registries | Only canonical BUM and FinderShip checkouts; no probe/worktree created |

Raw captured logs and counts: [exact-head-results.json](evidence/BUM-03/exact-head-results.json). Group elapsed times include imports/loading: 0.029s safety and 2.688s contract; table timings are unittest execution times. The runner stops on safety failure or any recorded denial, and selects only `orchestrator.test_contract_section_ownership` afterward—no broad discovery.

Provider/command/Git/repository discovery and shared pipeline-context readers are fail-closed in the modules actually bound. Actual scratch file operations and authorization remain real. Audit rejects credential-file opens, subprocesses, external networking and out-of-scratch mutations, recording denied attempts even if caught. Coordinator Git operations below are intentional checkpoint publication, outside application tests.

## RED evidence and auxiliary review

The worker observed RED for dynamic-path truncation, section hierarchy/reference handling, labels and token integrity before fixes. [Initial RED](evidence/BUM-03/worker-initial-red.json) records 22 scoped tests with 11 failures, after 3 safety tests passed; this is working-diff evidence, not the final revision.

Auxiliary static review identified two remaining authorization gaps: unmatched delimiters could grant truncated writable aliases, and string-only conflicts missed equivalent reference paths. Follow-up TDD reproduced both before fixing: [literal RED](evidence/BUM-03/review-literals-red.json) and [alias RED](evidence/BUM-03/review-aliases-red.json). Final coordinator committed-head run above verifies the fixes. Review itself was read-only; no claim of a second post-fix external Reviewer verdict.

Runner review identified unguarded shared artifact/context readers and setup failures that lost JSON evidence. Those guards/reporting were fixed before the tested commit. A deliberate harness-only setup-failure probe passed its 3 safety tests, then persisted a failed report with zero scoped tests loaded: [setup-failure evidence](evidence/BUM-03/harness-setup-failure.json). This intentional injected failure is not a production regression or part of the successful exact-head result.

## Limits and next owner

This is a conservative contract-heading/token extractor, not a general Markdown renderer or arbitrary local filesystem equivalence resolver. Alias identity uses host-platform lexical rules; existing real filesystem/link guards remain authoritative. No production permission widening, transactional batch guarantees or console readiness is claimed.

No BUM-04, BUM-05, console restart, real worktree lifecycle, provider invocation, full offline discovery, CI, authentication implementation/cases, Supabase/email, credential inspection, schema migration, main merge or deployment. FS-011 remains paused until BUM-05. Separate read-only engineering reviews are not the configured external five-role Reviewer or BUM-05 combined readiness approval.

## Ready-to-paste next-chat prompt

> Do BUM-04 only. Read current GitHub FinderShip AGENTS.md and docs/WORK_STATUS.md, then BUM docs/BUM-03_HANDOFF.md and docs/FS011_CONSOLE_TODO.md on fix/fs-011-console-compatibility. Preserve saved WIP ancestor 000e76afb8f2cef53f2639f3a299a633c80feb8f and completed BUM-01/02/03 tested commits 8d1b35799e1612e1384325194e52d569bb57d866, 44a5e19e0432bb0ca64c474aac7c00aa9bb9bfdb and 44da6a57f72fa62e17456e4fdb0f8dc58d397e63. Inspect current changes before editing. Finish only predictable Tester operation-batch preflight in pipeline.py and test_artifact_scope_and_batch.py: missing deletes, directory targets and parent-file conflicts must reject before the first mutation; simulate operation order and prove valid write-then-delete sequences. Preserve contract/reference/manifest/link guards and run-scoped artifacts. State unexpected IO/partial-write limits; no broad transactional rewrite. Run import-safety before broader tests and isolate provider, command, Git, repository/context and filesystem effects, including import-time dotenv loading. Do not start BUM-05, authentication or a console restart. Publish exact test results and both repositories' handoffs with the next-chat prompt, then stop.
