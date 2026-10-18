# BUM: Generalized Multi-Agent SWE Orchestrator

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![UI: React + Vite](https://img.shields.io/badge/UI-React%20%2B%20Vite-61dafb.svg)](https://vitejs.dev/)

**BUM** is a high-reliability, multi-agent software engineering orchestrator designed to plan, develop, test, and review complex software features across arbitrary repositories with rigorous verification gates.

---

## 🌟 Overview & Architecture

BUM orchestrates specialized LLM agent stages governed by dynamic project manifests (`bum.config.json`), strict file boundaries, negative token guards, AST type-skeleton extraction, and live SSE event streaming.

```
                              ┌────────────────────────┐
                              │  User Task / Prompt    │
                              └───────────┬────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │   Stage 0: Preflight & Baseline Gate  │
                      │   (Git clean check + Typecheck Gate)  │
                      └───────────────────┬───────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │   Stage 1: Architect / Planner        │
                      │   (Generates Spec & Architecture)     │
                      └───────────────────┬───────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │   Stage 2: Frontend & UI Engineer     │
                      │   (Components, Screens, Navigation)   │
                      └───────────────────┬───────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │   Stage 3: Backend & Domain Engineer  │
                      │   (Models, DB Repositories, APIs)     │
                      └───────────────────┬───────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │   Stage 4: Tester / Verification      │
                      │   (Typecheck, Tests, Coverage)        │
                      └──────────────┬────────────────────────┘
                                     │
                    ┌────────────────┴──────────────┐
              Fail  │                               │  Pass
         (Retry <= 3)                               │
                    ▼                               ▼
       ┌─────────────────────────┐    ┌───────────────────────────┐
       │ Repair & Fix Iteration  │    │ Stage 5: Reviewer Auditor │
       └─────────────────────────┘    └─────────────┬─────────────┘
                                                    │
                                                    ▼
                                      ┌───────────────────────────┐
                                      │ Final Human Gate & Commit │
                                      └───────────────────────────┘
```

---

## 🚀 Key Features

* **Dynamic Workspace Manifests (`bum.config.json`):** Zero code changes needed to support new tech stacks (React Native, Next.js, Python/FastAPI, Node/Express, Rust).
* **Multi-Pillar Negative Guards:** Enforces negative token rules, forbidden imports, and strictly authorized write roots.
* **Harness & Sanitization Layer:** Automatic AST type-skeleton extraction and terminal log observation pruning to protect LLM context windows from blowout.
* **Real-Time SSE Web UI:** Live streaming terminal logs, visual stage timers, cycle counters, active file modification badges, and smart copy buttons.
* **Smart Stage Resume:** Resume execution directly from failed verification stages (e.g., Tester/Repair) without restarting from Planner.
* **Clone & Edit Past Runs:** One-click task replay and prompt iteration from historical execution records.
* **Multi-Provider LLM Agnostic:** Seamless support for OpenRouter, Anthropic Claude, OpenAI, DeepSeek, and local Ollama instances.

---

## 🛠️ Quickstart

### 1. Prerequisites
* Python 3.10+
* Node.js 18+ and `npm`

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/JEREMIAHLAWAL/BUM.git
cd BUM

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Build Web UI assets
cd agent-flow-ui
npm install
npm run build
cd ..
```

### 3. Configure Environment
Copy the example environment template and add your API keys:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
OPENROUTER_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

### 4. Run the Control Room Server
```bash
python run_server.py
```
Open **`http://localhost:8900`** in your browser to access the control room.

---

## 📋 Workspace Manifest (`bum.config.json`)

To target any repository, place a `bum.config.json` in the root of that project:

### Example: React Native / Expo
```json
{
  "name": "Mobile Client",
  "project_type": "react-native-expo",
  "rules": {
    "forbidden_imports": ["@expo/vector-icons", "date-fns"],
    "required_packages": ["lucide-react-native", "expo-sqlite"],
    "forbidden_tokens": ["Colors."],
    "allowed_write_roots": ["src/", "assets/"],
    "prohibited_files": [".env", "package.json"]
  },
  "verification": {
    "typecheck_cmd": "npm run ts:check",
    "test_cmd": "npm test"
  },
  "context": {
    "type_skeleton_paths": ["src/domain/types.ts", "src/theme/colors.ts"]
  }
}
```

### Example: Python / FastAPI
```json
{
  "name": "Backend API",
  "project_type": "fastapi",
  "rules": {
    "forbidden_imports": ["flask", "django"],
    "required_packages": ["pydantic", "fastapi"],
    "allowed_write_roots": ["app/", "tests/"],
    "prohibited_files": [".env", "config/secrets.json"]
  },
  "verification": {
    "typecheck_cmd": "mypy app/",
    "test_cmd": "pytest -v",
    "lint_cmd": "ruff check"
  },
  "context": {
    "type_skeleton_paths": ["app/schemas.py", "app/models.py"]
  }
}
```

---

## 🧪 Testing & Verification

Run the offline orchestrator regression suite:
```bash
python -m unittest discover -s orchestrator -p "test_*.py"
```

Legacy provider/context/capability scripts are import-safe and expose explicit
`main()` entrypoints for manual use. Test discovery must not call live providers,
execute development commands, or mutate a project merely by importing a module.
`orchestrator.test_legacy_import_safety` enforces that boundary. Manual smoke tests
remain separate evidence and must target an explicitly selected disposable
workspace; they are not part of offline regression verification.

---

## 📄 License
MIT License. Created by Jeremiah Lawal.
