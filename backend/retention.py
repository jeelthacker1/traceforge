"""Inspect retention eligibility without silently destroying evidence."""
import json
from datetime import timedelta

from sqlalchemy import func, select

from app.db import Event, Incident, RetentionPolicy, SessionLocal, now

with SessionLocal() as db:
    policy = db.get(RetentionPolicy, 'telemetry')
    days = policy.days if policy else 30
    cutoff = now() - timedelta(days=days)
    expired = db.scalar(select(func.count()).select_from(Event).where(Event.timestamp < cutoff))
    open_incidents = db.scalar(select(func.count()).select_from(Incident).where(Incident.status.not_in(['RESOLVED', 'FALSE_POSITIVE'])))
    print(json.dumps({'policy_days': days, 'cutoff': cutoff.isoformat(), 'expired_events': expired, 'unresolved_incidents': open_incidents, 'action': 'Export evidence and retain checkpoints separately before dataset rotation. Automatic destructive retention is not enabled.'}, indent=2))
