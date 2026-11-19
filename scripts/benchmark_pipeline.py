"""Measure the real local HTTP -> Redis -> PostgreSQL -> detector path; no external target option."""
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import platform
import time
import urllib.request
from uuid import uuid4

BASE = 'http://localhost:8000'
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, data=None, ingest=False):
    headers = {'Content-Type': 'application/json'}
    if ingest:
        headers['X-Ingest-Key'] = os.environ['INGEST_KEY']
    request = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    with client.open(request, timeout=60) as response:
        return json.load(response)


def wait_for(predicate, seconds=300):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.5)
    raise TimeoutError('The real pipeline did not meet the benchmark completion condition')


def main():
    call('/api/login', {'username': 'admin', 'password': os.environ['ADMIN_PASSWORD']})
    wait_for(lambda: call('/api/overview')['pending'] == 0)
    before = call('/api/overview')
    run_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    count = 10000
    started = time.perf_counter()
    for start in range(0, count, 500):
        events = [{'id': f'pipeline-benchmark:{run_id}:{i}', 'timestamp': timestamp, 'service': 'benchmark', 'kind': 'log', 'origin': 'synthetic', 'attributes': {'body': 'Benign throughput measurement', 'sequence': i}} for i in range(start, start + 500)]
        assert call('/api/ingest', events, ingest=True)['accepted'] == 500
    accepted_seconds = time.perf_counter() - started

    def drained():
        state = call('/api/overview')
        return state if state['total_events'] >= before['total_events'] + count and state['pending'] == 0 and state['pipeline']['queue'] == 0 else None

    after = wait_for(drained)
    processed_seconds = time.perf_counter() - started
    assert after['pipeline']['dead_letters'] == before['pipeline']['dead_letters']
    started = time.perf_counter()
    integrity = call('/api/evidence/verify')
    verify_seconds = time.perf_counter() - started
    assert integrity['valid'] and integrity['count'] >= count
    previous_alerts = {a['id'] for a in call('/api/alerts')}
    started = time.perf_counter()
    call('/api/scenarios/B', {})
    wait_for(lambda: any(a['id'] not in previous_alerts and a['rule_id'] == 'privileged_access' for a in call('/api/alerts')))
    alert_seconds = time.perf_counter() - started
    started = time.perf_counter()
    graph = call('/api/graph')
    graph_seconds = time.perf_counter() - started
    started = time.perf_counter()
    assert call('/api/incidents')
    incident_seconds = time.perf_counter() - started
    result = {'environment': {'os': platform.platform(), 'logical_cpus': os.cpu_count(), 'database': 'PostgreSQL in Docker Compose', 'transport': 'HTTP JSON, Redis Streams, separate ingestion and correlation workers'}, 'synthetic_events': count, 'http_acceptance_seconds': accepted_seconds, 'accepted_events_per_second': count / accepted_seconds, 'end_to_end_processing_seconds': processed_seconds, 'processed_events_per_second': count / processed_seconds, 'alert_observation_seconds': alert_seconds, 'chain_verification_seconds': verify_seconds, 'incident_query_seconds': incident_seconds, 'graph_api_seconds': graph_seconds, 'graph_nodes': len(graph['nodes']), 'graph_sample_truncated': graph.get('truncated'), 'limitations': 'One local CI run. Normal metric traffic may continue during measurement. Alert timing includes 0.5-second polling. This does not measure raw OTLP capacity or browser rendering.'}
    Path('pipeline-benchmark-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
