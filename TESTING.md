# Verification record

Verification is in progress. Do not interpret implementation presence or a CI workflow file as a passing result.

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

The authoring host does not currently have an available Linux Docker engine / WSL backend. Full-stack startup and browser end-to-end verification must therefore be confirmed in CI or on a Docker-capable machine. Browser automation also stopped because it could not verify the active browser URL. No fabricated screenshots or benchmark measurements are included.

## Benchmark method

`backend/benchmark.py` persists 10,000 explicitly synthetic events in a temporary SQLite database, verifies their chain, constructs the graph, processes a separate detection scenario, and queries the resulting incident. It records platform, Python version, CPU description, logical CPUs, elapsed time, and events/sec. It cleans up only its temporary database. Distributed OTLP/Redis throughput and browser graph-rendering performance are separate, unmeasured dimensions until explicitly run.
