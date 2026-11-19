import json
import os
import signal
import time
import uuid
from datetime import datetime

from redis import Redis
from sqlalchemy import select, text

from .db import Evidence, Event, Metric, Service, SessionLocal, Span, Trace
from .integrity import GENESIS, digest
from .rules import detect, enrich_incidents, escalate_due
from .schema import Telemetry

STREAM = 'traceforge:ingest'
MAX_QUEUE = int(os.getenv('MAX_QUEUE', '50000'))


def redis_client():
    return Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)


def enqueue(events):
    client = redis_client()
    # Atomic capacity check + batch enqueue. Never trim unprocessed evidence.
    script = """
    if redis.call('XLEN', KEYS[1]) + #ARGV - 1 > tonumber(ARGV[1]) then return 0 end
    for i=2,#ARGV do redis.call('XADD', KEYS[1], '*', 'event', ARGV[i]) end
    return #ARGV - 1
    """
    return client.eval(script, 1, STREAM, MAX_QUEUE, *[json.dumps(e) for e in events])


def persist(db, data):
    data = Telemetry.model_validate(data).normalized()
    # Serialize chain writers at the database boundary, including duplicate races.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(842091)'))
    existing = db.get(Event, data['id'])
    if existing:
        if existing.content != data:
            raise ValueError('Event ID collision with different normalized content')
        return existing, False
    last = db.scalar(select(Evidence).order_by(Evidence.sequence.desc()).limit(1))
    previous = last.digest if last else GENESIS
    event = Event(id=data['id'], timestamp=datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00')), service=data['service'], kind=data['kind'], trace_id=data['trace_id'], span_id=data['span_id'], parent_span_id=data['parent_span_id'], account=data['account'], source=data['source'], origin=data['origin'], content=data)
    db.add(event)
    db.flush()
    db.add(Evidence(event_id=event.id, previous_hash=previous, digest=digest(previous, data)))
    service = db.get(Service, event.service)
    if service:
        service.last_seen = event.timestamp
    else:
        db.add(Service(id=event.service, last_seen=event.timestamp))
    if event.trace_id:
        if not db.get(Trace, event.trace_id):
            db.add(Trace(id=event.trace_id))
            db.flush()
        if event.span_id:
            span_key = event.trace_id + ':' + event.span_id
            if not db.get(Span, span_key):
                db.add(Span(id=span_key, trace_id=event.trace_id, event_id=event.id))
    if event.kind == 'metric' and isinstance(data['attributes'].get('value'), (int, float)):
        db.add(Metric(event_id=event.id, name=data['attributes'].get('name', 'unknown'), value=data['attributes']['value']))
    db.flush()
    return event, True


def run(mode):
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    client = redis_client()
    consumer = str(uuid.uuid4())
    if mode == 'ingestion':
        try:
            client.xgroup_create(STREAM, 'persist', id='0', mkstream=True)
        except Exception as exc:
            if 'BUSYGROUP' not in str(exc):
                raise
    while running:
        try:
            if mode == 'ingestion':
                claimed = client.xautoclaim(STREAM, 'persist', consumer, min_idle_time=30000, count=100)[1]
                batches = [(STREAM, claimed)] if claimed else client.xreadgroup('persist', consumer, {STREAM: '>'}, count=100, block=1000)
                for _, entries in batches:
                    for sid, fields in entries:
                        try:
                            with SessionLocal.begin() as db:
                                persist(db, json.loads(fields['event']))
                        except (ValueError, KeyError) as exc:
                            # Explicit dead-letter metadata; no raw payload or secrets in logs.
                            client.xadd('traceforge:dead', {'stream_id': sid, 'error': str(exc)[:200]}, maxlen=1000)
                        client.xack(STREAM, 'persist', sid)
                        client.xdel(STREAM, sid)
            else:
                with SessionLocal.begin() as db:
                    pending = list(db.scalars(select(Event).where(Event.processed.is_(False)).order_by(Event.timestamp, Event.id).limit(100).with_for_update(skip_locked=True)))
                    for event in pending:
                        detect(db, event)
                        enrich_incidents(db, event)
                    escalate_due(db)
                if pending:
                    client.publish('traceforge:updates', json.dumps({'type': 'events', 'count': len(pending)}))
                else:
                    time.sleep(0.5)
            client.set('traceforge:heartbeat:' + mode, str(time.time()), ex=30)
        except Exception as exc:
            print(json.dumps({'level': 'error', 'worker': mode, 'error_type': type(exc).__name__}), flush=True)
            time.sleep(1)


if __name__ == '__main__':
    import sys
    run(sys.argv[1])
