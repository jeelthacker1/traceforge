# Data pipeline

1. Local services emit OTLP spans, structured authentication logs, request counters, and duration histograms through OpenTelemetry SDKs.
2. Collector receivers accept protobuf; the exporter translates to OTLP JSON, with no compression at the API boundary.
3. Authentication, a 2 MB body limit, a 1,000-event batch limit, strict normalization, timezone validation, structured sensitive-field redaction, and 32 KB attribute limits protect ingestion.
4. A Redis Lua script atomically checks capacity and enqueues the entire accepted batch. Full queues return HTTP 429 with Retry-After; unavailable queues return 503. No unprocessed stream entry is trimmed.
5. The ingestion consumer reclaims entries idle for 30 seconds. Permanent malformed/collision records produce bounded dead-letter metadata. Database failures retain pending entries for retry.
6. PostgreSQL stores normalized content, ingestion timestamps, extracted indexes, and the evidence-chain link in a transaction. Duplicate normalized content is not appended again.
7. The correlation worker evaluates event-time windows and writes alerts/incidents before marking events processed. It publishes a refresh hint only after commit.

## Normalization contract

`timestamp` requires an explicit timezone and is stored in UTC. Missing timestamps are rejected, not substituted with ingestion time. Ingestion time is separately recorded. Service names are validated. Trace/span/parent IDs may be null; supplied IDs must have the correct hexadecimal length. IDs are lowercased. Each event has provenance `local`, `synthetic`, or `imported`.

Auth events contain outcome, pseudonymous account, and source identifiers without passwords. Logs need not include trace IDs. Metric events preserve the normalized OTLP data point and aggregation name; histogram sums are not mislabeled as individual request latencies in the dashboard.

Canonical event JSON uses sorted keys, compact separators, UTF-8, preserved non-ASCII text, and finite numbers. Hashes cover the redacted normalized content, not the raw network bytes. Original redacted content remains in `telemetry_events.content`.

## Backpressure and observability

Queue length, dead-letter count, worker heartbeats, unprocessed-event count, and the age of the oldest unprocessed ingestion are visible in Overview. Collector storage and Redis AOF volumes persist across container restarts. Graceful worker shutdown completes the current transaction; pending stream entries recover through the consumer group.

Notifications are best effort; dashboard refresh always reads authoritative API state. Event explorer returns the latest 200 matching events by default. Overview and graph views cap their sample at 10,000 and expose truncation.
