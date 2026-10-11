# Task: TRAYNE Feature 3 & 4 — Workout History & Progress/PR Analytics (Rebuild)

## Context & Objectives
`src/app/(app)/history.tsx` and `src/app/(app)/analytics.tsx` were built once in an earlier
BUM pipeline run and briefly existed on disk (verified live-tested by the user in VS Code +
Expo), but that run's Reviewer cycle never reached final APPROVE, so the files were never
committed to git. They were then permanently destroyed by a later pipeline run's unconditional
startup `git reset --hard && git clean -fd` (a separate, now-logged bug — see MASTER_TODO
"CRITICAL: BUM Startup git reset..."). This task rebuilds both screens from scratch.

The historical draft (recovered from `pipeline/changes.md`'s own git history, commit `c0b920f`)
had the right feature *intent* but hallucinated throughout — invented a nonexistent nested
`Colors.gray[950]` / `Colors.red[500]` / `Colors.white` palette (real export is flat:
`Colors.background`, `Colors.surface`, `Colors.text`, etc. — see Pillar 2 below), and
referenced session fields/methods that don't exist (`session.programDayTitle`,
`session.totalVolume`, bare `sessionRepository.personalRecord()` return shape).
**Do not copy that draft's code. Use it only for feature/UX intent.**

## 4-Pillar Requirements & Guardrails

### 1. File Modification Isolation
Only create the following two files:
- `src/app/(app)/history.tsx`
- `src/app/(app)/analytics.tsx`

Also update `src/app/(app)/_layout.tsx` — verified live right now, it already registers 4 tabs
(`index`, `history`, `program`, `profile`) and the `history` tab entry already exists correctly
(icon, title, flat `Colors.*` tokens). **Only `analytics` is missing.** Add ONE new
`<Tabs.Screen name="analytics" ...>` entry (a `LineChart` or similar icon from
`lucide-react-native`, label "Analytics" or "Progress") — do not touch the 4 existing
`<Tabs.Screen>` entries or `screenOptions`.

Do not create new shared components beyond what's already available
(`EmptyState`, `SetLogger`, `NumericInput`, `WarningMessage` in `src/components/` — these now
exist, committed `c2d416d`). Do not touch `src/db/**`, `src/domain/**`, `src/generator/**`.

### 2. Strict Theme Token Guardrails
- MUST strictly use `Colors.*` (capitalized, NO `theme.` wrapper, FLAT keys — NOT a nested
  Tailwind-style palette). Import via `import { Colors } from '../../theme';` (two levels up
  from `src/app/(app)/`, matching the existing pattern in `profile.tsx`/`index.tsx`).
- Real exported keys (verified live against `src/theme/colors.ts` — use ONLY these):
  `background`, `surface`, `surfaceElevated`, `surfaceSubtle`, `border`, `borderActive`,
  `primary`, `primaryMuted`, `primaryForeground`, `text`, `textMuted`, `textSubtle`,
  `success`, `successSurface`, `warning`, `warningSurface`, `danger`, `dangerSurface`,
  `info`, `infoSurface`, `backdrop`.
- There is NO `Colors.gray[...]`, `Colors.red[...]`, `Colors.white`, `Colors.yellow[...]`, or
  any bracket-indexed color — these do not exist and must never appear in the output.

### 3. Package & Import Guardrails
- MUST use `lucide-react-native` for all icons.
- PROHIBITED IMPORTS: Do NOT import `@expo/vector-icons` or `date-fns`.

### 4. Verified Real Signatures — Use These, Not Invented Ones
From `src/db/repositories/sessionRepository.ts` (verify against live file before coding, this
is a summary):
- `listHistory(userId: string, options?: { limit?, offset?, completedOnly? }): Promise<SessionSummary[]>`
  — returns `{ id, title, startedAt, completedAt, durationSeconds, totalVolumeKg,
  workingSetCount, exerciseCount }`. NOTE: field is `title` and `totalVolumeKg`, NOT
  `programDayTitle` / `totalVolume`.
- `personalRecord(userId: string, exerciseId: string): Promise<{ weightKg, reps, achievedAt } | null>`
- `delete(sessionId: string): Promise<void>` — for History's delete action.
- `exerciseHistory(userId, exerciseId, options?)` and `weeklySetsByMuscle(...)` also exist if
  useful for Analytics, but keep scope to PRs + basic progress per the acceptance criteria
  below — do not over-build.
- Access via `useDatabase()` from `../../contexts/DatabaseContext` (verified live against
  `DatabaseContext.tsx` and `profile.tsx`'s actual usage) — this returns
  `{ dataLayer, loading, error }`, NOT flat repository names. `dataLayer` is `InitResult | null`
  and exposes `dataLayer.sessions` (SessionRepository), `dataLayer.profiles` (ProfileRepository),
  `dataLayer.exercises` (ExerciseRepository). Always null-check `dataLayer` (it's `null` while
  `loading` is true) before calling methods on it — see `profile.tsx`'s
  `const { dataLayer, loading: dbLoading } = useDatabase();` pattern.
- Use `dataLayer.profiles.requireCurrent()` to get the current user profile/id (single-user
  MVP, established pattern — see `src/db/repositories/profileRepository.ts`). Call methods as
  `dataLayer.sessions.listHistory(...)`, `dataLayer.sessions.personalRecord(...)`,
  `dataLayer.sessions.delete(...)` — NOT a bare `sessionRepository` variable.

### 5. Preservation of Domain & Context Invariants
- Do NOT delete, overwrite, or mutate pre-existing core domain logic (`src/domain/**`,
  `src/db/**`, `src/contexts/DatabaseContext.tsx`).

## Feature Intent (from recovered historical draft — UX only, not code)
- **History (`history.tsx`)**: Scrollable list of past completed workout sessions (newest
  first), each card showing title, date, and total volume. Delete action per session with a
  confirmation prompt. "Load more" / pagination using `listHistory`'s `limit`/`offset`. Empty
  state via `EmptyState` when no sessions exist yet.
- **Analytics (`analytics.tsx`)**: Personal-record display per exercise (weight x reps, with
  an estimated 1RM if you want — Epley formula `weightKg * (1 + reps / 30)` is fine to reuse
  as a calculation, it's just arithmetic, not hallucinated data). Empty state via `EmptyState`
  when there's not enough data yet (no completed sessions / no PRs).

## Acceptance Criteria
1. Planner produces an immutable `pipeline/contract.md` enforcing the 5 pillars above,
   explicitly declaring the real `Colors.*` keys and the real `sessionRepository` signatures
   as the EXPORTED SIGNATURES / PERMITTED TOKENS sections.
2. Frontend writes both screens using only verified-real `Colors.*` keys and verified-real
   repository method signatures — no invented palette, no invented fields.
3. Backend: no work required — all repository methods needed already exist.
4. Tester logs execution evidence into `.evidence/tester_verification.json`; typecheck must
   pass (this will directly catch any hallucinated `Colors.*` key or repository field, since
   `Colors` and `SessionSummary` are typed — this is a good forcing function, lean on it).
5. Reviewer verifies all components against disk evidence and issues `APPROVE`.
