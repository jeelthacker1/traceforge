from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.analytics import graph, statistics
from app.db import Detection, Event, Evidence, Incident, IncidentEvent, Rule
from app.integrity import verify
from app.otlp import decode
from app.pipeline import persist
from app.rules import detect, enrich_incidents
from app.scenarios import CATALOG, scenario
from app.schema import Telemetry

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def process(db, items):
    rows = []
    for item in items:
        event, created = persist(db, item)
        if created:
            detect(db, event)
            enrich_incidents(db, event)
        db.flush()
        rows.append(event)
    return rows


def test_timezone_and_missing_timestamp():
    event = Telemetry(timestamp='2026-01-01T05:30:00+05:30', service='auth', kind='auth')
    assert event.normalized()['timestamp'] == '2026-01-01T00:00:00Z'
    with pytest.raises(ValidationError):
        Telemetry(timestamp='2026-01-01T00:00:00', service='auth', kind='auth')
    with pytest.raises(ValidationError):
        Telemetry(service='auth', kind='auth')


def test_redaction_and_log_injection():
    e = Telemetry(timestamp=START, service='auth', kind='log', attributes={'password': 'never store me', 'nested': {'api_token': 'secret'}, 'body': 'line1\nFORGED\rline2'})
    data = e.normalized()
    assert data['attributes']['password'] == '[REDACTED]'
    assert data['attributes']['nested']['api_token'] == '[REDACTED]'
    assert '\n' not in data['attributes']['body']
    with pytest.raises(ValidationError):
        Telemetry(timestamp=START, service='auth\nspoof', kind='log')


def test_idempotency_and_collision(db):
    item = scenario('A', 'dedup', START)[0]
    first, created = persist(db, item)
    assert created
    assert persist(db, item)[1] is False
    item['attributes']['outcome'] = 'success'
    with pytest.raises(ValueError):
        persist(db, item)
    assert len(list(db.scalars(select(Event)))) == 1
    assert verify(db)['valid']


@pytest.mark.parametrize('code', list(CATALOG))
def test_deterministic_scenarios(db, code):
    items = scenario(code, 'test', START)
    assert items == scenario(code, 'test', START)
    process(db, items)
    detections = list(db.scalars(select(Detection)))
    assert {d.rule_id for d in detections} == set(CATALOG[code]['expected'])
    assert all(db.get(Event, eid) for d in detections for eid in d.evidence)
    if code == 'E':
        assert not list(db.scalars(select(Incident)))
    else:
        assert len(list(db.scalars(select(Incident)))) == 1


def test_sliding_window_boundary(db):
    items = scenario('A', 'window', START)[:5]
    items[-1]['timestamp'] = (START + timedelta(seconds=65)).isoformat()
    process(db, items)
    assert not list(db.scalars(select(Detection)))


def test_rule_disable_and_suppression(db):
    for rule in db.scalars(select(Rule)):
        rule.config = {**rule.config, 'suppressed_services': ['auth']}
    process(db, scenario('A', 'suppressed', START))
    assert not list(db.scalars(select(Detection)))
    for rule in db.scalars(select(Rule)):
        rule.config = {**rule.config, 'enabled': False, 'suppressed_services': []}
    process(db, scenario('A', 'disabled', START))
    assert not list(db.scalars(select(Detection)))


def test_alert_deduplication(db):
    process(db, scenario('A', 'dedup-alerts', START))
    detections = list(db.scalars(select(Detection)))
    assert len(detections) == 2
    assert len(list(db.scalars(select(Incident)))) == 1


def test_temporal_proximity_alone_not_correlation(db):
    a = scenario('B', 'one', START)
    b = scenario('B', 'two', START)
    for item in b:
        item['source'] = 'different-source'
    process(db, a + b)
    assert len(list(db.scalars(select(Incident)))) == 2


def test_synthetic_and_imported_not_merged(db):
    a = scenario('B', 'synthetic', START)
    b = scenario('B', 'imported', START)
    for item in b:
        item['origin'] = 'imported'
        item['trace_id'] = a[0]['trace_id']
    process(db, a + b)
    assert len(list(db.scalars(select(Incident)))) == 2


def test_late_parent_span_and_graph(db):
    data = scenario('D', 'reverse', START)
    rows = process(db, list(reversed(data)))
    assert list(db.scalars(select(Detection)))
    result = graph(rows)
    assert result['edges'][0]['source'] == 'auth'
    assert result['edges'][0]['target'] == 'payments'
    assert result['missing_parents'] == 0
    assert graph(rows[:1])['missing_parents'] == 1


def test_chain_tamper_and_missing_record(db):
    process(db, scenario('B', 'hash', START))
    assert verify(db)['valid']
    e = db.scalar(select(Event).limit(1))
    original = e.content
    e.content = {**e.content, 'service': 'altered'}
    assert not verify(db)['valid']
    e.content = original
    assert verify(db)['valid']
    db.delete(db.get(Evidence, 2))
    db.flush()
    assert not verify(db)['valid']


def test_out_of_order_chain_uses_ingestion_order(db):
    process(db, list(reversed(scenario('E', 'ordering', START)[:10])))
    assert verify(db)['valid']
    assert verify(db)['count'] == 10


def test_statistical_cold_start_and_holdout(db):
    rows = process(db, scenario('C', 'statistics', START)[:30])
    assert statistics(rows[:5])[0]['z_score'] is None
    rows[-1].content = {**rows[-1].content, 'attributes': {'latency_ms': 10000, 'status': 200}}
    stat = statistics(rows)[0]
    assert stat['baseline'] < 30
    assert stat['z_score'] > 3


def test_otlp_logs_without_trace():
    result = decode({'resourceLogs': [{'resource': {'attributes': [{'key': 'service.name', 'value': {'stringValue': 'auth'}}]}, 'scopeLogs': [{'logRecords': [{'timeUnixNano': '1767225600000000000', 'body': {'stringValue': 'hello'}}]}]}]}, 'logs')
    assert result[0]['trace_id'] is None
    assert result[0]['timestamp'] == '2026-01-01T00:00:00Z'
    with pytest.raises(ValueError):
        decode({}, 'traces')


def test_authorization_unknown_does_not_trigger(db):
    rows = scenario('B', 'unknown', START)
    for row in rows:
        row['attributes'].pop('authorized')
    process(db, rows)
    assert not list(db.scalars(select(Detection)))


def test_late_related_event_is_added(db):
    rows = process(db, scenario('B', 'late', START))
    incident = db.scalar(select(Incident))
    extra = Telemetry(timestamp=START + timedelta(seconds=10), service='gateway', kind='log', origin='synthetic', trace_id=rows[0].trace_id).normalized()
    process(db, [extra])
    assert db.get(IncidentEvent, (incident.id, extra['id']))
