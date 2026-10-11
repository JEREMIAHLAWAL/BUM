# Task: TRAYNE Core Shared Component Hardening (Stage 2)

## Context & Objectives
Now that the BUM SWE Orchestrator has been upgraded with Spec-First Contracts (BMAD), Evidence-on-Disk (GSD), and Ralph Micro-Commit Savepoints, we must implement Stage 2: Core Shared Component Hardening for the TRAYNE mobile codebase (`CLAUDE/trayne`).

This replaces the monolithic bug triage attempt with strict, modular, and verified core shared UI primitives. (DB transaction hardening was scoped out — already implemented correctly; see File Modification Isolation note below.)

## 4-Pillar Requirements & Guardrails

### 1. File Modification Isolation
Only create or update the following core shared files:
- `src/components/EmptyState.tsx` (Shared empty state placeholder with title, message, optional action button)
- `src/components/SetLogger.tsx` (Clean, standardized weight/reps/rpe logger row)
- `src/components/NumericInput.tsx` (Sanitized numeric keypad/input for weights & reps)
- `src/components/WarningMessage.tsx` (Card-style warning banner for volume capacity overloads)

Note: Atomic SQLite transactions are already implemented and in use (`src/db/sql.ts`
`transaction()` interface, both adapters, and `exerciseRepository.ts` /
`programRepository.ts` / `sessionRepository.ts` all call `this.db.transaction(...)`
correctly where multi-statement writes occur). `profileRepository.ts` only issues
single-statement writes per method, which don't need wrapping. No DB hardening work
remains — do not create `src/db/transaction.ts` or touch `src/db/**`.

### 2. Strict Theme Token Guardrails
- MUST strictly use `Colors.*` (capitalized, NO `theme.` wrapper — exported from
  `src/theme/colors.ts`, re-exported via `src/theme/index.ts`, and imported with a
  relative path matching the file's depth, e.g. `import { Colors } from '../theme';`
  or `'../../theme'` — verify existing repo files for the correct relative path).
- NEVER reference hallucinated properties like `theme.colors.*`, `Colors.gray[...]`,
  `Colors.dark[...]`, etc. — verify against the real exported keys in `src/theme/colors.ts`
  before using any token.

### 3. Package & Import Guardrails
- MUST use `lucide-react-native` for all icons.
- PROHIBITED IMPORTS: Do NOT import `@expo/vector-icons` or `date-fns`.

### 4. Preservation of Domain & Context Invariants
- Do NOT delete, overwrite, or mutate pre-existing core domain logic (`src/domain/units.ts`, `src/domain/errors.ts`, `src/db/DatabaseContext.tsx`).

## Acceptance Criteria
1. Planner produces an immutable `pipeline/contract.md` enforcing the 4 pillars.
2. Frontend and Backend write the shared component primitives. (No backend/DB work required this run.)
3. Tester logs execution evidence into `.evidence/tester_verification.json`.
4. Reviewer verifies all components against disk evidence and issues `APPROVE`.
