# Security and evidence trust model

## Intended use

TraceForge is a local defensive demonstration and engineering portfolio. The workload generator uses a fixed internal gateway, bounded counts, and fictional accounts/orders/payments. It does not accept arbitrary targets. It is not a hardened multi-tenant SaaS deployment.

## Controls

- Argon2id password hashes; no plaintext password database columns.
- Random 256-bit opaque sessions stored as SHA-256 token hashes with eight-hour expiry; logout revokes server-side state.
- HttpOnly, SameSite=Strict session cookies. Secure cookies are configurable and required behind public HTTPS.
- ADMIN, SECURITY_ANALYST, VIEWER authorization on protected routes and every mutation.
- WebSockets validate both Origin and the session, then recheck session validity during connection lifetime.
- Exact CORS allowlist and mutation-origin checks; no wildcard credentialed CORS.
- Redis-backed login throttling; limiter failure rejects login rather than bypassing controls.
- Authenticated ingestion, strict event validation, body/batch/attribute limits, bounded buffering, and structured sensitive-field redaction.
- Structured JSON demonstration logs and control-character normalization prevent simple newline log injection.
- API and web host ports bind to loopback. Backend containers run as a non-root application user; Collector uses a writable private volume.
- `.env`, runtime evidence, dependencies, and databases are excluded from Git.

## Roles and visibility

All users belong to one shared workspace. VIEWER can inspect all its evidence and export reports. Analysts may change alerts, incident status, notes, bookmarks, and run safe scenarios. Only ADMIN can create users, edit rules, and generate checkpoints. This is explicit shared-workspace access, not per-user evidence isolation.

## Evidence integrity

For each accepted event, `digest = SHA256(previous_digest + "\n" + canonical_normalized_event)`. The genesis digest is 64 zeroes. Sequence continuity and content hashes are checked. Normalized evidence is never updated by an application endpoint.

An ordinary database administrator can replace records and their hashes, delete a suffix, or change audit records. Hash chains alone cannot rule this out. Optional HMAC-SHA256 checkpoints can be exported and retained separately. A checkpoint stored only in the same database is not an independent trust anchor. Use a separately protected signing key and external retention for stronger assurance. This implementation does not claim asymmetric signatures, WORM storage, trusted timestamps, or legal chain-of-custody certification.

Exports contain all chain records to make offline verification self-contained. They may therefore contain more than the selected incident's evidence. Protect exported files accordingly. JSON/PDF reporting separates recorded facts, hypotheses, unresolved questions, and recommendations.

## Privacy and retention

Structured password/token/cookie/authorization/email/secret keys are redacted recursively before persistence and hashing. Account and source identifiers should be pseudonymous. Free-form log messages may still contain sensitive text; producers must not emit personal data or secrets. Raw original bytes are not retained.

`RETENTION_DAYS` seeds a stored retention policy. The retention inspection command identifies expired evidence and unresolved incidents. Automatic deletion is deliberately not enabled because deleting arbitrary records breaks a continuous evidence chain and may remove incident evidence. Export and separately retain checkpoints before manually rotating the whole local dataset. Partitioned chain epochs and automatic archival/deletion remain a documented follow-up, rather than a false claim of automatic retention enforcement.

## Deployment requirements

Before any public deployment: TLS, secure cookies, narrow origins, protected internal networking, independent secrets, backups, external checkpoints, resource limits, monitoring, and an operational retention policy. Pin and update dependency versions after verification. Enable GitHub Dependabot/security scanning as appropriate. Never expose the demo services, database, Redis, or unauthenticated Collector receivers publicly.

Report security issues privately to the repository owner; do not upload live evidence or secrets in a public issue.
