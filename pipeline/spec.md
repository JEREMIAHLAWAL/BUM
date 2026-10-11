# Stage 2 — Core Shared Component & Database Hardening: Implementation Spec

**Repo:** TRAYNE (Mobile App) — working tree root `CLAUDE/trayne/`
**Project type:** react-native-expo (Expo SDK 51, expo-router, TypeScript strict, offline-first SQLite)
**Goal:** Introduce a small set of reusable, theme-correct UI primitives for the logging & warning surfaces, and add a first-class atomic-transaction helper for the data layer — without disturbing any existing domain logic, generator, repositories, or context wiring.

This spec is derived strictly from `pipeline/prompts/core_shared_hardening.md` and the project manifest rules. It contains no invented backend API or new dependency.

---

## 1. Scope split

- **FRONTEND TASK:** Create four shared components plus a barrel export under `src/components/` that consume `theme.colors.*` and `lucide-react-native`.
- **BACKEND TASK:** Create `src/db/transaction.ts` (a thin, atomic, repository-friendly transaction primitive layered on the existing `SqlDatabase` port) and wire it into the existing repositories' multi-statement writes.

No new runtime dependency is added. Nothing outside `src/` and `pipeline/` may be written.

---

## 2. SPEC CONTRACT

### 2.1 FILE BOUNDARIES

**Create (Frontend):**
- `src/components/EmptyState.tsx`
- `src/components/NumericInput.tsx`
- `src/components/SetLogger.tsx`
- `src/components/WarningMessage.tsx`
- `src/components/index.ts`

**Create (Backend):**
- `src/db/transaction.ts`
- `src/db/transaction.test.ts`

**Modify (Backend — narrow, additive only):**
- `src/db/repositories/sessionRepository.ts` — wrap the multi-statement write paths (`logSet`, `updateSet`, `deleteSet`, `complete`, `replaceFeedback`) in `withTransaction`.
- `src/db/repositories/programRepository.ts` — wrap the multi-statement write paths (`create`, `activate`, `createNextVersion`, `delete`) in `withTransaction`.

**Never create, modify, or delete:**
- `src/domain/units.ts`, `src/domain/errors.ts`, `src/domain/types.ts`, `src/domain/ids.ts`
- `src/data/exercises.seed.ts`
- `src/db/sql.ts`, `src/db/migrations.ts`, `src/db/mappers.ts`, `src/db/adapters/**`, `src/db/index.ts`
- `src/contexts/DatabaseContext.tsx` and `src/contexts/index.ts`
- `src/app/**` (routing/screens untouched in this stage)
- `src/generator/**`
- `package.json`, `package-lock.json`, `tsconfig*.json`, `jest.config.js`, `app.json`, `.env`

> NOTE: The prompt text refers to `src/db/DatabaseContext.tsx`; that path does not exist in this repo. The live file is `src/contexts/DatabaseContext.tsx`. Treat **both** as protected/out-of-scope — the invariant "do not mutate the DatabaseContext" is preserved either way.

### 2.2 EXPORTED SIGNATURES

All components are **named exports**, default-export-free, `React.FC`-free (plain function components), with explicit prop interfaces exported alongside the component.

```ts
// src/components/EmptyState.tsx
import type { LucideIcon } from 'lucide-react-native';

export interface EmptyStateProps {
  /** Headline. Required. */
  title: string;
  /** Optional supporting copy. */
  message?: string;
  /** Optional lucide icon component rendered above the title. */
  icon?: LucideIcon;
  /** If both provided, renders a primary action button. */
  actionLabel?: string;
  onAction?: () => void;
}
export function EmptyState(props: EmptyStateProps): JSX.Element;
```

```ts
// src/components/NumericInput.tsx
export interface NumericInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  /** Placeholder text; default "0". */
  placeholder?: string;
  /** Inclusive lower bound; values below are clamped on commit. */
  min?: number;
  /** Inclusive upper bound; values above are clamped on commit. */
  max?: number;
  /** Fractional digits to retain; default 0 for reps, pass 1/2 for weight. */
  decimals?: number;
  /** Trailing unit label, e.g. "kg", "lb", "sec". Optional. */
  unit?: string;
  /** Accessibility label. Required for a11y correctness. */
  accessibilityLabel: string;
  /** Disable input (e.g. completed set). Default false. */
  disabled?: boolean;
  /** Called with the committed value on blur / submit. */
  onCommit?: (value: number | null) => void;
  testID?: string;
}
export function NumericInput(props: NumericInputProps): JSX.Element;

/** Pure, exported helper used by NumericInput and unit-testable in isolation. */
export function sanitizeNumericInput(
  raw: string,
  opts: { decimals: number; min?: number; max?: number },
): number | null;
```

```ts
// src/components/SetLogger.tsx
import type { LoadType } from '../domain/types';

export interface SetLoggerProps {
  /** 0-based index of the set being edited; component renders as `Set ${setNumber + 1}`. */
  setNumber: number;
  weightKg: number | null;
  reps: number | null;
  rpe: number | null;
  completed: boolean;
  /** Drives the weight/reps column labels and increment semantics. */
  loadType: LoadType;
  /** True when the logged weight is per-side; surfaced as a "per side" hint. */
  isLoadPerSide: boolean;
  /** kg is canonical; this only affects the weight column's unit label. */
  unitLabel?: string; // default "kg"
  onChangeWeight: (value: number | null) => void;
  onChangeReps: (value: number | null) => void;
  /** Optional; RPE is hidden when omitted. */
  onChangeRpe?: (value: number | null) => void;
  /** Toggles set completion. Required. */
  onToggleComplete: () => void;
  disabled?: boolean;
  testID?: string;
}
export function SetLogger(props: SetLoggerProps): JSX.Element;
```

```ts
// src/components/WarningMessage.tsx
export type WarningSeverity = 'info' | 'warning' | 'error';

export interface WarningMessageProps {
  /** Defaults to 'warning'. */
  severity?: WarningSeverity;
  /** Optional bold lead line above the message. */
  title?: string;
  /** Display-only body copy. */
  message: string;
  /** Optional dismiss handler; renders a close affordance when provided. */
  onDismiss?: () => void;
  /** Optional CTA, e.g. "Adjust weekly volume". */
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
}
export function WarningMessage(props: WarningMessageProps): JSX.Element;
```

```ts
// src/components/index.ts
export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { NumericInput, sanitizeNumericInput } from './NumericInput';
export type { NumericInputProps } from './NumericInput';
export { SetLogger } from './SetLogger';
export type { SetLoggerProps } from './SetLogger';
export { WarningMessage } from './WarningMessage';
export type { WarningMessageProps, WarningSeverity } from './WarningMessage';
```

```ts
// src/db/transaction.ts
import type { SqlDatabase } from './sql';

/**
 * Run `work` inside a single atomic SQLite transaction on `db`.
 * - Delegates to the existing `SqlDatabase.transaction` port — do NOT reimplement BEGIN/COMMIT.
 * - Commits on normal return; rolls back and rethrows on throw.
 * - Returns whatever `work` returns.
 */
export function withTransaction<T>(
  db: SqlDatabase,
  work: (tx: SqlDatabase) => T,
): T;

/**
 * Convenience wrapper for a synchronous unit of work that must be deferred
 * (e.g. building statements before opening the tx). Kept to one signature so
 * repositories migrate incrementally.
 */
export function runAtomic<T>(
  db: SqlDatabase,
  work: () => T,
): T;

/**
 * Type guard used by repository code and tests to assert a callback received
 * a live transactional handle.
 */
export function isTransactional(db: SqlDatabase): boolean;
```

> BACKEND IMPLEMENTATION NOTE: `withTransaction` / `runAtomic` MUST delegate to the **existing** transaction facility exposed by the `SqlDatabase` port in `src/db/sql.ts` (and provided by both `db/adapters/betterSqlite3.ts` and `db/adapters/expoSqlite.ts`). Do NOT hand-roll `BEGIN` / `COMMIT` / `ROLLBACK` SQL and do NOT add a new connection API. If `SqlDatabase.transaction` is not already present with a compatible signature, stop and record the gap in a `NEEDS CONTEXT` note rather than inventing a port.

### 2.3 NEGATIVE CONSTRAINTS

- **FORBIDDEN IMPORTS:** `@expo/vector-icons`, `date-fns`. Any icon must come from `lucide-react-native`.
- **FORBIDDEN TOKEN PATTERN:** a capitalized `Colors.*` accessor (e.g. `Colors.gray[500]`, `Colors.dark.border`, `Colors.primary`). The ONLY permitted color access is lowercase `theme.colors.<token>` (see §2.4).
- **No new dependencies.** Do not edit `package.json`; do not import any library not already in the dependency list (`react`, `react-native`, `expo-router`, `expo-sqlite`, `react-native-svg`, `lucide-react-native`).
- **No `as` casts to silence row/enum typing.** (Consistent with the existing repository/mapper discipline.)
- **No mutation of protected files** (§2.1). Additive imports from `src/domain/types.ts` and `src/theme/**` ARE allowed.
- **No backend service, no network calls, no auth.** The app is local-only SQLite; do not introduce fetch/axios/AsyncStorage/state libraries.
- **No screen or route changes.** Do not touch `src/app/**`, and do not wire components into screens in this stage — this stage delivers primitives only.
- **No rewrite of existing files.** Repository edits must be minimal, additive `withTransaction` wraps around existing statement sequences; the observable SQL executed must not change.
- **No `default` exports** on any new component or helper.

### 2.4 PERMITTED TOKENS

- Colors: **only** `theme.colors.<token>` where `theme` is imported from `src/theme` (verify the exact export shape first — see NEEDS CONTEXT). Permitted token names are whatever `src/theme/colors.ts` actually defines; a reasonable expected set includes `background`, `surface`, `card`, `border`, `text`, `textMuted`, `primary`, `primaryText`, `danger`, `warning`, `success`, and a `white`/`black` if present.
- Spacing/typography: use the exported non-color tokens from `src/theme/index.ts` (e.g. `theme.spacing.*`, `theme.radius.*`, `theme.typography.*`) **only if they exist**. If only colors are exported, use inline numeric literals for spacing/radius and document why.
- Icons: `lucide-react-native` only. Suggested: `EmptyState` default → `Dumbbell` or `Inbox`; `WarningMessage` → `AlertTriangle` (warning/error) and `Info` (info); `SetLogger` → `Check` for the completion toggle, `X` if a clear affordance is needed. `WarningMessage.onDismiss` → `X`.

---

## 3. Per-file behavior spec

### 3.1 `NumericInput.tsx`
- Controlled numeric field. Renders a `TextInput` with `keyboardType="decimal-pad"` (or `"number-pad"` when `decimals === 0`).
- `sanitizeNumericInput(raw, opts)` is a pure function: strips every character except digits and at most one decimal separator (`.`), truncates fractional digits to `opts.decimals`, parses to `number`, returns `null` for empty/invalid input, and clamps to `[min, max]` when those are provided. It must never return `NaN`.
- On change: sanitize, keep a local string mirror so partial input like `"12."` is preserved for editing, and call `NumericInputProps.onChange` with the parsed value (`null` when the field is empty).
- On blur/submit: call `onCommit` with the final parsed value. Not required to fire if `onCommit` is omitted.
- When `disabled` is true, the field is non-editable and visually dimmed using `theme.colors.*` only.
- Unit label renders to the right of the field when `unit` is provided.

### 3.2 `EmptyState.tsx`
- Centered vertical stack: optional `icon` (rendered as a `lucide-react-native` component sized via a numeric literal), `title`, optional `message`, optional action.
- When both `actionLabel` and `onAction` are provided, render a `Pressable` styled with `theme.colors.primary` (text on `theme.colors.primaryText` or the theme's inverse token). Otherwise render no button.
- Must be usable full-screen (flex: 1, centered) or embedded; expose no layout props — parent sizes via `style` passed through `View` props is **not** in this contract, so keep the container `flex: 1` with `justifyContent: 'center'`.

### 3.3 `SetLogger.tsx`
- A single horizontal row: set index label (`Set ${setNumber + 1}`), weight cell (`NumericInput`, `decimals` = 1 or 2, `unit = unitLabel`), reps cell (`NumericInput`, `decimals: 0`), optional RPE cell (`NumericInput`, `decimals: 1`, `min: 1`, `max: 10`), and a completion toggle (`Pressable` showing a `Check` icon, tinted with `theme.colors.success` when `completed`, `theme.colors.border`/`theme.colors.textMuted` when not).
- When `loadType === 'duration'` the reps cell's `unit` becomes `"sec"` and its accessibility label reads "Seconds" — the value still occupies the `reps` field (per the domain invariant that duration stores seconds in `reps`).
- When `isLoadPerSide === true`, render a compact "per side" hint next to the weight cell (text only, `theme.colors.textMuted`).
- When `loadType === 'assisted'`, annotate the weight cell with an "assist" hint so the UI communicates that lower is stronger. Do not invert the stored value — the value is written through unchanged.
- `onChangeRpe` is required for the RPE cell to render; when omitted, the row collapses to weight/reps/toggle with no blank column.
- All callbacks fire with `null` when a field is cleared.

### 3.4 `WarningMessage.tsx`
- Card: full-width, padded, rounded with the theme radius, background tinted per severity, 3px-ish left accent bar using the severity color.
- Severity → color mapping must resolve through `theme.colors.*` (e.g. `warning` → `theme.colors.warning`, `error` → `theme.colors.danger`, `info` → `theme.colors.primary`). Never hardcode hex.
- Leading lucide icon per severity; optional `title` in a bold style; `message` body in muted text.
- `onDismiss` renders a `Pressable` close (`X`) affordance at the trailing edge; must include an `accessibilityLabel`.
- `actionLabel` + `onAction` render a text CTA below the message.
- This component takes *display strings*, not `PlanWarning` objects. Callers (a later track) map `PlanWarning.kind` → `severity` + copy; do **not** import from `src/generator/warnings.ts` here.

### 3.5 `src/db/transaction.ts`
- `withTransaction(db, work)` calls the port's transaction method and returns `work`'s result. On throw it must roll back (the port owns rollback) and rethrow the original error unchanged (do not wrap in a new error type).
- `runAtomic(db, work)` is a convenience for callers that build their statements lazily; it must also be atomic.
- `isTransactional(db)` returns a boolean indicating whether `db` advertises transaction support (used by tests and defensive call sites).
- Must not manage connection lifecycle, must not open/close the DB, must not alter PRAGMA state.

### 3.6 Repository wiring (minimal)
- In `sessionRepository.ts` and `programRepository.ts`, wrap the *existing* multi-statement write bodies in `withTransaction(this.db, (tx) => { ... })`, replacing the inner `this.db` references with `tx` inside the closure. No SQL changes, no signature changes, no behavior change on the happy path. `find*` / `list*` reads are out of scope and must not be wrapped.
- If any repository method is already atomic through the port, leave it as-is rather than double-wrapping.

---

## 4. Acceptance criteria (mapped to the prompt)

1. This file (`pipeline/spec.md`) is the immutable contract; the pillar rules in §2.3 are binding. *(Planner → `contract.md` is emitted downstream from this spec.)*
2. Frontend delivers `EmptyState`, `NumericInput`, `SetLogger`, `WarningMessage`, `components/index.ts`; Backend delivers `db/transaction.ts` and the minimal repository wraps.
3. Tester records execution evidence in `.evidence/tester_verification.json`, including the exact `npm test` and `npm run ts:check` output, plus a check that no forbidden import/token string appears in the new files.
4. Reviewer verifies artifacts on disk against this spec and issues `APPROVE` when all four pillars hold.

### Verification checklist the Tester must evidence
- `npx tsc --noEmit` (`npm run ts:check`) exits 0 under strict mode.
- `npm test` passes with the new `src/db/transaction.test.ts` included; the existing 237 tests remain green.
- `transaction.test.ts` proves: success commits and returns the value; a throw rolls back and rethrows; a rollback leaves no partial rows.
- Grep over `src/components/**` finds zero occurrences of `@expo/vector-icons`, `date-fns`, and zero matches for the capitalized `Colors.` token pattern.
- `git status` (or the changes log) confirms no protected file in §2.1 was modified.

---

## 5. Non-goals (explicitly out of scope)

- Wiring any of these components into `src/app/**` screens.
- Building the onboarding, Today's Workout, logging, or history screens.
- Choosing or adding a state-management library.
- Making `PlanWarning` → `WarningMessage` mapping (a later track owns that).
- Any change to generator, domain, data, migrations, adapters, or context.

**BACKEND TASK:** Limited to `src/db/transaction.ts` (+ test) and the atomic-transaction wiring in `sessionRepository.ts` / `programRepository.ts` described in §2.1 and §3.5–3.6. No server, no API, no new dependency. If the `SqlDatabase` port lacks a usable transaction primitive, do not invent one — report it under NEEDS CONTEXT.

---

## 6. NEEDS CONTEXT

The following files were not supplied in the prompt and must be read on disk by the implementing agents before writing code. They are listed so no agent guesses:

1. **`src/theme/colors.ts` and `src/theme/index.ts`** — the exact set of exported tokens and the imported symbol name (`theme` vs. named `colors`). Components must reference only tokens that actually exist. If the export is a bare `colors` object rather than a `theme` wrapper, use the lowercased property access that matches the file (`colors.primary`), never `Colors.primary`.
2. **`src/db/sql.ts`** — the exact `SqlDatabase` interface, specifically whether it exposes a `transaction` method, its signature, and whether operations are synchronous. `withTransaction` MUST delegate to whatever is there; do not add a new port or a new adapter.
3. **`src/domain/types.ts`** — confirm the exported names `LoadType` and `MuscleGroup` used in the prop types above (they are referenced by the codebase already; verify only the import path).
4. **`src/db/repositories/sessionRepository.ts` and `programRepository.ts`** — the actual method bodies and their current use of `this.db`, so the transaction wraps are surgical and no SQL changes.
5. **`src/contexts/DatabaseContext.tsx`** — read-only, to confirm the runtime `SqlDatabase` instance shape that `withTransaction` receives; do not modify it.
6. **`jest.config.js` / `tsconfig.test.json`** — confirm the test glob picks up `src/db/transaction.test.ts` and that component `.tsx` files are within the tsconfig `include` for the strict check.

If any of items 1–2 contradict the signatures in §2.2, the on-disk contract wins and the implementing agent must adapt the component/helper internals accordingly while preserving the *names and shapes* declared here (so downstream tracks can code against a stable surface).