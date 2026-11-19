import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SENSITIVE = re.compile(r'password|secret|token|authorization|cookie|email', re.I)


def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if SENSITIVE.search(k) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(r'[\x00-\x1f\x7f]', ' ', value)[:4096]
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


class Telemetry(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str | None = Field(None, max_length=128)
    timestamp: datetime
    service: str = Field(min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9_.:-]+$')
    kind: Literal['span', 'log', 'metric', 'auth', 'request', 'change']
    origin: Literal['local', 'synthetic', 'imported'] = 'imported'
    trace_id: str | None = Field(None, pattern=r'^[a-fA-F0-9]{32}$')
    span_id: str | None = Field(None, pattern=r'^[a-fA-F0-9]{16}$')
    parent_span_id: str | None = Field(None, pattern=r'^[a-fA-F0-9]{16}$')
    request_id: str | None = Field(None, max_length=128)
    account: str | None = Field(None, max_length=128)
    source: str | None = Field(None, max_length=128)
    attributes: dict = Field(default_factory=dict)

    @field_validator('timestamp')
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError('A timestamp must include its timezone; missing timestamps are rejected')
        return value.astimezone(timezone.utc)

    @field_validator('attributes')
    @classmethod
    def validate_attributes(cls, value):
        if len(canonical(value).encode()) > 32000:
            raise ValueError('Attributes must fit within 32 KB')
        if 'status' in value and (not isinstance(value['status'], int) or not 100 <= value['status'] <= 599):
            raise ValueError('HTTP status must be an integer between 100 and 599')
        if 'latency_ms' in value and (not isinstance(value['latency_ms'], (float, int)) or value['latency_ms'] < 0):
            raise ValueError('Latency must be a non-negative number')
        if 'path' in value and not isinstance(value['path'], str):
            raise ValueError('Request path must be a string')
        if 'authorized' in value and not isinstance(value['authorized'], bool):
            raise ValueError('Authorization must be a boolean, or omitted when unknown')
        return value

    def normalized(self):
        obj = redact(self.model_dump(mode='json', exclude={'id'}))
        # Revalidate strings after redaction and normalize IDs for OTLP interoperability.
        for key in ('trace_id', 'span_id', 'parent_span_id'):
            if obj[key]:
                obj[key] = obj[key].lower()
        return {'id': self.id or hashlib.sha256(canonical(obj).encode()).hexdigest(), **obj}
