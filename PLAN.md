# Implementation plan

Status: implementation underway. A phase is verified only when its checks have run.

1. Repository, database, authentication, Docker — implemented; runtime tests pending
2. Instrumented demonstration services — implemented; real-stack verification pending
3. OpenTelemetry ingestion and Redis processing — implemented; real-stack verification pending
4. Live dashboard and dependency graph — production build and TypeScript checks passed
5. Explainable detection rules — implemented; backend tests pending dependency installation
6. Incident correlation — implemented; backend tests pending
7. Security Time Machine — implemented; browser integration pending
8. Evidence integrity — implemented; backend tests pending
9. Statistical analysis and reporting — implemented; tests pending
10. Tests, security review, CI, documentation — in progress

Verification will include deterministic unit/integration tests, a frontend production build,
and Docker end-to-end checks when the local Docker daemon is available.

Recorded limits: this Windows host lacks an available Linux Docker/WSL backend;
the Compose integration suite will be run through GitHub Actions. Automated destructive
retention, distributed scale benchmarks, and optional Isolation Forest are not claimed complete.
