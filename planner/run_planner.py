import os
from pathlib import Path
import anthropic

BASE_DIR = Path(__file__).resolve().parent.parent

instructions = (BASE_DIR / "planner" / "instructions.md").read_text()
handoff = (BASE_DIR / "pipeline" / "HANDOFF.md").read_text()
task = (BASE_DIR / "tasks" / "active" / "TEST_TASK.md").read_text()

client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"]
)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    system=instructions,
    messages=[
        {
            "role": "user",
            "content": f"""
PROJECT HANDOFF:
{handoff}

CURRENT TASK:
{task}

Create the development plan.
"""
        }
    ]
)

output = response.content[0].text

current_task_path = BASE_DIR / "pipeline" / "CURRENT_TASK.md"
current_task_path.write_text(
    f"""# Current Trayne Task

TASK:
{task}

PLANNER OUTPUT:
{output}

FRONTEND OUTPUT:
None

BACKEND OUTPUT:
None

TESTER OUTPUT:
None

REVIEWER OUTPUT:
None
"""
)

print(output)
