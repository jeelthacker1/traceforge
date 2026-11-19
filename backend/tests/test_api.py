from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import auth, main
from app.db import User
from app.pipeline import persist
from app.rules import detect
from app.scenarios import scenario


@pytest.fixture
def client(factory, monkeypatch):
    monkeypatch.setattr(main, 'SessionLocal', factory)
    monkeypatch.setattr(auth, 'SessionLocal', factory)
    redis = MagicMock()
    redis.incr.return_value = 1
    redis.xlen.return_value = 0
    monkeypatch.setattr(main, 'redis_client', lambda: redis)
    with TestClient(main.app) as client:
        yield client


def login(client):
    assert client.post('/api/login', json={'username': 'admin', 'password': 'test-only-password-12345'}).status_code == 200


def test_authentication_and_session(client):
    assert client.get('/api/events').status_code == 401
    assert client.post('/api/login', json={'username': 'admin', 'password': 'wrong'}).status_code == 401
    login(client)
    assert client.get('/api/me').json()['role'] == 'ADMIN'
    assert client.post('/api/logout').status_code == 200
    assert client.get('/api/events').status_code == 401


def test_invalid_session(client):
    client.cookies.set('tf_session', 'invalid')
    assert client.get('/api/me').status_code == 401


def test_roles_and_cross_user_session(client, factory):
    login(client)
    assert client.post('/api/users', json={'username': 'viewer', 'password': 'viewer-password-long', 'role': 'VIEWER'}).status_code == 200
    client.post('/api/logout')
    assert client.post('/api/login', json={'username': 'viewer', 'password': 'viewer-password-long'}).status_code == 200
    assert client.get('/api/me').json()['username'] == 'viewer'
    assert client.post('/api/scenarios/A').status_code == 403
    assert client.get('/api/audit').status_code == 403
    assert client.post('/api/users', json={'username': 'other', 'password': 'other-password-long', 'role': 'ADMIN'}).status_code == 403
    assert client.get('/api/events').status_code == 200


def test_origin_and_oversize(client):
    assert client.post('/api/login', headers={'Origin': 'https://untrusted.example'}, json={'username': 'admin', 'password': 'test-only-password-12345'}).status_code == 403
    assert client.post('/api/ingest', content=b'x' * 2_000_001).status_code == 413


def test_ingestion_validation_and_backpressure(client, monkeypatch):
    assert client.post('/api/ingest', json=[]).status_code == 401
    headers = {'X-Ingest-Key': 'test-ingestion-key'}
    assert client.post('/api/ingest', headers=headers, json=[{'kind': 'auth'}]).status_code == 422
    monkeypatch.setattr(main, 'enqueue', lambda _: 0)
    assert client.post('/api/ingest', headers=headers, json=scenario('A', 'full')).status_code == 429
    monkeypatch.setattr(main, 'enqueue', lambda items: len(items))
    assert client.post('/api/ingest', headers=headers, json=scenario('A', 'accept')).json()['accepted'] == 12


def test_incident_status_notes_report_and_integrity(client, factory):
    with factory.begin() as db:
        for item in scenario('B', 'api'):
            event, _ = persist(db, item)
            detect(db, event)
    login(client)
    iid = client.get('/api/incidents').json()[0]['id']
    assert client.patch('/api/incidents/' + iid, json={'status': 'INVESTIGATING', 'reason': 'Review telemetry'}).status_code == 200
    detail = client.get('/api/incidents/' + iid).json()
    assert detail['status'] == 'INVESTIGATING'
    assert client.post('/api/incidents/' + iid + '/notes', json={'text': 'Potentially related', 'bookmark': detail['events'][0]['id']}).status_code == 200
    assert client.post('/api/incidents/' + iid + '/notes', json={'text': 'Invalid bookmark', 'bookmark': 'does-not-exist'}).status_code == 422
    report = client.get('/api/incidents/' + iid + '/report').json()
    assert report['integrity']['valid']
    assert len(report['manifest']['records']) == 6
    assert report['notes'][0]['text'] == 'Potentially related'
    pdf = client.get('/api/incidents/' + iid + '/report?format=pdf')
    assert pdf.content.startswith(b'%PDF')
    assert client.get('/api/audit').json()


def test_websocket_rejects_unauthenticated(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws', headers={'origin': 'http://localhost:3000'}):
            pass


def test_alert_and_rule_updates_persist(client, factory):
    with factory.begin() as db:
        for item in scenario('B', 'updates'):
            event, _ = persist(db, item)
            detect(db, event)
    login(client)
    alert = client.get('/api/alerts').json()[0]
    state = {'acknowledged': True, 'assignee': 'admin', 'resolution': 'Operational issue', 'escalated': True}
    assert client.patch('/api/alerts/' + alert['id'], json=state).status_code == 200
    assert client.get('/api/alerts').json()[0]['state'] == state
    assert client.patch('/api/rules/login_failures', json={'enabled': False, 'threshold': 7, 'window_seconds': 30}).status_code == 200
    rules = client.get('/api/rules').json()
    assert next(r for r in rules if r['id'] == 'login_failures')['enabled'] is False


def test_no_password_in_user_response(client, factory):
    login(client)
    assert 'password' not in str(client.get('/api/me').json())
    with factory() as db:
        assert db.get(User, 'admin').password_hash.startswith('$argon2')
