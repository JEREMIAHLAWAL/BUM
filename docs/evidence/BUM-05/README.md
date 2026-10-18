# BUM-05 verification entrypoints

Status: reopened; acceptance is pending. These scripts are evidence tooling, not the five-role implementation pipeline.

- `run_offline.py`: import gate followed by full offline tests, executable provenance and side-effect audit. Dirty diagnostic runs are never acceptance. Native/child-process fixture permissions must be explicitly reviewed; no blanket subprocess bypass.
- `run_preparation.py`: separate real isolated FinderShip preparation smoke, no dotenv/provider calls; requires explicit live mutation scope and performs owned cleanup/readback.
- `serve_readiness.py`: explicit operator-authorized BUM-local dotenv loading and one unchanged Planner invocation, then the unchanged real FastAPI console behind an external GET/path-only boundary. No pipeline worker or implementation stage is started. Standard provider SDK retries remain configured by production code. The probe report alone never declares console readiness.
- `verify_loaded.py`: independent loopback HTTP/PID/socket/version/project/artifact/read-only-boundary readback of that instance. Captures a historical readiness observation, not indefinite future service availability.
- `test_*.py`: bounded negative and harness-contract regressions. These are separate from the complete orchestrator suite and their counts must not be conflated.

`exact-head-results.json` is the historical, unaudited pre-review result retained from initial WIP. Its name is not proof. Do not use it for acceptance, independent sign-off, complete cleanup or loaded-console readiness.

`preservation-before.json` is the initial reference for approved role configuration, fifteen canonical sources and four transfer inputs. It does not prove preservation by itself. The coordinator additionally captured full tracked-file bytes, all five instruction hashes and 23,369 dependency file digests in scratch before new smoke work. Authorized work-status documentation changes are accounted for separately, not described as unchanged baseline status.

Final evidence must name the exact tested/reviewed SHA, runner hashes, actual counts and errors, cleanup readback, authorized documentation deltas, limitations, and publication SHA. A documentation-only successor commit is not the tested executable head unless re-executed explicitly.
