# Explainable detection engine

Rules are seeded into `detection_rules` and edited through an ADMIN-only endpoint. Analysts can inspect the rule catalog; VIEWER cannot mutate rules, alerts, incidents, or scenarios. All configuration changes are audited.

| ID | Required fields | Window and condition | Severity | Expected false positives |
| --- | --- | --- | --- | --- |
| login_failures | account, auth outcome, service | 5 failures in 60s | high | Forgotten credentials, recovery |
| password_spray | source, account, auth outcome | 5 distinct accounts in 60s | high | Shared NAT or test automation |
| privileged_access | source, request path, explicit authorized=false | 3 `/admin` requests in 60s | high | Misconfigured access controls |
| error_spike | request/server span, numeric HTTP status | ≥10 current + ≥10 preceding baseline observations; recent error rate ≥0.5 and ≥0.3 above baseline | medium | Outages and deployments |
| request_frequency | request/server span, source, service | 120 requests in 60s | medium | Legitimate concentrated surge |
| unexpected_dependency | trace/span/parent IDs | Observed edge absent from configured allowed edges | medium | New legitimate call paths |

Default values are configurable. Each result includes observed value, threshold, window, evidence IDs, origin, processing timestamp, and a limitations statement. Disabled rules and suppressed services do not generate results. Sliding-window fingerprint deduplication avoids a new alert just because the clock crosses a fixed bucket boundary.

Unacknowledged, unresolved alerts automatically escalate to high severity after the rule's configured response interval (default 900 seconds). Escalation persists and is audited; acknowledged or resolved alerts are excluded. `CORRELATION_KEYS` configures identifier priority (default `trace,request,account`) and `CORRELATION_WINDOW_SECONDS` controls the association window.

Synthetic and non-synthetic origins are evaluated independently. Rate indicators never label traffic as malicious by themselves. Scenario E spreads normal requests across clients and must not generate detections under default thresholds.

Error-spike baseline data ends before the current window. Latency statistical analysis separately holds out the newest sample, computes the preceding 60-observation rolling mean/std and EWMA, and requires at least 20 training samples with nonzero sample standard deviation for a Z-score. Its threshold is absolute Z > 3. These diagnostic scores are not probability estimates.

Known limitations: clocks can be inaccurate; source identifiers can be shared or spoofed by a compromised producer; late events outside an already evaluated window may require replay; correlated events establish association, not a root cause. One correlation worker is the supported deployment. Isolation Forest is not implemented because it is optional and meaningful model evaluation would require a representative training dataset.
