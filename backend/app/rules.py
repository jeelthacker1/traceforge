import hashlib
import os
from datetime import timedelta

from sqlalchemy import select

from .db import Detection, Event, Incident, IncidentEvent, Rule, now

BASELINE = [['gateway', 'auth'], ['gateway', 'orders'], ['orders', 'inventory'], ['orders', 'payments']]
DEFAULTS = {
    'login_failures': {'name': 'Excessive login failures', 'threshold': 5, 'severity': 'high', 'required': ['account', 'attributes.outcome'], 'limitations': 'Mistyped credentials and account recovery can trigger this rule.'},
    'password_spray': {'name': 'Password spraying indicators', 'threshold': 5, 'severity': 'high', 'required': ['source', 'account', 'attributes.outcome'], 'limitations': 'Shared NAT gateways can combine unrelated users.'},
    'privileged_access': {'name': 'Unexpected administrative access', 'threshold': 3, 'severity': 'high', 'required': ['source', 'attributes.path', 'attributes.authorized'], 'limitations': 'Requires explicit authorization telemetry; absent authorization is unknown.'},
    'error_spike': {'name': 'API error spike', 'threshold': 0.5, 'severity': 'medium', 'required': ['attributes.status'], 'limitations': 'Operational failures are not proof of malicious activity. Requires 10 baseline and 10 current requests.'},
    'request_frequency': {'name': 'Suspicious request frequency', 'threshold': 120, 'severity': 'medium', 'required': ['source'], 'limitations': 'Legitimate traffic surges can trigger a rate indicator; no malicious intent is inferred.'},
    'unexpected_dependency': {'name': 'Unexpected service communication', 'threshold': 1, 'severity': 'medium', 'required': ['trace_id', 'span_id', 'parent_span_id'], 'limitations': 'Configuration changes may introduce legitimate new paths. Missing parents are unknown.'},
}


def seed_rules(db):
    for key, config in DEFAULTS.items():
        if not db.get(Rule, key):
            db.add(Rule(id=key, config={'enabled': True, 'window_seconds': 60, 'suppressed_services': [], 'allowed_edges': BASELINE, **config}))


def request(e):
    return e.kind == 'request' or (e.kind == 'span' and e.content['attributes'].get('span_kind') == 2)


def parent_edges(events):
    spans = {(e.origin, e.trace_id, e.span_id): e for e in events if e.trace_id and e.span_id}
    return [(spans[(e.origin, e.trace_id, e.parent_span_id)], e) for e in events
            if e.trace_id and e.parent_span_id and (e.origin, e.trace_id, e.parent_span_id) in spans
            and spans[(e.origin, e.trace_id, e.parent_span_id)].service != e.service]


def detect(db, event):
    results = []
    for rule in db.scalars(select(Rule)):
        cfg = rule.config
        if not cfg['enabled'] or event.service in cfg.get('suppressed_services', []):
            continue
        seconds = cfg['window_seconds']
        start = event.timestamp - timedelta(seconds=seconds)
        rows = list(db.scalars(select(Event).where(Event.timestamp >= start, Event.timestamp <= event.timestamp, Event.origin == event.origin)))
        attrs = event.content['attributes']
        evidence = []
        group = event.service
        observed = None
        if rule.id == 'login_failures' and event.kind == 'auth' and event.account and attrs.get('outcome') == 'failure':
            evidence = [e for e in rows if e.kind == 'auth' and e.account == event.account and e.service == event.service and e.content['attributes'].get('outcome') == 'failure']
            group = event.account
        elif rule.id == 'password_spray' and event.kind == 'auth' and event.source and attrs.get('outcome') == 'failure':
            evidence = [e for e in rows if e.kind == 'auth' and e.source == event.source and e.account and e.content['attributes'].get('outcome') == 'failure']
            observed = len({e.account for e in evidence})
            group = event.source
        elif rule.id == 'privileged_access' and request(event) and event.source and attrs.get('path', '').startswith('/admin') and attrs.get('authorized') is False:
            evidence = [e for e in rows if request(e) and e.source == event.source and e.content['attributes'].get('path', '').startswith('/admin') and e.content['attributes'].get('authorized') is False]
            group = event.source
        elif rule.id == 'request_frequency' and request(event) and event.source:
            evidence = [e for e in rows if request(e) and e.source == event.source and e.service == event.service]
            group = event.source
        elif rule.id == 'error_spike' and request(event):
            current = [e for e in rows if e.service == event.service and request(e) and 'status' in e.content['attributes']]
            base = [e for e in db.scalars(select(Event).where(Event.timestamp >= start - timedelta(seconds=seconds * 5), Event.timestamp < start, Event.service == event.service, Event.origin == event.origin)) if request(e) and 'status' in e.content['attributes']]
            if len(base) >= 10 and len(current) >= 10:
                rate = sum(e.content['attributes']['status'] >= 500 for e in current) / len(current)
                baseline = sum(e.content['attributes']['status'] >= 500 for e in base) / len(base)
                if rate >= cfg['threshold'] and rate >= baseline + 0.3:
                    evidence, observed = base + current, rate
        elif rule.id == 'unexpected_dependency' and event.trace_id:
            trace = list(db.scalars(select(Event).where(Event.trace_id == event.trace_id, Event.origin == event.origin)))
            for parent, child in parent_edges(trace):
                if [parent.service, child.service] not in cfg['allowed_edges']:
                    evidence, group = [parent, child], f'{parent.service}>{child.service}'
                    break
        if observed is None:
            observed = len(evidence)
        if not evidence or observed < cfg['threshold']:
            continue
        # Sliding cooldown avoids alerts duplicated at fixed bucket boundaries.
        fingerprint = hashlib.sha256(f'{rule.id}:{event.origin}:{group}'.encode()).hexdigest()
        recent = db.scalars(select(Detection).where(Detection.rule_id == rule.id, Detection.timestamp >= start, Detection.timestamp <= event.timestamp)).all()
        if any(d.detail.get('fingerprint') == fingerprint for d in recent):
            continue
        key = hashlib.sha256(f'{fingerprint}:{event.id}'.encode()).hexdigest()[:24]
        result = Detection(id=key, rule_id=rule.id, timestamp=event.timestamp, severity=cfg['severity'],
                           evidence=[e.id for e in evidence], detail={'name': cfg['name'], 'observed': observed, 'threshold': cfg['threshold'], 'window_seconds': seconds, 'fingerprint': fingerprint, 'limitations': cfg['limitations'], 'origin': event.origin, 'processed_at': now().isoformat()}, state={'acknowledged': False, 'assignee': None, 'resolution': None})
        db.add(result)
        db.flush()
        correlate(db, result, event)
        results.append(result)
    event.processed = True
    return results


def correlate(db, detection, event):
    # Shared trace, explicit request ID, or account: never proximity or service alone.
    identity = ('trace:' + event.trace_id if event.trace_id else
                'request:' + event.content['request_id'] if event.content.get('request_id') else
                'account:' + event.account if event.account else 'detection:' + detection.id)
    key = event.origin + ':' + identity
    window = int(os.getenv('CORRELATION_WINDOW_SECONDS', '300'))
    incident = db.scalar(select(Incident).where(Incident.correlation_key == key, Incident.end >= event.timestamp - timedelta(seconds=window), Incident.start <= event.timestamp + timedelta(seconds=window)).order_by(Incident.end.desc()))
    if not incident:
        incident = Incident(id='inc-' + detection.id, correlation_key=key, start=event.timestamp, end=event.timestamp, detection_ids=[], limitations='Shared identifiers and an explicit time window establish association, not causation. Missing trace parents and uncollected events remain unknown.')
        db.add(incident)
        db.flush()
    incident.detection_ids = list(dict.fromkeys(incident.detection_ids + [detection.id]))
    related = list(detection.evidence)
    if event.trace_id:
        related += list(db.scalars(select(Event.id).where(Event.trace_id == event.trace_id, Event.origin == event.origin, Event.timestamp >= event.timestamp - timedelta(seconds=window), Event.timestamp <= event.timestamp + timedelta(seconds=window))))
    for eid in set(related):
        if not db.get(IncidentEvent, (incident.id, eid)):
            db.add(IncidentEvent(incident_id=incident.id, event_id=eid))
        item = db.get(Event, eid)
        # SQLite strips timezone offsets; compare UTC wall times consistently.
        incident.start = min(incident.start.replace(tzinfo=None), item.timestamp.replace(tzinfo=None))
        incident.end = max(incident.end.replace(tzinfo=None), item.timestamp.replace(tzinfo=None))


def enrich_incidents(db, event):
    if not event.trace_id:
        return
    window = timedelta(seconds=int(os.getenv('CORRELATION_WINDOW_SECONDS', '300')))
    for incident in db.scalars(select(Incident).where(Incident.correlation_key == event.origin + ':trace:' + event.trace_id, Incident.end >= event.timestamp - window, Incident.start <= event.timestamp + window)):
        if not db.get(IncidentEvent, (incident.id, event.id)):
            db.add(IncidentEvent(incident_id=incident.id, event_id=event.id))
