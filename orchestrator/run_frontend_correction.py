"""
Manual recovery utility for targeted Frontend corrections.
NOTE: This is a manual recovery utility and must not be automatically re-invoked
after the main pipeline reaches its retry limit (MAX_REVIEW_CYCLES_EXCEEDED).
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.run import run_agent
from orchestrator.repo_tools import (
    get_repo_root,
    repo_tree,
    read_file,
    write_file,
    delete_file,
    file_exists,
)
from orchestrator.command_tools import run_safe_command
from orchestrator.git_tools import run_safe_git_command
from orchestrator.pipeline import (
    get_shared_context,
    read_pipeline_file,
    write_pipeline_file,
    format_command_result,
    format_git_result,
    get_untracked_files_content,
    parse_and_apply_agent_file_operations,
    parse_reviewer_verdict,
)

def run_frontend_correction():
    print("=== TRAYNE PIPELINE: FRONTEND CORRECTION & VERIFICATION ===")
    
    spec = read_pipeline_file("spec.md")
    changes = read_pipeline_file("changes.md")
    shared_ctx = get_shared_context()
    untracked_contents = get_untracked_files_content()
    
    print("\n[1/3] FRONTEND CORRECTION STARTED", flush=True)
    open_db_import = "import { openAppDatabase } from '@/db/adapters/expoSqlite';"
    init_layer_import = "import { initializeDataLayer } from '@/db';"
    changes_text = str(changes)
    spec_text = str(spec)
    shared_text = str(shared_ctx)
    untracked_text = str(untracked_contents)

    fe_correction_prompt = (
        shared_text
        + "\n\nPLANNER SPEC:\n"
        + spec_text
        + "\n\nCURRENT IMPLEMENTATION CHANGES:\n"
        + changes_text
        + "\n\nUNTRACKED IMPLEMENTATION FILE CONTENTS:\n"
        + untracked_text
        + "\n\nCRITICAL ARCHITECTURAL CONTEXT & CODEBASE CONTRACTS:\n"
        + "1. EXPORTS FROM `@/db`:\n"
        + "   - Import directly from `@/db`:\n"
        + "     `import { initializeDataLayer, InitResult } from '@/db';`\n"
        + "   - Do NOT import from `@/db/repositories` (it does not exist).\n"
        + "2. DATABASE SETUP:\n"
        + "   - `import { openAppDatabase } from '@/db/adapters/expoSqlite';`\n"
        + "   - In `home.tsx` inside `useEffect(..., [])`:\n"
        + "     ```ts\n"
        + "     const db = await openAppDatabase();\n"
        + "     const repos = await initializeDataLayer(db);\n"
        + "     ```\n"
        + "   - NOTICE: `initializeDataLayer` MUST be `await`ed inside the async `loadWorkout` function.\n"
        + "3. DAY SELECTION LOGIC:\n"
        + "   - In Trayne, `ProgramDay` has `weekday: WeekdayIndex | null` (where 0=Sunday, 1=Monday, ..., 6=Saturday, or null for generic sequence) and `orderIndex: number`.\n"
        + "   - Resolve today's program day:\n"
        + "     ```ts\n"
        + "     const todayWeekday = new Date().getDay() as WeekdayIndex;\n"
        + "     // Check if there is a day explicitly scheduled for today's weekday:\n"
        + "     let programDay = activeProgram.days.find((d: ProgramDay) => d.weekday === todayWeekday);\n"
        + "     // If none matches by weekday, pick by current cycle index or fallback:\n"
        + "     if (!programDay && activeProgram.days.length > 0) {\n"
        + "       programDay = activeProgram.days[0];\n"
        + "     }\n"
        + "     ```\n"
        + "   - If `programDay` is found, display its details (`Day ${programDay.orderIndex + 1}: ${programDay.title}`).\n"
        + "   - If no program day matches, display 'No workout planned for today'.\n"
        + "4. DATA FLOW IN `loadWorkout`:\n"
        + "   ```ts\n"
        + "   const hasOnboarded = await repos.profiles.hasCompletedOnboarding();\n"
        + "   if (!hasOnboarded) {\n"
        + "     setError('Complete onboarding to get your first program');\n"
        + "     return;\n"
        + "   }\n"
        + "   const profile = await repos.profiles.find();\n"
        + "   if (!profile) {\n"
        + "     setError('Complete onboarding to get your first program');\n"
        + "     return;\n"
        + "   }\n"
        + "   const activeProgram = await repos.programs.findActive(profile.id);\n"
        + "   if (!activeProgram || activeProgram.days.length === 0) {\n"
        + "     setError('No active program found. Complete onboarding to get your first program.');\n"
        + "     return;\n"
        + "   }\n"
        + "   const daysList: readonly ProgramDay[] = activeProgram.days;\n"
        + "   const programDay: ProgramDay | undefined = daysList[0];\n"
        + "   if (!programDay) {\n"
        + "     setError('No workout planned for today');\n"
        + "     return;\n"
        + "   }\n"
        + "   setActiveProgramName(activeProgram.name);\n"
        + "   setDayTitle(`Day ${programDay.orderIndex + 1}: ${programDay.title}`);\n"
        + "   const exerciseIds: readonly string[] = programDay.slots.map((s: ProgramSlot) => s.exerciseId);\n"
        + "   const exerciseEntities: Exercise[] = await repos.exercises.findByIds(exerciseIds);\n"
        + "   const exercisesList = programDay.slots.map((slot: ProgramSlot) => {\n"
        + "     const ex = exerciseEntities.find((e: Exercise) => e.id === slot.exerciseId);\n"
        + "     return {\n"
        + "       name: ex ? ex.name : 'Exercise',\n"
        + "       sets: slot.targetSets,\n"
        + "       reps: `${slot.targetReps.min}-${slot.targetReps.max}`,\n"
        + "     };\n"
        + "   });\n"
        + "   setExercises(exercisesList);\n"
        + "   ```\n"
        + "   DO NOT write `days[0]` and assume it is defined without assigning to `const programDay = daysList[0]` and immediately checking `if (!programDay) return;`.\n"
        + "   ```\n"
        + "5. TYPES:\n"
        + "   - Import `Program`, `ProgramDay`, `ProgramSlot`, `Exercise`, `WeekdayIndex` from `@/domain/types`.\n"
        + "6. Write the full, clean files now using canonical syntax:\n"
        + "```write:src/app/(app)/home.tsx\n"
        + "<complete file contents here>\n"
        + "```\n"
        + "```write:src/app/(app)/_layout.tsx\n"
        + "<complete file contents here>\n"
        + "```\n"
    )
    t0 = time.time()
    fe_correction_res = run_agent("frontend", fe_correction_prompt)
    t_fe = time.time() - t0
    parse_and_apply_agent_file_operations(fe_correction_res, role="frontend")
    print(f"[1/3] FRONTEND CORRECTION COMPLETE ({t_fe:.2f}s)", flush=True)
    
    changes += f"\n\n## FRONTEND CORRECTION\n\n{fe_correction_res}"
    write_pipeline_file("changes.md", changes)
    
    # Run test commands
    print("\n[2/3] RUNNING SAFE TEST COMMANDS...", flush=True)
    test_commands = [
        ["npm", "run", "ts:check"],
        ["npm", "test"],
    ]
    command_results = []
    for cmd in test_commands:
        cmd_str = " ".join(cmd)
        print(f"Executing: {cmd_str} ...", flush=True)
        res = run_safe_command(cmd)
        res["timed_out"] = False
        command_results.append(res)
        print(f"  Command: {res['command']} | Return Code: {res['returncode']} | Timed Out: {res['timed_out']}", flush=True)
    
    command_outputs_formatted = "\n\n".join(format_command_result(r) for r in command_results)
    current_tree = repo_tree()
    
    # Safe Git inspection
    print("\n[2/3] RUNNING GIT INSPECTION...", flush=True)
    git_commands = [
        ["git", "status", "--short"],
        ["git", "diff", "--stat"],
        ["git", "diff", "--name-only"],
        ["git", "diff"],
        ["git", "diff", "HEAD"],
    ]
    git_results = []
    for gcmd in git_commands:
        gres = run_safe_git_command(gcmd)
        git_results.append(gres)
        print(f"  Command: {gres['command']} | Return Code: {gres['returncode']} | Timed Out: {gres['timed_out']}", flush=True)
    
    git_outputs_formatted = "\n\n".join(format_git_result(r) for r in git_results)
    untracked_contents = get_untracked_files_content()
    
    # Call Tester
    print("\n[2/3] TESTER EVALUATION STARTED...", flush=True)
    tester_prompt = f"""
TRAYNE REPOSITORY TREE AFTER IMPLEMENTATION:
{current_tree}

PLANNER SPEC:
{spec}

CHANGES (pipeline/changes.md):
{changes}

COMMAND EXECUTION RESULTS:
{command_outputs_formatted}

GIT INSPECTION RESULTS:
{git_outputs_formatted}

UNTRACKED IMPLEMENTATION FILE CONTENTS:
{untracked_contents}

IMPORTANT INSTRUCTIONS FOR TESTER:
- This is a RE-EVALUATION after Frontend correction.
- Files have been written to disk by Frontend.
- You do NOT have arbitrary shell access; the above commands were executed in a controlled sandbox by the orchestrator.
- Do NOT fabricate PASS.
- Clearly note the exact results of `npm run ts:check` and `npm test`.
- Compare actual implementation files against the Planner acceptance criteria.

Provide your evaluation using this exact structure:

STATUS: PASS / FAIL / UNVERIFIABLE
FINDINGS:
...
BLOCKERS:
...
"""
    t0 = time.time()
    tester_result = run_agent("tester", tester_prompt)
    t_tester = time.time() - t0
    print(f"[2/3] TESTER COMPLETE ({t_tester:.2f}s)", flush=True)
    print("\n=== TESTER REPORT ===")
    print(tester_result)
    
    # Call Reviewer
    print("\n[3/3] REVIEWER EVALUATION STARTED...", flush=True)
    reviewer_prompt = f"""
TRAYNE REPOSITORY TREE AFTER IMPLEMENTATION:
{current_tree}

PLANNER SPEC:
{spec}

CHANGES (pipeline/changes.md):
{changes}

TESTER REPORT:
{tester_result}

GIT INSPECTION RESULTS:
{git_outputs_formatted}

UNTRACKED IMPLEMENTATION FILE CONTENTS:
{untracked_contents}

IMPORTANT INSTRUCTIONS FOR REVIEWER:
- Review the corrected implementation changes made by Frontend.
- Output your machine-readable verdict at the VERY TOP:
VERDICT: APPROVE
or
VERDICT: CHANGES REQUIRED

- If CHANGES REQUIRED, also provide:
FRONTEND_FIX_REQUIRED: YES/NO
BACKEND_FIX_REQUIRED: YES/NO
DEPENDENCY_FIX_REQUIRED: YES/NO

- Followed by TASK, ISSUES, and REASON.
"""
    t0 = time.time()
    reviewer_result = run_agent("reviewer", reviewer_prompt)
    t_reviewer = time.time() - t0
    print(f"[3/3] REVIEWER COMPLETE ({t_reviewer:.2f}s)", flush=True)
    print("\n=== REVIEWER REPORT ===")
    print(reviewer_result)
    
    verdict_data = parse_reviewer_verdict(reviewer_result)
    print(f"\nFINAL VERDICT: {verdict_data['verdict']}")

if __name__ == "__main__":
    run_frontend_correction()
