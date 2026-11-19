import hashlib
import os
import secrets
from datetime import timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import Role, Session, SessionLocal, User, audit, now

hasher = PasswordHasher()


def bootstrap(db):
    for role in ('ADMIN', 'SECURITY_ANALYST', 'VIEWER'):
        if not db.get(Role, role):
            db.add(Role(name=role))
    db.flush()
    if not db.scalar(select(User).limit(1)):
        password = os.getenv('ADMIN_PASSWORD')
        if not password or len(password) < 12:
            raise RuntimeError('Set ADMIN_PASSWORD to at least 12 characters before starting')
        db.add(User(id='admin', password_hash=hasher.hash(password), role='ADMIN'))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def lookup(token):
    if not token:
        return None
    with SessionLocal() as db:
        session = db.get(Session, token_hash(token))
        if session and session.expires.replace(tzinfo=timezone.utc) > now():
            return db.get(User, session.user_id)
    return None


def current(request: Request):
    user = lookup(request.cookies.get('tf_session'))
    if not user:
        raise HTTPException(401, 'Authentication required')
    return user


def analyst(user=Depends(current)):
    if user.role not in ('ADMIN', 'SECURITY_ANALYST'):
        raise HTTPException(403, 'Analyst role required')
    return user


def admin(user=Depends(current)):
    if user.role != 'ADMIN':
        raise HTTPException(403, 'Administrator role required')
    return user


def login(db, username, password):
    user = db.get(User, username)
    # Verify a dummy Argon2 hash for unknown accounts to reduce timing disclosure.
    check = user.password_hash if user else DUMMY
    try:
        hasher.verify(check, password)
    except VerificationError:
        return None
    if not user:
        return None
    token = secrets.token_urlsafe(32)
    db.add(Session(id=token_hash(token), user_id=user.id, expires=now() + timedelta(hours=8)))
    audit(db, user.id, 'login', user.id)
    return token


DUMMY = hasher.hash(secrets.token_urlsafe(32))
