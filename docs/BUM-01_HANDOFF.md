# BUM-01 — Windows cleanup handoff

**Checkpoint:** October 18, 2026, 07:19 UTC. **State:** BUM-01 complete; stop here.

## Preserved refs and ownership

- BUM branch: `fix/fs-011-console-compatibility`.
- Saved mixed WIP remains ancestor `000e76afb8f2cef53f2639f3a299a633c80feb8f`; no other repair was changed or started.
- Exact tested code/test commit: `8d1b35799e1612e1384325194e52d569bb57d866`. Later handoff commits change documentation/evidence only.
- FinderShip branch/base throughout real probes: `fs-011/authentication` at `20e1108f1ed967b80fa660a553d825f7f18eaa91`.
- Freshly fetched GitHub startup publication: main `7fce3d341e8bd007e7c413fb5082923adfe9c3df`; also read task-branch WORK_STATUS and resume checklist. Brief: `FINDERSHIP/FS-011_IMPLEMENTATION_BRIEF.md`; source versions Discovery 40, Technical Plan 29, Master To-Do 30, section 01 v1, section 07 v11. Source snapshots were not edited.
- Coordinator owns this infrastructure checkpoint. Auxiliary implementation/test work is not execution of the external FS-011 Planner, Frontend, Backend, Tester or Reviewer. No full-console approval, independent review, CI, auth coverage or founder acceptance is inferred.

## Change and diagnosis

Only `orchestrator/worktree_tools.py` and `orchestrator/test_worktree_bootstrap.py` changed in the code commit. Windows filesystem teardown retries only actual sharing/lock errors 32/33: five attempts, waits 0.1/0.2/0.4/0.8 seconds. Other errors stop immediately. Structured diagnostics retain attempts, error codes/history and last error, including after eventual success. Persistent failure preserves available registration/branch; unregister/delete follow confirmed filesystem removal. Existing long-path and junction-target protections remain.

The old named probe reproduced error 32 at an empty ordinary dependency directory after previous processes had completed; it was not a junction or a demonstrated read-only/path-length failure. A read-only Restart Manager query registered the directory but returned error 5 from GetList, so it did not identify a lock owner. No claim is made about antivirus/Syncthing or the exact external locker. Later bounded cleanup progressed across two error-32 dependency directories and succeeded on attempt 3. This demonstrates transient sharing behavior on the real residual, not an identified lock-owning process. No unrelated process was killed and no global setting was changed.

An approval timeout paused the first attempt at final verification/publication. The founder explicitly resumed; final observed evidence below supersedes the earlier blocked handoff.

## Exact-head verification

Windows Python 3.14.7; portable Node 24.22.0 and pnpm 10.9.0. Child Node also 24.22.0. TEMP/TMP/TMPDIR explicitly set to coordinator scratch for the final tests/probe.

At BUM `8d1b35799e1612e1384325194e52d569bb57d866`:

| Command / check | Actual outcome |
| --- | --- |
| `python -m unittest orchestrator.test_legacy_import_safety -v` | 3 tests, OK, 0.063s; run before larger suite |
| `python -m unittest orchestrator.test_worktree_bootstrap orchestrator.test_legacy_import_safety -v` | 35 tests, OK, 53.261s |
| `git diff --check` | Exit 0 |
| `python .../scratch/bum01_verify.py` | Exit 0; archived identical script at `docs/evidence/BUM-01/verify_windows.py` |
| Fresh isolated frozen pnpm bootstrap | Success; actual install, not mocks |
| `node --version`, `pnpm --version`, `pnpm exec node --version` | Exit 0; 24.22.0 / 10.9.0 / 24.22.0 |
| `pnpm run typecheck` | Exit 0; shared and web checks complete |
| `pnpm run lint` | Exit 0; tooling, shared and web checks complete |

The narrow suite includes simulated errors 32/33, immediate refusal of unrelated errors, real fixture-child Windows handles released during backoff and held persistently, branch/registration preservation, long paths, junction target preservation and unrelated-worktree protection. The worker observed the new transient-error test fail before production edits, then pass afterward; the coordinator independently reran the complete narrow suite on the committed code above. No broad discovery or live-provider test was run.

## Real cleanup read-back

- Old residual `run_fs011_bootstrap_20261018T065158Z_1a3963`: `worktree_removed=true`, `branch_deleted=true`, filesystem attempts 3, two retained error-32 diagnostics. Filesystem path absent; FinderShip worktree list has only its canonical checkout; exact run branch absent. Canonical HEAD/status unchanged.
- Final fresh run `run_bum01_20261018T071707Z_e4efce`: install/typecheck/lint passed, then cleanup returned both flags true on filesystem attempt 1. Directory, registration and run branch independently read back absent.
- Fresh root, web and shared `node_modules` were directories, not junctions/symlinks. Canonical HEAD, status and root dependency-directory inode matched before/after.
- Final registries showed only the canonical BUM checkout and canonical FinderShip checkout. No residual from either BUM-01 verification run or the old named probe remains.
- Canonical FinderShip's pre-existing four untracked transfer inputs were preserved. Subsequent coordinator documentation edits/commits are intentional handoff changes, not probe mutation.

Machine-readable observations: [fresh worktree](evidence/BUM-01/fresh-worktree.json), [old residual cleanup](evidence/BUM-01/residual-cleanup.json). The archived verification script is machine-specific, creates/removes one new managed FinderShip probe, and must not be imported or run casually; rerunning is outside this completed chat.

## What remains

BUM-02 through BUM-05 remain pending. Their preserved partial repairs are not accepted by this narrow pass. No console restart or FS-011 auth execution occurred. No credentials were inspected, no live Supabase/email was used, and no merge/deployment was performed. Existing five role identities remain untouched.

## Ready-to-paste next-chat kickoff

> Work on BUM-02 only. Read current GitHub FinderShip AGENTS.md and docs/WORK_STATUS.md, then BUM docs/BUM-01_HANDOFF.md and docs/FS011_CONSOLE_TODO.md on fix/fs-011-console-compatibility. Preserve WIP ancestor 000e76afb8f2cef53f2639f3a299a633c80feb8f and completed BUM-01 code 8d1b35799e1612e1384325194e52d569bb57d866. Finish only run-scoped artifacts, original source propagation and safe legacy resume using offline side-effect-isolated regressions. Do not start contract parsing, Tester batch handling, consolidated readiness or authentication. Publish the handoff and stop.
