from collections import defaultdict

import networkx as nx
import pandas as pd

from .rules import parent_edges, request


def graph(events):
    g = nx.DiGraph()
    for e in events:
        if e.service not in g:
            g.add_node(e.service, count=0, errors=0, latencies=[])
        n = g.nodes[e.service]
        n['count'] += 1
        n['errors'] += int(e.content['attributes'].get('status', 0) >= 500)
        if 'latency_ms' in e.content['attributes']:
            n['latencies'].append(e.content['attributes']['latency_ms'])
    for parent, child in parent_edges(events):
        previous = g.get_edge_data(parent.service, child.service, {}).get('count', 0)
        g.add_edge(parent.service, child.service, count=previous + 1, relationship='observed parent-child spans')
    nodes = [{'id': name, 'events': n['count'], 'error_rate': n['errors'] / n['count'], 'latency_ms': sum(n['latencies']) / len(n['latencies']) if n['latencies'] else None} for name, n in g.nodes(data=True)]
    span_keys = {(e.origin, e.trace_id, e.span_id) for e in events if e.trace_id and e.span_id}
    missing = sum(1 for e in events if e.parent_span_id and (e.origin, e.trace_id, e.parent_span_id) not in span_keys)
    return {'nodes': nodes, 'edges': [{'source': a, 'target': b, **d} for a, b, d in g.edges(data=True)], 'missing_parents': missing, 'limitations': 'Observed calls show communication, not attacker movement. Unobserved relationships are unknown.'}


def statistics(events):
    points = defaultdict(list)
    for e in events:
        if request(e) and 'latency_ms' in e.content['attributes']:
            points[e.service].append((e.timestamp, e.content['attributes']['latency_ms']))
    output = []
    for service, samples in points.items():
        series = pd.Series([p[1] for p in sorted(samples)], dtype=float)
        training = series.iloc[:-1].tail(60)
        observed = float(series.iloc[-1])
        mean = float(training.mean()) if len(training) else None
        std = float(training.std()) if len(training) >= 2 else None
        valid = len(training) >= 20 and std is not None and std > 0
        z = (observed - mean) / std if valid else None
        output.append({'service': service, 'samples': len(training), 'observed': observed, 'baseline': mean, 'std': std,
                       'ewma': float(training.ewm(alpha=0.3, adjust=False).mean().iloc[-1]) if len(training) else None,
                       'z_score': z, 'threshold': 3, 'anomalous': abs(z) > 3 if z is not None else None,
                       'reason': 'Held-out latest sample versus preceding observations' if valid else 'Insufficient training samples or zero variance; confidence unavailable'})
    return output
