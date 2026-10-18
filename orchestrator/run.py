from pathlib import Path
from typing import Optional

import yaml

from orchestrator.providers import call_provider, validate_provider_options


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "agents.yaml"


def load_agents():
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    return config["agents"]


def load_instructions(instructions_path: str) -> str:
    path = ROOT / instructions_path

    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def run_agent(role: str, user_prompt: str, timeout: Optional[float] = None) -> str:
    agents = load_agents()

    if role not in agents:
        raise ValueError(f"Unknown agent role: {role}")

    agent = agents[role]
    options = {key: agent[key] for key in ("max_tokens", "reasoning") if key in agent}
    validated_reasoning = validate_provider_options(agent["provider"], agent["model"], **options)
    if "reasoning" in options:
        options["reasoning"] = validated_reasoning

    system_prompt = load_instructions(agent["instructions"])

    return call_provider(
        provider=agent["provider"],
        model=agent["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=timeout,
        **options,
    )


if __name__ == "__main__":
    from orchestrator.repo_tools import repo_tree

    spec_path = ROOT / "pipeline" / "spec.md"
    changes_path = ROOT / "pipeline" / "changes.md"
    handoff_path = ROOT / "pipeline" / "HANDOFF.md"

    spec = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    changes = changes_path.read_text(encoding="utf-8") if changes_path.exists() else ""
    handoff = handoff_path.read_text(encoding="utf-8") if handoff_path.exists() else ""
    tree = repo_tree(max_depth=3)

    shared_context = f"""
TRAYNE HANDOFF:
{handoff}

CURRENT SPEC:
{spec}

CURRENT CHANGES LOG:
{changes}

CURRENT REPO TREE:
{tree}
"""

    tests = {
        "frontend": "Confirm you can understand the provided Trayne repo context. Reply exactly: FRONTEND_REPO_CONTEXT_OK",
        "backend": "Confirm you can understand the provided Trayne repo context. Reply exactly: BACKEND_REPO_CONTEXT_OK",
        "tester": "Confirm you can understand the provided Trayne repo context. Reply exactly: TESTER_REPO_CONTEXT_OK",
        "reviewer": "Confirm you can understand the provided Trayne repo context. Reply exactly: REVIEWER_REPO_CONTEXT_OK",
    }

    for role, instruction in tests.items():
        print(f"\nTesting {role} repo context...")

        response = run_agent(
            role=role,
            user_prompt=f"""
{shared_context}

{instruction}

Do not propose changes.
Do not write code.
Do not run tests.
Do not review implementation.
This is a read-only context connection test.
""",
        )

        print(response)
