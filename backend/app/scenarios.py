import hashlib
from datetime import datetime, timedelta, timezone

from .schema import Telemetry

CATALOG = {
    'A': {'name': 'Repeated authentication failures', 'expected': ['login_failures', 'password_spray'], 'truth': 'Synthetic suspicious authentication', 'false_positives': 'Shared NAT and forgotten passwords', 'correlation': 'Shared account or trace within 300 seconds'},
    'B': {'name': 'Privileged API pattern', 'expected': ['privileged_access'], 'truth': 'Synthetic unauthorized administrative requests', 'false_positives': 'Incorrect permission configuration', 'correlation': 'Shared synthetic trace'},
    'C': {'name': 'Slowdown and errors', 'expected': ['error_spike'], 'truth': 'Synthetic operational failure; malicious intent unknown', 'false_positives': 'Deployments and dependency outages', 'correlation': 'Evidence supporting the error-rate comparison'},
    'D': {'name': 'Unusual service path', 'expected': ['unexpected_dependency'], 'truth': 'Synthetic unexpected dependency', 'false_positives': 'Legitimate architecture changes', 'correlation': 'Explicit parent-child trace relationship'},
    'E': {'name': 'Normal distributed traffic surge', 'expected': [], 'truth': 'Benign synthetic traffic', 'false_positives': 'Concentrated clients may trigger the configured rate rule', 'correlation': 'No incident expected'},
}


def scenario(code, run_id, start=None):
    start = start or datetime.now(timezone.utc) - timedelta(minutes=6)
    trace = hashlib.sha256(f'{code}:{run_id}'.encode()).hexdigest()[:32]
    items = []

    def add(i, **kwargs):
        base = dict(id=f'{run_id}:{code}:{i}', timestamp=start + timedelta(seconds=i), service='gateway', kind='request', origin='synthetic', trace_id=trace, source='scenario-client', attributes={'status': 200, 'latency_ms': 20})
        base.update(kwargs)
        items.append(Telemetry(**base).normalized())

    if code == 'A':
        for i in range(12):
            add(i, service='auth', kind='auth', account='demo-account' if i < 6 else f'demo-{i}', attributes={'outcome': 'failure'})
    elif code == 'B':
        for i in range(6):
            add(i, attributes={'path': '/admin/settings', 'authorized': False, 'status': 403})
    elif code == 'C':
        for i in range(30):
            add(i, service='orders', attributes={'status': 200, 'latency_ms': 20 + i % 7})
        for i in range(120, 140):
            add(i, service='orders', attributes={'status': 503, 'latency_ms': 900 + i})
    elif code == 'D':
        add(0, service='auth', kind='span', span_id='1' * 16, attributes={'span_kind': 3})
        add(1, service='payments', kind='span', span_id='2' * 16, parent_span_id='1' * 16, attributes={'span_kind': 2})
    elif code == 'E':
        for i in range(200):
            add(i, timestamp=start + timedelta(milliseconds=i * 100), source=f'normal-{i % 20}', trace_id=hashlib.sha256(f'{run_id}:{i}'.encode()).hexdigest()[:32])
    else:
        raise ValueError('Unknown scenario')
    return items
