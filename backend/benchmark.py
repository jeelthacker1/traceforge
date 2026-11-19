"""Reproducible real measurements; SQLite microbenchmark is not a distributed throughput claim."""
import json
import os
import platform
import tempfile
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.analytics import graph
from app.db import Base, Detection, Event, Incident
from app.integrity import verify
from app.pipeline import persist
from app.rules import detect, seed_rules
from app.scenarios import scenario
from app.schema import Telemetry


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = create_engine('sqlite:///' + directory + '/benchmark.db')
        Base.metadata.create_all(engine)
        start_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        count = 10000
        with Session(engine) as db:
            seed_rules(db)
            db.commit()
            started = time.perf_counter()
            for i in range(count):
                event = Telemetry(id=f'benchmark-{i}', timestamp=start_time + timedelta(milliseconds=i), service='gateway', kind='request', origin='synthetic', source=f'normal-{i%100}', attributes={'status': 200, 'latency_ms': 20 + i % 11}).normalized()
                persist(db, event)
                if i % 500 == 0:
                    db.commit()
            db.commit()
            ingest = time.perf_counter() - started
            started = time.perf_counter()
            result = verify(db)
            verification = time.perf_counter() - started
            assert result['valid'] and result['count'] == count
            started = time.perf_counter()
            graph(list(db.scalars(select(Event))))
            graph_seconds = time.perf_counter() - started
            started = time.perf_counter()
            for row in scenario('A', 'benchmark-alert', start_time + timedelta(hours=1)):
                event, _ = persist(db, row)
                detect(db, event)
            db.commit()
            detection = time.perf_counter() - started
            assert list(db.scalars(select(Detection)))
            started = time.perf_counter()
            assert list(db.scalars(select(Incident)))
            query = time.perf_counter() - started
        engine.dispose()
    print(json.dumps({'environment': {'os': platform.platform(), 'python': platform.python_version(), 'cpu': platform.processor(), 'logical_cpus': os.cpu_count(), 'database': 'SQLite local file'}, 'events': count, 'persistence_seconds': ingest, 'events_per_second': count / ingest, 'verification_seconds': verification, 'server_graph_query_seconds': graph_seconds, 'scenario_processing_seconds': detection, 'incident_query_seconds': query, 'limitations': 'Single-process SQLite persistence microbenchmark. Does not measure OTLP network/Redis throughput or browser graph rendering.'}, indent=2))


if __name__ == '__main__':
    main()
