```markdown
## Pipeline Task: TRAYNE MVP Bug Triage & State Hardening (5-Tab End-to-End Loop)

This specification outlines the work required to perform a systematic bug triage, edge-case audit, and state hardening pass across the entire TRAYNE MVP core loop. The goal is to identify, test, and fix runtime defects, unhandled states, race conditions, and SQLite transaction inconsistencies.

### Frontend Task:

The Frontend work will involve auditing existing UI components, implementing new ones where necessary to handle edge cases (e.g., empty states), and ensuring data integrity and responsiveness across the user interface. This will involve significant interaction with the `SessionRepository` and `ProfileRepository` to ensure correct data display and persistence.

**Files to Create/Modify:**

*   **`src/app/onboarding.tsx`**:
    *   Implement validation for input fields (e.g., `displayName` not empty, reasonable ranges for `heightCm` and `bodyweightKg`).
    *   Add error handling and display for invalid inputs.
    *   Audit back-navigation behavior to ensure data is preserved or discarded appropriately.
    *   Ensure metric/imperial unit selection correctly updates the `OnboardingAnswers` and is propagated to `ProfileRepository.createFromOnboarding`.
*   **`src/app/(app)/profile.tsx`**:
    *   Implement validation for profile updates.
    *   Ensure metric/imperial unit toggle correctly updates the `ProfileRepository` and triggers UI re-renders where necessary.
    *   Handle cases where `heightCm` or `bodyweightKg` might be `null` or `0` for display.
*   **`src/app/(app)/program.tsx`**:
    *   Implement UI to allow users to modify `GenerateProgramInput` (e.g., days/week, equipment filters).
    *   Display `PlanWarning` messages in a user-friendly way. This will involve mapping `PlanWarning` kinds (`priority_uncovered`, `frequency_capped`, `capacity_trim`, `equipment_shortfall`) to distinct UI components or messages.
    *   Ensure that updating program parameters correctly triggers `generateProgram` and `ProgramRepository.create`.
    *   Implement UI to confirm program switch and handle the transition.
*   **`src/app/(app)/index.tsx` (Today's Workout view)**:
    *   Implement debouncing for rapid set logging to prevent duplicate entries and ensure atomic updates via `SessionRepository.logSet`.
    *   Implement UI to handle incomplete sessions (e.g., saving progress when navigating away, or a prompt on app close).
    *   Implement clamping for RPE input (1-10).
    *   Manage rest timer state, considering background suspension/resumption (this might require `expo-task-manager` for background tasks, but for MVP, focus on foreground behavior and saving state).
    *   Add placeholders/empty states for days with no exercises or no active program.
*   **`src/app/(app)/history.tsx`**:
    *   Implement UI to display a user's workout history.
    *   Add empty state rendering for users with no completed workouts.
    *   Implement pagination or infinite scroll for history display.
    *   Implement UI for deleting historical workout sessions, confirming the cascading cleanup of logged sets.
    *   Ensure correct display of weights (kg/lb) based on user preference.
*   **`src/app/(app)/analytics.tsx`**:
    *   Implement UI to display progress and PR analytics.
    *   Add empty state rendering for scenarios with insufficient data (e.g., no workouts logged for PRs).
    *   Implement logic to handle `0` reps or `0` weight when calculating 1RM (e.g., display "N/A" or "Not enough data" to avoid division by zero).
    *   Ensure PR badges update immediately upon new session completion without requiring a full app reload. This will likely involve re-fetching data or updating local state after a session is completed.
*   **`src/components/` (New components as needed)**:
    *   `src/components/EmptyState.tsx`: A reusable component for displaying empty states with calls to action.
    *   `src/components/WarningMessage.tsx`: A component to display `PlanWarning` messages.
    *   `src/components/NumericInput.tsx`: A controlled input component with validation for numbers, min/max values.
    *   `src/components/SetLogger.tsx`: Component responsible for logging sets, incorporating debouncing.
*   **`src/contexts/DatabaseContext.tsx`**:
    *   Ensure database interactions are robust and handle potential errors gracefully.
*   **`src/__tests__/`**:
    *   Add new unit/integration tests for UI components to cover edge cases, input validations, and state transitions identified during the audit. This will include tests for empty states, invalid inputs, and correct data display.

### Backend Task:

The Backend work will primarily focus on auditing and hardening the existing repository methods to ensure data integrity, atomicity, and consistent behavior under various conditions. This includes verifying existing transaction usage and adding additional checks where necessary.

**Files to Create/Modify:**

*   **`src/db/repositories/profileRepository.ts`**:
    *   Audit `createFromOnboarding` and `update` methods to ensure atomic transactions and robust error handling for edge-case inputs (e.g., extremely large/small numbers, invalid string lengths for `displayName`).
    *   Add checks to ensure `displayName` is not empty during creation/update.
*   **`src/db/repositories/programRepository.ts`**:
    *   Audit `create` and `activate` methods to ensure atomic transactions and prevent orphaned data if a program activation fails mid-process.
    *   Ensure `createNextVersion` correctly handles scenarios where no active program exists.
    *   Verify partial unique index on active program is properly enforced.
*   **`src/db/repositories/sessionRepository.ts`**:
    *   Audit `start`, `addExercise`, `logSet`, `updateSet`, `deleteSet`, and `complete` methods for transaction atomicity and race condition prevention. For `logSet`, ensure that concurrent calls (e.g., from rapid UI interaction) do not lead to data corruption or incorrect ordering.
    *   Verify `complete` method handles cases where a session might have no sets logged gracefully.
    *   Audit `personalRecord` and `weeklySetsByMuscle` to handle `0` reps/weight correctly without division-by-zero errors. Ensure `exerciseHistory` correctly handles exercises with no logged sets.
*   **`src/generator/volume.ts`**:
    *   Review `fitToWeeklyCapacity`, `trimToSessionBudget`, and `planSessionMovements` regarding the open decisions:
        *   **Volume floors vs. frequency:** No code changes unless SPEC is amended. If SPEC is amended, adjust logic to scale floors by frequency or implement the agreed-upon coverage reduction strategy.
        *   **`capacity_trim` warning:** Ensure the generator correctly flags this warning when day-level rounding occurs. No code change needed if current behavior is accepted.
        *   **Soft sets-per-movement:** No code change needed if this behavior is accepted. If a hard ceiling is specified, implement logic to enforce it and potentially add a new warning kind.
*   **`src/generator/warnings.ts`**:
    *   If a new warning kind is introduced (e.g., for hard sets-per-movement ceiling), update this file.
*   **`src/__tests__/`**:
    *   Add new integration tests for repository methods focusing on concurrency, transaction integrity, and edge-case data inputs (e.g., logging sets with `0` weight, updating non-existent sets, starting multiple sessions concurrently).
    *   Add tests for the `generator` modules to cover the accepted resolutions for the open decisions, particularly how warnings are generated under those conditions.

**Note on `src/db/repositories/` testing:** The existing repository tests are robust. New tests will extend this coverage to specifically target the identified bug triage dimensions (e.g., concurrent `logSet` calls, handling `null` values for optional profile fields, etc.).

### BACKEND TASK: None.

The "Backend" in this context refers to the data layer within the client-side application (SQLite and its repositories). No external server-side backend is involved.
```