import os
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(String, ForeignKey('roles.name'))


class Role(Base):
    __tablename__ = 'roles'
    name: Mapped[str] = mapped_column(String, primary_key=True)


class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = 'telemetry_events'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    service: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    trace_id: Mapped[str | None] = mapped_column(String, index=True)
    span_id: Mapped[str | None]
    parent_span_id: Mapped[str | None]
    account: Mapped[str | None] = mapped_column(String, index=True)
    source: Mapped[str | None] = mapped_column(String, index=True)
    origin: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[dict] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(default=False, index=True)


class Evidence(Base):
    __tablename__ = 'evidence_records'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('telemetry_events.id'), unique=True)
    previous_hash: Mapped[str]
    digest: Mapped[str]


class Checkpoint(Base):
    __tablename__ = 'evidence_checkpoints'
    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Rule(Base):
    __tablename__ = 'detection_rules'
    id: Mapped[str] = mapped_column(primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)


class Detection(Base):
    __tablename__ = 'detection_results'
    id: Mapped[str] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey('detection_rules.id'))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    severity: Mapped[str] = mapped_column(index=True)
    evidence: Mapped[list] = mapped_column(JSON)
    detail: Mapped[dict] = mapped_column(JSON)
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class Incident(Base):
    __tablename__ = 'incidents'
    id: Mapped[str] = mapped_column(primary_key=True)
    correlation_key: Mapped[str] = mapped_column(index=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(default='NEW')
    detection_ids: Mapped[list] = mapped_column(JSON)
    limitations: Mapped[str] = mapped_column(Text)


class IncidentEvent(Base):
    __tablename__ = 'incident_events'
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('telemetry_events.id'), primary_key=True)


class Investigation(Base):
    __tablename__ = 'investigations'
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id'), index=True)
    author: Mapped[str]
    text: Mapped[str] = mapped_column(Text)
    bookmark: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str]
    action: Mapped[str]
    target: Mapped[str]
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RetentionPolicy(Base):
    __tablename__ = 'retention_policies'
    id: Mapped[str] = mapped_column(primary_key=True)
    days: Mapped[int]


class Service(Base):
    __tablename__ = 'services'
    id: Mapped[str] = mapped_column(primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Trace(Base):
    __tablename__ = 'traces'
    id: Mapped[str] = mapped_column(primary_key=True)


class Span(Base):
    __tablename__ = 'spans'
    id: Mapped[str] = mapped_column(primary_key=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey('traces.id'), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('telemetry_events.id'))


class Metric(Base):
    __tablename__ = 'metrics'
    event_id: Mapped[str] = mapped_column(ForeignKey('telemetry_events.id'), primary_key=True)
    name: Mapped[str]
    value: Mapped[float]


engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./traceforge.db'), pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def audit(db, actor, action, target, detail=None):
    db.add(Audit(actor=actor, action=action, target=target, detail=detail or {}))
