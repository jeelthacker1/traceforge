# Three-minute demo

Before recording, configure `.env`, start `docker compose up --build`, sign in, and run:

```sh
docker compose run --rm workload python workload.py --count 60
```

## 0:00–0:35 — Observe real telemetry

Show Overview. Explain that event counts, error rates, latency, and pipeline lag come from stored data. Open Event explorer and point to `local` provenance. Inspect a span and identify its trace ID; show an event with missing correlation if one is present. Do not invent missing events for the demo.

## 0:35–1:00 — Follow service communication

Open Service graph. Trace gateway → orders → inventory/payments and gateway → auth when those edges have actually been observed. Click a service to inspect its events. Explain that a dependency is communication, not evidence of attacker movement.

## 1:00–1:30 — Trigger a controlled scenario

Open Scenario lab and run A. Show the explicit synthetic label and expected ground truth. Wait for ingestion/correlation workers. Open Incidents and explain the observed thresholds and evidence IDs. Acknowledge an alert or assign it to an analyst.

## 1:30–2:20 — Reconstruct the timeline

Open the incident's Security Time Machine. Scrub backward and forward, inspect an auth event, and play the timeline. Show historical service state and the preceding baseline. Note the confidence limitations and absence of a proven root cause. Change the incident to INVESTIGATING with a reason. Add a note and bookmark a selected incident event.

## 2:20–3:00 — Verify and preserve

Verify the evidence chain. Export JSON and PDF. Explain canonical hashing, missing-record detection, and the need for separately protected checkpoints. End by showing scenario E's benign traffic and its expected absence of detections under default rules.

If a worker or exporter fails, show the actual pipeline state instead of substituting mock results. The demo's credibility comes from the evidence, including its limitations.
