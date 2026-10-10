# Trayne Agent Handoff Contracts

## Planner
Reads:
- HANDOFF.md
- CURRENT_TASK.md
- task file from tasks/active/

Writes:
- PLANNER OUTPUT in CURRENT_TASK.md

## Frontend
Reads:
- HANDOFF.md
- CURRENT_TASK.md

Writes:
- FRONTEND OUTPUT in CURRENT_TASK.md

## Backend
Reads:
- HANDOFF.md
- CURRENT_TASK.md

Writes:
- BACKEND OUTPUT in CURRENT_TASK.md

## Tester
Reads:
- HANDOFF.md
- CURRENT_TASK.md
- completed code changes

Writes:
- TESTER OUTPUT in CURRENT_TASK.md

## Reviewer
Reads:
- HANDOFF.md
- CURRENT_TASK.md
- tester results
- completed code changes

Writes:
- REVIEWER OUTPUT in CURRENT_TASK.md
