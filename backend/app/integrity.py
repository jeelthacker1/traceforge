import hashlib
import hmac
import os

from sqlalchemy import select

from .db import Evidence, Event
from .schema import canonical

GENESIS = '0' * 64


def digest(previous, content):
    return hashlib.sha256((previous + '\n' + canonical(content)).encode()).hexdigest()


def verify(db):
    previous = GENESIS
    errors = []
    count = 0
    last_sequence = 0
    for record in db.scalars(select(Evidence).order_by(Evidence.sequence)):
        event = db.get(Event, record.event_id)
        if record.sequence != last_sequence + 1:
            errors.append(f'Missing sequence before {record.sequence}')
        if not event or record.previous_hash != previous or digest(previous, event.content) != record.digest:
            errors.append(f'Integrity failure at sequence {record.sequence}')
        previous = record.digest
        last_sequence = record.sequence
        count += 1
    return {'valid': not errors, 'count': count, 'head': previous, 'errors': errors,
            'limitations': 'Tail deletion requires a separately retained checkpoint to detect. Database administrators can rewrite the chain.'}


def checkpoint(result):
    payload = {k: result[k] for k in ('count', 'head')}
    key = os.getenv('CHECKPOINT_SIGNING_KEY')
    return {**payload, 'algorithm': 'HMAC-SHA256' if key else 'unsigned',
            'signature': hmac.new(key.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest() if key else None}
