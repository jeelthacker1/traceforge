# Verification record

Initial full-stack verification passed in [GitHub Actions run 44553119229](https://github.com/jeelthacker1/traceforge/actions/runs/44553119229), commit `4473263d667bf55a6977b326d60ed41a8a0c2de6`.

- Backend: **29 tests passed**, Ruff passed; one upstream Starlette TestClient deprecation warning.
- Frontend: production build and strict TypeScript checks passed locally and in Linux CI.
- Integration: all Compose services started, actual local service traffic was generated, and **1 Playwright end-to-end test passed**.
- The 10,000-event SQLite benchmark completed; output is committed in `docs/benchmark-results.json`.
- Real CI screenshots were downloaded and inspected. Follow-up changes add graph assertions, automatic escalation tests, and an HTTP/Redis/PostgreSQL pipeline benchmark; verification will be recorded after execution.

## Automated checks

Backend tests exercise timestamp normalization, redaction/log injection, event ID collisions, deterministic scenarios A–E, negative normal-traffic behavior, sliding windows, suppression, alert deduplication, origin isolation, late parents, hash tampering, missing sequence records, held-out statistics, authentication/session revocation, roles, CORS, oversize/malformed ingestion, backpressure, persistent mutations, incident reports, bookmarks, and rejected WebSockets.

The API tests use an isolated in-memory SQLite database and replace Redis calls with controlled test doubles. They are not a substitute for real stream integration.

The Docker Playwright workflow starts the complete stack, generates actual microservice traffic, checks local telemetry in the dashboard, runs synthetic scenario A, investigates an incident, advances its timeline, verifies evidence, and downloads the JSON report. Full integration is exercised by GitHub Actions when its run succeeds.

```sh
cd backend
pip install -r requirements.txt
ruff check .
pytest -q
python benchmark.py
cd ../web
npm ci
npm run build
npm run typecheck
# With the stack and real local traffic already running:
npm run test:e2e
```

## Host limitations

The authoring host lacks a Linux Docker/WSL backend. Full-stack startup and browser verification were performed successfully in Linux CI. Local browser automation stopped because it could not verify the active browser URL; screenshots come from the actual Playwright CI run. No fabricated screenshots or benchmark measurements are included.

## Benchmark method

`backend/benchmark.py` persists 10,000 explicitly synthetic events in a temporary SQLite database, verifies their chain, constructs the graph, processes a separate detection scenario, and queries the resulting incident. It records platform, Python version, CPU description, logical CPUs, elapsed time, and events/sec. It cleans up only its temporary database. Distributed OTLP/Redis throughput and browser graph-rendering performance are separate, unmeasured dimensions until explicitly run.
