import os

os.environ.setdefault('ADMIN_PASSWORD', 'test-only-password-12345')
os.environ.setdefault('INGEST_KEY', 'test-ingestion-key')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.rules import seed_rules


@pytest.fixture
def factory():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as db:
        seed_rules(db)
    yield sessions
    engine.dispose()


@pytest.fixture
def db(factory):
    with factory.begin() as session:
        yield session
