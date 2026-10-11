# Task: Fix Hardcoded Placeholder Model Name on Planner Stage Card (UI)

## Scope
Repo: `BUM` only. `agent-flow-ui` frontend. **Planner stage card only** —
this is a narrowed test fix; Frontend/Backend/Tester/Reviewer stage cards
are explicitly out of scope for this run and must not be touched.

## Problem
In the Web UI, the Planner stage card displays a model-name label (e.g.
"Gemini 2.5 Flash").

Observed behavior:
- On a **new run**, the Planner card renders with a stale/incorrect
  hardcoded placeholder model-name string.
- Once the Planner agent actually starts streaming output, the label
  **corrects itself** to the real model in use (confirmed via Agent Log,
  which correctly shows e.g. `google/gemini-2.5-flash -- openrouter`).
- On the **next new run**, the card resets back to the wrong hardcoded
  placeholder again, repeating the cycle.

The actual model selection/execution is correct — this is a
**display-only bug** on the Planner card: its model-name label is
initialized from a hardcoded default/placeholder value instead of the
live run's configured model, and only updates once streamed agent output
overwrites it.

## Required Behavior
1. Locate the frontend component rendering the Planner stage card in
   `agent-flow-ui` — search for the hardcoded model-name string (e.g.
   "Gemini 2.5 Flash" or similar) in that component's initial
   state/props/default values.
2. Identify where the *correct* model name is already available (the
   same run-config/manifest source used by the backend to actually
   invoke the model, or the value parsed from the agent log's first
   line, e.g. `google/gemini-2.5-flash -- openrouter`).
3. Change the Planner card's model-name label to initialize from that
   live run-config source on mount/run-start, not from a hardcoded
   default string.
4. Verify the label is correct from the very first render of a new run —
   no flash of wrong model name before correcting.
5. Do not change stage ordering, stage names/icons, queued/attempt
   counters, or any other card UI element — label source only.
6. Do **not** modify the Frontend, Backend, Tester, or Reviewer stage
   cards in this run, even if they share the same hardcoded-label
   pattern — this run is scoped to Planner only to validate the fix
   cheaply before extending it to the other stages in a follow-up run.

## 4-Pillar Guards
- Strict file isolation: only touch the Planner stage card component and
  the minimal state/prop plumbing needed to source the correct model
  name. Do not touch Planner/Dev/Tester/Reviewer backend logic, pipeline
  orchestration, or unrelated UI panels (Agent log, Tests & shell,
  Changes, Review tabs), and do not touch the other stage card
  components even if visually/structurally similar.
- No `Colors.*` token guard violations — do not introduce new color
  literals; reuse existing theme tokens if any styling touch is required.
- Verified exact repo signatures: inspect the actual current component
  props/state/types for the Planner stage card and run-config object
  before editing — do not assume field names.
- No `@expo/vector-icons` or `date-fns` introduced (N/A — this is the
  `agent-flow-ui` web frontend, not TRAYNE mobile, but the prohibition
  still applies if any icon/date utility is touched).

## Verification
- Start a new run and confirm the Planner card shows the correct model
  name immediately (no stale placeholder, no flash-then-correct).
- Confirm this holds across at least 2 consecutive new runs (catches the
  "resets on next run" part of the bug).
- Confirm Frontend/Backend/Tester/Reviewer stage cards are untouched and
  unaffected by the change (diff review should show only the Planner
  card's source path modified, plus any shared util it legitimately
  reuses).
- Evidence-on-disk: stream test/typecheck exit codes into `.evidence/`
  per existing pipeline convention.
