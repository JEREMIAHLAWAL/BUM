# BUM-05 — completed bounded console-readiness handoff

October 18, 2026. **BUM-05 complete for the bounded acceptance gates below. FS-011 was not implemented or started.** A checked box is not evidence; use the exact commits, machine results, raw reports and review record.

## Exact tested/reviewed state

- **Final tested console/tooling commit:** `396ff0a4ff713714c1c4b963767dfb7d58e7bc1d`.
- **Exact independently reviewed tree:** `f9bf55d5716e3ead086dce3a85dc980439ca522d`.
- Combined review base: saved WIP `000e76afb8f2cef53f2639f3a299a633c80feb8f`; BUM-05 parent `14ea6a493266294db7014966286984080e58321c`. All saved WIP and BUM-01–04 history remain preserved on `fix/fs-011-console-compatibility`.
- Preparation executed at `37436552690ad3f308421805c326c32e8e7a12fb`; its production source and preparation runner are unchanged through the final tested commit. Genuine Planner invocation executed at `4ed2d1c8b500beb53d987d50c8cb5943ddb3e3c1`; the final console revalidated its captured response without a second credential load or provider invocation.
- This publication is a **documentation/evidence-only successor**, not a claim that its future SHA was already executed. The proof console was stopped before publication, so no stale loaded process is represented as current.

## Evidence and actual results

Primary records: [machine acceptance](evidence/BUM-05/FINAL_RESULTS.json), [independent review and findings/dispositions](evidence/BUM-05/INDEPENDENT_REVIEW.md), [evidence guide](evidence/BUM-05/README.md). Machine results index 26 compressed raw JSON reports with uncompressed/compressed hashes. Original failed reports remain intact.

| Gate | Observed result |
| --- | --- |
| Prerequisite import safety | **3 passed**, 0 failures/errors/skips. |
| Complete audited offline console suite | **188 passed across 31 modules**, 0 failures/errors/skips; no dirty executable inputs; exact tested HEAD above; before/after provenance unchanged. Full-suite unittest duration 86.279 seconds. |
| Audit/process boundary | **0 unexpected denials**, 569 allowed fixture records and 32 Python-child reports. Installed-hook, Git-policy and child-policy negatives intentionally denied 8, 8 and 4 cases respectively. Trusted native Git is not an OS security sandbox. |
| Separate harness contracts | **22 passed**; includes setup-failure retention/no full-suite load, missing/staged-added input rejection, API schema, read-only mutation denial, capture tamper/source drift/writable-grant rejection. |
| Independent combined review | Bounded static PASS plus exact-tree follow-ups. Reviewers did not perform the coordinator's tests or act as the configured FS Reviewer stage. |
| Real isolated FinderShip preparation | Frozen pnpm bootstrap; Node **v24.22.0**, pnpm **10.9.0**, pnpm-executed Node **v24.22.0**; actual typecheck and lint passed; dependency roots isolated from canonical directories. |
| Preparation cleanup | Initial runner **exited 1** because WinError 32 sharing locks outlasted bounded cleanup retries. Scoped recovery after ownership readback subsequently removed the exact path, registration and branch. Initial failure is not rewritten as a clean first pass. |
| Loaded real console | Independent PID/socket/session-header/HTTP checks passed for exact commit `396ff0a...`, active FinderShip project and manifest, five configured identities, artifact location, idle state, zero write authority and rejected mutation/secret-preview requests. |
| Full content preservation | All **15 canonical sources**, **four transfer inputs**, **five instruction files**, role config and **23,369 dependency files** unchanged. Of 76 tracked FinderShip files, only the explicitly authorized `docs/WORK_STATUS.md` changed. |

## Fixed blocking findings

Scratch-isolated prompt, provenance, event, cancellation and architecture fixtures; fail-closed provenance/auditing and setup-failure evidence; bounded Git/Python fixture children; complete deleted/index-added executable inventory; real API-schema verification; strict baseline role/version/project/manifest checks; resolved Windows command paths; read-only server boundary; and zero-authority readiness semantics.

Independent review also found a retained-run P1: duplicate run IDs could destroy an existing worktree before artifact rejection. Ownership/query preflight and atomic run-ID reservation now precede any creation or teardown. Four new tests cover retained state, errors, sibling preservation and public-wrapper cancellation/context cleanup. This was BUM infrastructure only, not FS-011 application implementation.

## Five roles and genuine planning evidence

The approved configuration SHA-256 remains `3c1f8032a3bcb0df09ec1c1ca98bf060c4dc792af9f0700b27cbf27c04abff4b`:

| Role | Provider | Model |
| --- | --- | --- |
| Planner | openrouter | deepseek/deepseek-v4.1-flash |
| Frontend | openrouter | anthropic/claude-sonnet-5.5 |
| Backend | openrouter | anthropic/claude-sonnet-5.5 |
| Tester | openrouter | deepseek/deepseek-v4.1-flash |
| Reviewer | anthropic | claude-sonnet-5 |

One founder-authorized unchanged Planner invocation returned a genuine 11,281-byte saved markdown artifact at `.bum/runs/run_bum05_readiness_20261018T182710Z_7e4474/pipeline/spec.md`; its exact bytes are published as `evidence/BUM-05/genuine-planner-output.md.gz` with hashes in the machine results. The prompt made every path proposed future ownership only. Production parsing correctly granted **zero** writable files. The first harness wrongly required a writable contract and failed; its report is retained.

The corrected read-only gate rejects writable grants rather than relaxing the production parser. Final mode `CAPTURE_REVALIDATION_READ_ONLY` hashes the actual report/artifact, verifies unchanged production code/instructions/identities, and records original call HEAD/PID/failure. It is **not a fresh live call, executable FS-011 contract or builder authorization**. Current-console identity was then proved independently over real HTTP. No second dotenv/provider invocation was used.

## Ownership, preservation and shutdown

Founder authorized scoped commits/pushes and removal only after inspection. Both old smoke IDs `run_bum05_smoke_20261018T163734Z_ac3245` and `run_bum05_smoke_20261018T164052Z_e5b0a4`, plus the new preparation ID `run_bum05_prep_20261018T181757Z_35da0a3839b442e2abc38527734cd399`, have absent physical paths, owning FinderShip registrations and exact branches. Other branches/registrations were restored. No unrelated cleanup was performed.

FinderShip's application/source checkpoint is preserved through authorized status-only successors to `18f0890b04a1f753cc1f2a036c46a5b48a790278`; interim correction `ff1094f8f22c51f846702bbb1cc2f6a6bf3b842e` is retained in history. Four untracked transfer inputs remain untracked and byte-identical. Canonical dependencies were content-hashed before and after the real smoke and read-only console proof.

The owned proof PID and listening socket are verified absent after shutdown. Browser preview did load FinderShip and the owned readiness artifact; intentional stream/history restrictions can produce Offline/Not configured/Queued labels, while main/default-model UI labels are not actual Git/config facts. Use the API/PID/Git/config evidence, not these labels, for this bounded result.

## Remaining work and limits

- **No BUM-05 acceptance blocker remains within this bounded scope.** Windows locks can still require explicit recovery; ID reservation failures can retain a slot; untrusted native/external races are not sandboxed.
- FS-011 implementation, its normal executable Planner contract, coordinator-owned dependencies, browser/mock/live cases, full manifest checks, independent implementation review and founder acceptance remain separate work. `pnpm run lint` smoke is **not** the unexecuted manifest `pnpm check` gate.
- No merge, deployment, live email, migration, service purchase, provider/model substitution, Hermes credential-store inspection or later FS task occurred. The external five-stage implementation pipeline did not run.
- Original unsupported completion claims and historical unaudited output remain explicitly superseded, not acceptance evidence.

## Ready-to-paste separate-chat kickoff

> Resume FinderShip FS-011 in a separate task only after reading freshly fetched GitHub `AGENTS.md` and `docs/WORK_STATUS.md`, BUM `docs/BUM-05_HANDOFF.md`, `docs/evidence/BUM-05/FINAL_RESULTS.json`, FinderShip `docs/FS-011_RESUME_TODO.md`, and the published brief/addendum/manifest. BUM's exact tested source is `396ff0a4ff713714c1c4b963767dfb7d58e7bc1d`; later evidence publication is documentation-only. Preserve all WIP, canonical sources, four transfer inputs and the five existing roles. Recheck current branches and ownership; obtain permission for new Git mutations. Start the existing console at the current verified revision and select FinderShip explicitly; do not reuse the zero-authority BUM readiness artifact as an executable contract. Use the founder's Planner → Frontend → Backend → Tester → Reviewer pipeline, resolve the normal contract and coordinator-owned integration gates before builders, and follow all FS-011 acceptance requirements. Do not merge, deploy, send live email, migrate or start FS-012.
