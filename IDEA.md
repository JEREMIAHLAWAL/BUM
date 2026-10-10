# IDEA: BUM (Autonomous Multi-Agent SWE Orchestrator)

## 1. High-Level Concept & Vision
* **Name:** `BUM`
* **Purpose:** A generalized, repo-agnostic multi-agent software engineering orchestrator designed to autonomously plan, code, test, repair, and review software features against any codebase.
* **Public Target:** Flagship open-source project on GitHub, built with public-grade code hygiene (zero hardcoded secrets, zero private repository coupling, clean CLI and Web UI ergonomics).
* **Lineage & Origin:** Born as the decoupled, generalized successor to `Trayne-Agents`.

---

## 2. Core Architecture & Differentiators

### A. Dynamic Manifest Engine (`bum.config.json`)
Target repositories define their own rules, contracts, and verification commands directly at the project root:
* **Rules & Guards:** Negative token guards (e.g. forbidden styles/modules), required packages, and strict write boundaries (`allowed_write_roots`).
* **Verification Contracts:** Dynamic test, typecheck, lint, and build execution (`typecheck_cmd`, `test_cmd`).
* **Context Extractors:** Automated AST type-skeleton and domain model extraction for lean prompt context.

### B. 5-Stage Resilient Lifecycle
1. **Planner:** Generates specifications, architectural contracts, and file boundaries from the target manifest.
2. **Frontend / Dev (Repair):** Authors code while strictly enforcing negative guards, boundary containment, and disk-evidence checks.
3. **Backend / Core:** Implements domain logic, services, and repositories.
4. **Tester / Verifier:** Executes dynamic validation commands with observation sanitization (preventing LLM context blowout from giant compiler errors).
5. **Reviewer:** Audits generated code diffs against disk logs and requirements with automated retry loops.

### C. Hardened Operator Ergonomics
* **SSE Real-Time Streaming:** Live log feeds and real-time active file modification badges.
* **Smart Stage Resume:** Resume failed pipelines directly from Tester/Repair rather than restarting from Planner.
* **Clone & Edit:** Re-run and tweak historical prompts with one click.
* **Zero-Breakage Duplication:** Isolated workspace on port `8900` with runs logged to `.bum/runs/`.

---

## 3. Technology Stack
* **Backend:** Python (FastAPI, Uvicorn, Pydantic, Subprocess Execution Harness)
* **Frontend:** React + TypeScript (Vite, Server-Sent Events, Tailwind/CSS Dashboard)
* **LLM Engine:** Provider-agnostic support (OpenRouter, DeepSeek, Anthropic, OpenAI, Ollama)
* **State Management:** JSONL Event Sourcing + Resumable on-disk state machine (`.bum/`)

---

## 4. Current Milestone & Next Steps
* [x] **Step 1:** Workspace Duplication & Isolation (Port `8900`, `.bum/runs/` state).
* [ ] **Step 2:** Manifest Engine Implementation (`bum.config.json` schema validator & discovery).
* [ ] **Step 3:** Decouple Pipeline Prompts from hardcoded domain assumptions.
* [ ] **Step 4:** Dual Verification (verify against sample repo and target codebases).
* [ ] **Step 5:** CLI Scaffolding (`bum init`) and Public GitHub Launch.
```
