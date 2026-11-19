import asyncio
import io
import json
import os
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import func, select
from xml.sax.saxutils import escape

from . import auth
from .analytics import graph, statistics
from .db import Audit, Checkpoint, Detection, Event, Incident, IncidentEvent, Investigation, RetentionPolicy, Rule, Session, SessionLocal, User, audit, now
from .integrity import checkpoint, verify
from .otlp import decode
from .pipeline import enqueue, redis_client
from .rules import seed_rules
from .scenarios import CATALOG, scenario
from .schema import Telemetry, redact

ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')


@asynccontextmanager
async def lifespan(app):
    with SessionLocal.begin() as db:
        auth.bootstrap(db)
        seed_rules(db)
        if not db.get(RetentionPolicy, 'telemetry'):
            db.add(RetentionPolicy(id='telemetry', days=int(os.getenv('RETENTION_DAYS', '30'))))
    yield


app = FastAPI(title='TraceForge', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True, allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Content-Type', 'X-Ingest-Key'])


@app.middleware('http')
async def security(request, call_next):
    if request.method in ('POST', 'PATCH', 'DELETE') and request.headers.get('origin') and request.headers['origin'] not in ORIGINS:
        return Response('Origin denied', status_code=403)
    if request.headers.get('content-encoding', 'identity') != 'identity':
        return Response('Compressed request bodies are not supported at the API boundary', status_code=415)
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2_000_000:
            return Response('Payload exceeds 2 MB', status_code=413)
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if request.url.path == '/api/login':
        try:
            client = redis_client()
            key = 'login-limit:' + request.client.host
            count = client.incr(key)
            if count == 1:
                client.expire(key, 60)
            if count > 10:
                return Response('Login rate limit exceeded', status_code=429)
        except Exception:
            return Response('Authentication rate limiter unavailable', status_code=503)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


class Credentials(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)


@app.post('/api/login')
def login(payload: Credentials, response: Response):
    with SessionLocal.begin() as db:
        token = auth.login(db, payload.username, payload.password)
        if not token:
            raise HTTPException(401, 'Invalid credentials')
    response.set_cookie('tf_session', token, httponly=True, samesite='strict', secure=os.getenv('COOKIE_SECURE', 'false') == 'true', max_age=28800, path='/')
    return {'ok': True}


@app.post('/api/logout')
def logout(request: Request, response: Response, user=Depends(auth.current)):
    with SessionLocal.begin() as db:
        session = db.get(Session, auth.token_hash(request.cookies['tf_session']))
        if session:
            db.delete(session)
        audit(db, user.id, 'logout', user.id)
    response.delete_cookie('tf_session', path='/')
    return {'ok': True}


@app.get('/api/me')
def me(user=Depends(auth.current)):
    return {'username': user.id, 'role': user.role}


class NewUser(Credentials):
    role: Literal['ADMIN', 'SECURITY_ANALYST', 'VIEWER']


@app.post('/api/users')
def create_user(payload: NewUser, user=Depends(auth.admin)):
    if len(payload.password) < 12:
        raise HTTPException(422, 'Use at least 12 characters')
    with SessionLocal.begin() as db:
        if db.get(User, payload.username):
            raise HTTPException(409, 'User exists')
        db.add(User(id=payload.username, password_hash=auth.hasher.hash(payload.password), role=payload.role))
        audit(db, user.id, 'create_user', payload.username, {'role': payload.role})
    return {'ok': True}


@app.get('/health')
def health():
    with SessionLocal() as db:
        db.execute(select(1))
    redis_client().ping()
    return {'status': 'ok'}


def ingest_key(request: Request):
    expected = os.getenv('INGEST_KEY', '')
    if not expected or not secrets.compare_digest(request.headers.get('x-ingest-key', ''), expected):
        raise HTTPException(401, 'Invalid ingestion credential')


def submit(events):
    if not events:
        return {'accepted': 0}
    if len(events) > 1000:
        raise HTTPException(413, 'At most 1000 events per batch')
    try:
        accepted = enqueue(events)
    except Exception:
        raise HTTPException(503, 'Ingestion buffer unavailable; retry later') from None
    if not accepted:
        raise HTTPException(429, 'Ingestion buffer full; retry later', headers={'Retry-After': '5'})
    return {'accepted': accepted}


@app.post('/api/ingest', dependencies=[Depends(ingest_key)], status_code=202)
def ingest(events: list[Telemetry]):
    return submit([e.normalized() for e in events])


@app.post('/v1/{signal}', dependencies=[Depends(ingest_key)])
async def otlp(signal: Literal['traces', 'logs', 'metrics'], request: Request):
    if 'application/json' not in request.headers.get('content-type', ''):
        raise HTTPException(415, 'Use OTLP/HTTP JSON; Collector accepts protobuf upstream')
    try:
        events = decode(await request.json(), signal)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise HTTPException(400, f'Invalid OTLP payload: {type(exc).__name__}') from None
    submit(events)
    return {}


def events_query(db, minutes=60, service=None, search=None, until=None, limit=10000):
    end = until or now()
    query = select(Event).where(Event.timestamp >= end - timedelta(minutes=minutes), Event.timestamp <= end)
    if service:
        query = query.where(Event.service == service)
    if search:
        query = query.where(Event.id.contains(search, autoescape=True) | Event.account.contains(search, autoescape=True) | Event.trace_id.contains(search, autoescape=True))
    return list(db.scalars(query.order_by(Event.timestamp.desc(), Event.id).limit(limit)))


@app.get('/api/events')
def events(minutes: int = Query(60, ge=1, le=43200), service: str | None = None, search: str | None = Query(None, max_length=128), limit: int = Query(200, ge=1, le=1000), user=Depends(auth.current)):
    with SessionLocal() as db:
        rows = events_query(db, minutes, service, search, limit=limit)
        return {'events': [e.content for e in rows], 'limit': limit, 'possibly_truncated': len(rows) == limit}


@app.get('/api/overview')
def overview(minutes: int = Query(60, ge=1, le=43200), service: str | None = None, user=Depends(auth.current)):
    with SessionLocal() as db:
        rows = events_query(db, minutes, service)
        pending = db.scalar(select(func.count()).select_from(Event).where(Event.processed.is_(False)))
        oldest = db.scalar(select(func.min(Event.ingested_at)).where(Event.processed.is_(False)))
        alerts = list(db.scalars(select(Detection).where(Detection.timestamp >= now() - timedelta(minutes=minutes))))
        latency = [e.content['attributes']['latency_ms'] for e in rows if 'latency_ms' in e.content['attributes']]
        requests = [e for e in rows if 'status' in e.content['attributes']]
        trend = Counter(e.timestamp.strftime('%H:%M') for e in rows)
        try:
            client = redis_client()
            pipeline = {'queue': client.xlen('traceforge:ingest'), 'dead_letters': client.xlen('traceforge:dead'), 'ingestion_worker': bool(client.get('traceforge:heartbeat:ingestion')), 'correlation_worker': bool(client.get('traceforge:heartbeat:correlation'))}
        except Exception:
            pipeline = {'available': False}
        return {'events': len(rows), 'services': len({e.service for e in rows}), 'alerts': len(alerts), 'auth_failures': sum(e.kind == 'auth' and e.content['attributes'].get('outcome') == 'failure' for e in rows),
                'error_rate': sum(e.content['attributes']['status'] >= 500 for e in requests) / len(requests) if requests else None,
                'latency_ms': sum(latency) / len(latency) if latency else None, 'pending': pending, 'lag_seconds': (now() - oldest.replace(tzinfo=timezone.utc)).total_seconds() if oldest else 0,
                'trend': [{'time': k, 'events': v} for k, v in sorted(trend.items())], 'pipeline': pipeline, 'sample_limit': 10000, 'truncated': len(rows) == 10000, 'anomalies': statistics(rows)}


@app.get('/api/graph')
def service_graph(minutes: int = Query(60, ge=1, le=43200), until: datetime | None = None, user=Depends(auth.current)):
    if until and until.tzinfo is None:
        raise HTTPException(422, 'until requires timezone')
    with SessionLocal() as db:
        rows = events_query(db, minutes, until=until)
        return {**graph(rows), 'truncated': len(rows) == 10000}


def serialize_detection(d):
    return {'id': d.id, 'rule_id': d.rule_id, 'timestamp': d.timestamp, 'severity': d.severity, 'evidence': d.evidence, 'detail': d.detail, 'state': d.state}


@app.get('/api/alerts')
def alerts(severity: str | None = None, user=Depends(auth.current)):
    with SessionLocal() as db:
        query = select(Detection).order_by(Detection.timestamp.desc()).limit(200)
        if severity:
            query = query.where(Detection.severity == severity)
        return [serialize_detection(d) for d in db.scalars(query)]


class AlertUpdate(BaseModel):
    acknowledged: bool = False
    assignee: str | None = Field(None, max_length=80)
    resolution: str | None = Field(None, max_length=2000)
    escalated: bool = False


@app.patch('/api/alerts/{aid}')
def update_alert(aid: str, payload: AlertUpdate, user=Depends(auth.analyst)):
    with SessionLocal.begin() as db:
        d = db.get(Detection, aid)
        if not d:
            raise HTTPException(404, 'Alert not found')
        d.state = redact(payload.model_dump())
        if payload.escalated:
            d.severity = 'high'
        audit(db, user.id, 'update_alert', aid, d.state)
    return {'ok': True}


@app.get('/api/rules')
def rules(user=Depends(auth.current)):
    with SessionLocal() as db:
        return [{'id': r.id, **r.config} for r in db.scalars(select(Rule))]


class RuleUpdate(BaseModel):
    enabled: bool
    threshold: float = Field(gt=0, le=100000)
    window_seconds: int = Field(ge=1, le=3600)
    suppressed_services: list[str] = Field(default_factory=list, max_length=100)
    allowed_edges: list[list[str]] | None = None


@app.patch('/api/rules/{rid}')
def update_rule(rid: str, payload: RuleUpdate, user=Depends(auth.admin)):
    with SessionLocal.begin() as db:
        rule = db.get(Rule, rid)
        if not rule:
            raise HTTPException(404, 'Rule not found')
        rule.config = {**rule.config, **payload.model_dump(exclude_none=True)}
        audit(db, user.id, 'update_rule', rid, payload.model_dump())
    return {'ok': True}


def incident_summary(i):
    return {'id': i.id, 'start': i.start, 'end': i.end, 'status': i.status, 'detection_ids': i.detection_ids, 'limitations': i.limitations}


@app.get('/api/incidents')
def incidents(user=Depends(auth.current)):
    with SessionLocal() as db:
        return [incident_summary(i) for i in db.scalars(select(Incident).order_by(Incident.end.desc()).limit(200))]


def incident_detail(db, iid):
    incident = db.get(Incident, iid)
    if not incident:
        raise HTTPException(404, 'Incident not found')
    rows = list(db.scalars(select(Event).join(IncidentEvent, Event.id == IncidentEvent.event_id).where(IncidentEvent.incident_id == iid).order_by(Event.timestamp, Event.id)))
    notes = list(db.scalars(select(Investigation).where(Investigation.incident_id == iid).order_by(Investigation.created_at)))
    detections = [db.get(Detection, did) for did in incident.detection_ids]
    baseline = events_query(db, 5, until=incident.start.replace(tzinfo=timezone.utc) - timedelta(microseconds=1))
    return {**incident_summary(incident), 'events': [e.content for e in rows], 'detections': [serialize_detection(d) for d in detections if d],
            'notes': [{'id': n.id, 'author': n.author, 'text': n.text, 'bookmark': n.bookmark, 'created_at': n.created_at} for n in notes],
            'graph': graph(rows), 'baseline_graph': graph(baseline), 'anomalies': statistics(rows),
            'facts': {'services': sorted({e.service for e in rows}), 'first_observed': rows[0].content if rows else None, 'deployment_events': [e.content for e in rows if e.kind == 'change']},
            'hypotheses': ['Potentially related events share explicit identifiers. Correlation does not establish causation.'],
            'unresolved_questions': ['Missing parents or events may limit reconstruction.', 'Deployment causes are unknown unless change events were collected.']}


@app.get('/api/incidents/{iid}')
def get_incident(iid: str, user=Depends(auth.current)):
    with SessionLocal() as db:
        return incident_detail(db, iid)


class StatusUpdate(BaseModel):
    status: Literal['NEW', 'TRIAGED', 'INVESTIGATING', 'CONTAINED', 'RESOLVED', 'FALSE_POSITIVE']
    reason: str = Field(min_length=1, max_length=2000)


@app.patch('/api/incidents/{iid}')
def update_incident(iid: str, payload: StatusUpdate, user=Depends(auth.analyst)):
    with SessionLocal.begin() as db:
        i = db.get(Incident, iid)
        if not i:
            raise HTTPException(404, 'Incident not found')
        audit(db, user.id, 'incident_status', iid, {'from': i.status, 'to': payload.status, 'reason': redact(payload.reason)})
        i.status = payload.status
    return {'ok': True}


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    bookmark: str | None = None


@app.post('/api/incidents/{iid}/notes')
def note(iid: str, payload: Note, user=Depends(auth.analyst)):
    with SessionLocal.begin() as db:
        if not db.get(Incident, iid):
            raise HTTPException(404, 'Incident not found')
        if payload.bookmark and not db.get(IncidentEvent, (iid, payload.bookmark)):
            raise HTTPException(422, 'Bookmark must belong to this incident')
        db.add(Investigation(incident_id=iid, author=user.id, text=redact(payload.text), bookmark=payload.bookmark))
        audit(db, user.id, 'investigation_note', iid)
    return {'ok': True}


@app.get('/api/evidence/verify')
def verification(user=Depends(auth.current)):
    with SessionLocal.begin() as db:
        result = verify(db)
        audit(db, user.id, 'verify_evidence', 'chain', {'valid': result['valid']})
        return result


@app.post('/api/evidence/checkpoint')
def make_checkpoint(user=Depends(auth.admin)):
    with SessionLocal.begin() as db:
        result = verify(db)
        if not result['valid']:
            raise HTTPException(409, 'Refusing to checkpoint an invalid chain')
        cp = checkpoint(result)
        db.add(Checkpoint(content=cp))
        audit(db, user.id, 'checkpoint', 'chain', cp)
        return cp


@app.get('/api/incidents/{iid}/report')
def report(iid: str, format: Literal['json', 'pdf'] = 'json', user=Depends(auth.current)):
    from fastapi.encoders import jsonable_encoder
    from .db import Evidence
    with SessionLocal.begin() as db:
        data = incident_detail(db, iid)
        # Export the complete chain so the offline utility can verify sequence continuity.
        records = [{'sequence': r.sequence, 'previous_hash': r.previous_hash, 'digest': r.digest, 'event': db.get(Event, r.event_id).content} for r in db.scalars(select(Evidence).order_by(Evidence.sequence))]
        data.update({'executive_summary': f"Investigation of {len(data['detections'])} telemetry indicators across {len(data['facts']['services'])} services. Malicious intent is not established.", 'integrity': verify(db), 'manifest': {'canonicalization': 'UTF-8 JSON, sorted keys, compact separators, non-ASCII preserved, finite numbers only; digest = SHA256(previous + newline + canonical event)', 'records': records}, 'checkpoint': checkpoint(verify(db)), 'recommendations': ['Validate affected account activity with its owner.', 'Review service configuration and dependency changes.', 'Retain the signed checkpoint separately from this database.']})
        audit(db, user.id, 'export_evidence', iid, {'format': format})
    if format == 'json':
        return Response(json.dumps(jsonable_encoder(data), ensure_ascii=False), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="{iid}.json"'})
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph('TRACEFORGE / Incident report', styles['Title']), Spacer(1, 16)]
    for title, value in [('Executive summary', data['executive_summary']), ('Facts', data['facts']), ('Detections', data['detections']), ('Timeline', data['events']), ('Notes', data['notes']), ('Hypotheses', data['hypotheses']), ('Unresolved questions', data['unresolved_questions']), ('Integrity', data['integrity']), ('Recommendations', data['recommendations'])]:
        story.append(Paragraph(title, styles['Heading2']))
        values = value if isinstance(value, list) else [value]
        for item in values:
            story.append(Paragraph(escape(json.dumps(jsonable_encoder(item), ensure_ascii=False)), styles['BodyText']))
            story.append(Spacer(1, 6))
    SimpleDocTemplate(buffer).build(story)
    return Response(buffer.getvalue(), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{iid}.pdf"'})


@app.get('/api/scenarios')
def scenarios(user=Depends(auth.current)):
    return CATALOG


@app.post('/api/scenarios/{code}')
def generate(code: str, user=Depends(auth.analyst)):
    if code not in CATALOG:
        raise HTTPException(404, 'Unknown scenario')
    run_id = str(uuid4())
    result = submit(scenario(code, run_id))
    with SessionLocal.begin() as db:
        audit(db, user.id, 'synthetic_scenario', code, {'run_id': run_id})
    return {**result, 'run_id': run_id, 'ground_truth': CATALOG[code]}


@app.get('/api/audit')
def audit_history(user=Depends(auth.analyst)):
    with SessionLocal() as db:
        return [{'actor': a.actor, 'action': a.action, 'target': a.target, 'detail': a.detail, 'timestamp': a.timestamp} for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(200))]


@app.websocket('/ws')
async def websocket(ws: WebSocket):
    if ws.headers.get('origin') not in ORIGINS or not auth.lookup(ws.cookies.get('tf_session')):
        await ws.close(code=1008)
        return
    await ws.accept()
    from redis.asyncio import Redis
    client = Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe('traceforge:updates')
        while True:
            if not auth.lookup(ws.cookies.get('tf_session')):
                await ws.close(code=1008)
                break
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
            await ws.send_json(json.loads(message['data']) if message else {'type': 'heartbeat'})
            await asyncio.sleep(0.1)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await pubsub.aclose()
        await client.aclose()
