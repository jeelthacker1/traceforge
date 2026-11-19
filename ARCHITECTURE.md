# Architecture and design decisions

## Components

Next.js renders the analyst interface. FastAPI owns authentication, authorization, validation, queries, reports, and WebSocket delivery. PostgreSQL stores the investigation record. Redis Streams is the bounded ingestion queue; Redis pub/sub carries refresh notifications. The UI polls as a fallback, so missed notifications do not erase data.

The OpenTelemetry Collector accepts OTLP protobuf HTTP/gRPC inside the private Compose network. It batches, limits memory, and persists its outbound queue. The API accepts OTLP/HTTP JSON at `/v1/traces`, `/v1/logs`, and `/v1/metrics`; structured telemetry uses `/api/ingest`.

The ingestion worker serializes evidence-chain writes through a PostgreSQL transaction-scoped advisory lock. An event and its evidence link are committed together. Redis acknowledgment follows the commit. A crash between commit and acknowledgment causes safe replay, and normalized IDs make the write idempotent. An ID reused for different content is rejected and recorded as a dead-letter condition.

The correlation worker scans committed, unprocessed events ordered by event time. Detection output, incident membership, and processing state commit together. The supported deployment runs one correlation worker. Horizontal scaling requires stronger per-rule/window locking before production use.

## Database

Tables: users, roles, sessions, services, telemetry_events, traces, spans, metrics, detection_rules, detection_results, incidents, incident_events, investigations, evidence_records, evidence_checkpoints, audit_logs, retention_policies. Indexes cover event time, service, provenance, trace, account/source, processing state, severity, incident relationships, and correlation keys.

Alembic revision `0001` creates the initial schema. Further changes require new migrations, rather than editing the bootstrap revision after deployment. No API route edits normalized event content.

## Correlation

Incident identity is chosen from trace ID, request ID, account ID, or a detection-specific fallback, with origin included. A default 300-second window is configurable through `CORRELATION_WINDOW_SECONDS`. Service identity and time alone never merge incidents. Detection evidence is always attached. Late events with an existing incident trace are attached within the configured window.

Parent-child edges require matching trace ID, parent span ID, and provenance. They are observed communications, not proof of attacker movement. Time-machine service state is reconstructed from the selected prefix of the incident's immutable event timeline.

## Tradeoffs

- PostgreSQL is authoritative; Redis is transport, not the evidence store.
- Queries and reports are suitable for a portfolio/local deployment. Large evidence exports should move to asynchronous streaming jobs.
- SQLite is used for isolated tests and the persistence microbenchmark. It does not validate PostgreSQL advisory locks, Redis recovery, or collector behavior; the Compose CI job covers those integrations.
- The baseline dependency graph is configured, avoiding silent learning of suspicious traffic as normal.
- A shared demo codebase keeps instrumentation consistent while separate containers produce actual distributed calls.
