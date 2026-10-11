# Session Handoff: BUM Pipeline Hardening ➔ Stage 2 Core Shared Component Run

## Target Milestone
Stage 2: TRAYNE Core Shared Component Hardening (`BUM/pipeline/prompts/core_shared_hardening.md`).
DB/transaction work was descoped — see below, already implemented correctly, not part of this run.

## What Was Actually Verified & Committed (corrected from earlier over-claims)
Earlier handoffs claimed Stage 1 (contract generation, evidence-on-disk, micro-commits) and the
providers.py token/empty-response fix were "completed" — this was **not fully true**. A full
git-pile review this session found most of it existed only as uncommitted Pi-local edits, never
actually shipped. Everything below is now verified committed on BUM `master` AND confirmed live
on the Pi (`git log --oneline -1` on Pi matched, service restarted, no startup errors):

| Commit | What | Verified how |
|---|---|---|
| `64cbe02` | NEEDS CONTEXT reference files now inlined read-only into Frontend/Backend prompts (`contract_tools.py`, `repo_tools.py`, `pipeline.py`) | 58/58 unit tests, manual extraction check |
| `1800322` | Evidence-on-disk (`evidence_tools.py`) + Ralph micro-commit (`micro_commit_tools.py`) — never committed before despite prior claims | 3 new tests pass on Pi, full suite 71/73 (2 pre-existing unrelated failures, see below) |
| `9dfd114` | `config/agents.yaml`: Frontend/Backend → Claude Sonnet 5.5, Planner/Tester → DeepSeek v4.1-flash | explicit user confirmation |
| `c4e066c` | `providers.py`: 16384 token limit + empty-response guard — **never actually landed before**, only a partial version existed | diffed against last-known-good, confirmed superset/no regression |
| `7665c3f` | `executor.py`: emits `stage_failed`/`pipeline_finished` on uncaught worker exceptions, so UI doesn't silently hang | diff review (small, additive, in except-branch only) |
| `40d7b0d` | `planner/frontend/backend/instructions.md`: SPEC CONTRACT declaration, FE/BE banned from self-writing `pipeline/changes.md` (clobber risk), theme token example corrected `theme.colors.*` → `Colors.*` | diff review + live disk check of `src/theme/colors.ts` |
| `22b3c8f` | Latest `spec.md`/`changes.md` run-artifact snapshots committed | confirmed these are legitimate per-run snapshots, not corrupted history (changes.md is rebuilt fresh every run by design, not append-only) |
| `3b81828` | Drafted (unexecuted) prompt for Planner stage-card model-name display bug | — |
| `22f8892` | **Corrected `core_shared_hardening.md` task prompt** — see below | verified against live TRAYNE disk |

TRAYNE side: commit `7ca5dc7` — `.bum/` and `.evidence/` run artifacts untracked + gitignored
(were spuriously tracked, caused false "working tree not clean" test failures). TRAYNE HEAD on
Pi confirmed clean at `7ca5dc7`.

**Known pre-existing issue, left as-is per user decision:** `test_dependency_tools.py` and
`test_review_retry_loop.py` assert `"src/app/" in git status --short` as a broken proxy for
"edits survived" with no self-created fixture — fails now that the tree is genuinely clean.
Out of scope, not a regression from this session's work.

## Two Real Bugs Found & Fixed in the Task Prompt Itself (before queuing)
1. **Wrong theme token**: prompt said `theme.colors.*`; real TRAYNE export (verified live on
   disk, `src/theme/colors.ts` + `src/theme/index.ts`) is `export const Colors = {...}` —
   capitalized, no wrapper, imported via relative path (`'../theme'` / `'../../theme'`).
2. **DB transaction work doesn't exist to do**: prompt told Planner to create
   `src/db/transaction.ts` / harden repo transactions. Verified live: `src/db/sql.ts` already
   defines a `transaction()` interface with SAVEPOINT nesting, both adapters implement it, and
   `exerciseRepository.ts`/`programRepository.ts`/`sessionRepository.ts` already call
   `this.db.transaction(...)` correctly everywhere multi-statement writes occur.
   `profileRepository.ts` only does single-statement writes, which don't need wrapping.
   **Nothing to harden — bullet removed, task rescoped to UI components only.**

Final corrected prompt lives at `BUM/pipeline/prompts/core_shared_hardening.md`, committed as
`22f8892`, confirmed synced to Pi byte-for-byte.

## Next Step & Prompt to Queue
```
Please implement core_shared_hardening according to @file:pipeline/prompts/core_shared_hardening.md
```

## What the Next Session Should Check Against the Run Result
1. Did Planner's `pipeline/spec.md`/`contract.md` scope to just the 4 UI components
   (`EmptyState.tsx`, `SetLogger.tsx`, `NumericInput.tsx`, `WarningMessage.tsx`) and avoid
   `src/db/**` entirely?
2. Did Frontend correctly use `Colors.*` (capitalized, no wrapper) — not `theme.colors.*` or a
   hallucinated `{ theme }` import?
3. Did Backend correctly report nothing-to-do, per the "No backend/DB work required this run"
   acceptance criterion?
4. Did Tester's report fit under the 16384 token limit without a `PROVIDER_EMPTY_RESPONSE` error
   (first real test of the `c4e066c` fix actually being live)?
5. Any new failure modes not seen in this session.

Do not assume anything is fixed without checking the actual pasted run output against repo
state — the user runs all Pi-side verification commands and pastes results back; no direct Pi
access from the agent side.
