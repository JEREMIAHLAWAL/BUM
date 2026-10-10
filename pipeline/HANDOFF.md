# TRAYNE — Engineering Handoff Summary (as of 2026-08-23)

> Self-contained brief for splitting work across sessions/agents. Verified against the
> working tree: `npm test` → 237/237 passing, `npx tsc --noEmit` clean.

## Product
TRAYNE is a mobile workout tracking + adaptive lifting app. Positioning: "Strava for
weightlifting" with adaptive programming. Core loop: PLAN → TRAIN → LOG → ANALYZE →
IMPROVE → SHARE.

AI is invisible in the product and aggressive in the build: no LLM calls at runtime.
Program generation is deterministic TypeScript. Social feed, wearables, and the adaptive
overload engine are Phase 2+ and explicitly NOT implemented.

## Stack & constraints
- React Native / Expo (SDK 51), expo-router, TypeScript strict.
- SQLite, offline-first, local-only for MVP (no backend, no auth server).
- Testing: Jest + ts-jest running in plain Node against `better-sqlite3` `:memory:`.
  No simulator needed. Full suite runs in ~7s.
- Minimal dependencies. No state-management library chosen yet. No UI kit.
- Deps in use: `expo-sqlite`, `react-native-svg`, `lucide-react-native`.

## Repo layout
- Working tree: `CLAUDE/trayne/` — ALL implementation code goes here.
- Upstream GitHub repo `github/trayne-app` is read-only, still at its initial commit
  (App.tsx, theme.ts, a coarse `src/types/workout.ts` that is superseded). Paths in the
  working tree mirror upstream exactly so promotion is a straight file copy.
- Coordination docs live in `Collaboration/`: `SPEC.md` (contracts), `TASKS.md` (board),
  `REVIEW.md` (review gate), `ADR.md` (5 accepted ADRs).
- Product brief: `CLAUDE/docs/TRAYNE_PRODUCT_BRIEF.md`.

## Current status

### DONE and approved — Data layer + exercise catalog
`src/domain/`, `src/data/`, `src/db/` — 168 tests. Approved 2026-08-23.

- `domain/types.ts` (361 lines) — the single source of truth for all entities and enums:
  - `MuscleGroup` (10, per-muscle not per-region): chest, back, shoulders, biceps,
    triceps, quads, hamstrings, glutes, calves, core
  - `Equipment`, `MovementPattern`, `ExerciseRole` (compound | accessory | isolation),
    `LoadType` (weighted | bodyweight | assisted | duration), `TrainingGoal` (5),
    `ExperienceLevel` (3), `TrainingDaysPerWeek` (2|3|4|5|6), `FeedbackTag`, `WeightUnit`
  - Entities: `Exercise`, `UserProfile`, `OnboardingAnswers`, `Program`, `ProgramDay`,
    `ProgramSlot`, `WorkoutSession`, `SessionExercise`, `SetLog`, `SessionSummary`
- `domain/ids.ts` — ULID generation + `toSlug()`.
- `domain/units.ts` — kg is canonical everywhere; lb exists only at the UI boundary.
- `domain/errors.ts` — typed errors + `assert()` helper carrying a field name.
- `data/exercises.seed.ts` — 122 movements, fully tagged (primary/secondary muscles,
  equipment, pattern, role, unilateral, per-side loading, default rep range, default rest,
  smallest realistic load increment). Ids are stable slugs (`barbell-bench-press`);
  re-seeding UPSERTs. Renaming a shipped exercise is forbidden — it changes the slug and
  orphans logged sets; add-new + archive instead.
- `db/sql.ts` — `SqlDatabase` port (query / execute / transaction).
- `db/adapters/` — `expoSqlite.ts` (app runtime) and `betterSqlite3.ts` (tests/CI).
- `db/migrations.ts` — v1 = full MVP schema. Tables: `profile`, `exercises`, `programs`,
  `program_days`, `program_slots`, `sessions`, `session_feedback`, `session_exercises`,
  `set_logs`. `PRAGMA foreign_keys = ON`. CHECK constraints on every enum. Partial unique
  index enforcing exactly one active program per user. Case-insensitive unique index on
  exercise name.
- `db/mappers.ts` — validating row decoders (throws on bad enum values, not `as`).
- `db/repositories/` — four repositories:
  - `ProfileRepository`: find, requireCurrent, createFromOnboarding, update,
    hasCompletedOnboarding
  - `ExerciseRepository`: seed, findById/requireById/findByIds, list(filter),
    createCustom, setArchived, count
  - `ProgramRepository`: create(draft), findById, findActive/requireActive, listForUser,
    activate, createNextVersion, delete
  - `SessionRepository`: start, addExercise, logSet, updateSet, deleteSet, complete,
    replaceFeedback, findById, findInProgress, listHistory, exerciseHistory,
    personalRecord, weeklySetsByMuscle
- `db/index.ts` — composition root: `initializeDataLayer(db)` → migrate + seed + repos.

### DONE, code-complete, AWAITING REVIEW — Deterministic plan generator
`src/generator/` — suite now at 237/237 passing, `tsc --noEmit` clean.

Public API:
```ts
generateProgram(input: GenerateProgramInput, catalog: readonly Exercise[]): GeneratedProgram

interface GenerateProgramInput {
  userId: string; goal: TrainingGoal; experience: ExperienceLevel;
  daysPerWeek: TrainingDaysPerWeek;
  prioritizedMuscles: readonly MuscleGroup[];   // ordered, highest first, may be empty
  availableEquipment: readonly Equipment[];
}
interface GeneratedProgram {
  draft: DraftProgram;                          // feeds ProgramRepository.create() directly
  warnings: readonly PlanWarning[];
  weeklySetsByMuscle: Readonly<Partial<Record<MuscleGroup, number>>>;
}
```

Modules:
- `splits.ts` — frequency → split template (2d Full Body, 3d Full Body, 4d Upper/Lower,
  5d, 6d PPL). Priority muscles get a minimum training frequency of 2 days.
- `volume.ts` — weekly set allocation. Prioritized muscles 10–20 sets, maintenance 6–10.
  Session ceilings by experience level. `fitToWeeklyCapacity`, `trimToSessionBudget`,
  `planSessionMovements`. `MAX_EXERCISES_PER_DAY = 9`, `MAX_SETS_PER_MUSCLE_PER_SESSION = 9`.
- `selection.ts` — exercise picking: compounds first, movement-pattern variety, heavy
  axial budget of 1/day and never on consecutive calendar days.
- `equipment.ts` — equipment presets → concrete equipment sets.
- `prescription.ts` — deterministic rep ranges / rest by goal × role.
- `warnings.ts` — `PlanWarning` discriminated union.
- Indirect volume credit: a set credits its secondary muscles 0.5 sets, capped at half a
  muscle's budget, and never reduces a prioritized muscle's direct work.
- Tested via a full 75-permutation sweep (frequency × goal × experience).

## Open decisions blocking sign-off (3 divergences from SPEC §3)
1. **Volume floors are unsatisfiable at low frequency.** SPEC's 6-set maintenance floor
   × 10 muscles = 60 weekly sets, but 2 days/week at the beginner ceiling holds 40.
   Resolution taken: reduce *coverage*, not intensity — drop the lowest-value muscles'
   direct work entirely (calves, core, biceps, triceps first) so every muscle remaining
   in the plan is trained inside its SPEC band. Prioritized muscles are never dropped.
   Surfaced once as a `frequency_capped` warning with a `suggestedDaysPerWeek`.
   *Needs: approve coverage-reduction, or amend SPEC to scale floors by frequency.*
2. **`warnings` is a discriminated union, not `string[]`.** Four kinds:
   `priority_uncovered`, `frequency_capped`, `capacity_trim`, `equipment_shortfall`.
   Callers branch on `kind`; `message` is display-only. *Needs: confirm `capacity_trim`
   is acceptable on an otherwise healthy plan (day-level rounding can leave one session
   1–2 sets over ceiling even when the week fits).*
3. **Sets-per-movement is soft; movement count is hard.** `planSessionMovements` reserves
   the day's exercise budget up front and folds movements back when fan-outs
   over-subscribe it, so a dense session may prescribe 5 sets on a lead compound instead
   of dropping sets. Concentrating volume is honest; silently dropping it is not.
   *Needs: confirm soft sets-per-movement, or specify a hard ceiling — in which case
   overflow needs its own warning kind.*

## Not built yet (the actual remaining MVP work)
1. **Onboarding flow UI** — collect `OnboardingAnswers`, call
   `ProfileRepository.createFromOnboarding`, then `generateProgram` →
   `ProgramRepository.create`. Data layer is ready; zero UI exists.
2. **App shell: expo-router navigation + screen scaffolding.** Nothing exists. No
   navigator, no screens, no theme wiring, no state layer.
3. **Today's Workout view** — read active program, resolve today's `ProgramDay`, render
   slots.
4. **Fast logging UI** — the highest-friction, highest-value surface. `SessionRepository`
   (start / addExercise / logSet / updateSet / complete / replaceFeedback) is complete
   and tested; the UI is entirely unwritten.
5. **History & progress** — `listHistory`, `exerciseHistory`, `personalRecord`,
   `weeklySetsByMuscle` all exist; charts and screens do not.
6. **Warning surfacing** — decide how each `PlanWarning` kind renders to the user.
7. **State management choice** — not yet made. Nothing depends on it yet.

## Clean seams for parallel work
The data layer and generator are pure, dependency-free, and fully tested, so UI work can
be split without stepping on itself:
- **Track A — App shell + navigation + theme.** Sole owner of expo-router setup and the
  DB provider/context. Everything else blocks on this landing first.
- **Track B — Onboarding + plan generation screens.** Depends only on A + existing
  `OnboardingAnswers` / `generateProgram`.
- **Track C — Today's Workout + fast logging.** Depends on A. Largest UX surface.
  Owns `SessionRepository` consumption.
- **Track D — History / progress / charts.** Depends on A only. Read-only queries;
  no overlap with C.
- **Track E — Generator review + SPEC reconciliation.** Pure docs/decisions; no code
  conflict with A–D. Gates treating the generator's output contract as stable.

No two tracks touch the same files after A lands.

## Rules a contributor must know
- All implementation code goes in `CLAUDE/trayne/`. Never write outside it.
- kg is the only unit in storage or logic. lb is an input/display concern only.
- Exercises are referenced by id, never by name.
- Invariants live in the schema (CHECK constraints, FKs), not only in application code.
- Volume math accounts for how load is actually carried: a 30 kg dumbbell press moves
  60 kg (`isLoadPerSide`); a single-arm row does not double. Warmups, failed sets,
  assisted reps and timed holds are excluded from volume.
- `duration` loadType stores SECONDS in the `reps` field. `assisted` loadType logs the
  ASSISTANCE weight, so lower is stronger — a future progression engine must invert its
  comparison for these.
- `ON DELETE RESTRICT` on the exercise catalog, `ON DELETE SET NULL` on program
  associations. Deleting a template must never erase logged history.
- Prefer small targeted edits over rewriting files. Never index `node_modules`,
  lockfiles, or build output.

## Known spec drift (fix before generating code from SPEC.md alone)
`Collaboration/SPEC.md` §2 still shows older shapes than the code: `WorkoutProgram`
(code: `Program`), a `UserProfile` without `displayName`, and `weightKg` on the profile
(code: `OnboardingAnswers.bodyweightKg`). `domain/types.ts` is authoritative.

## Known environment friction
- The machine's global npm cache is root-owned and breaks `npm install`. Fix once with
  `sudo chown -R 501:20 ~/.npm`, or install with `--cache ./.npm-cache`.
- `node_modules/` is ~473 MB and should be excluded from the Syncthing folder rather than
  replicated to the Pi and Windows machines.

## Commands
```bash
npm test          # 237 tests, plain Node, no simulator
npm run ts:check  # tsc --noEmit, strict
```
