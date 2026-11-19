"""Generate a local .env once, without emitting secrets."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
values = {name: secrets.token_hex(32) for name in ('POSTGRES_PASSWORD', 'ADMIN_PASSWORD', 'INGEST_KEY', 'CHECKPOINT_SIGNING_KEY')}
values.update(ALLOWED_ORIGINS='http://localhost:3000', COOKIE_SECURE='false', RETENTION_DAYS='30')
with (root / '.env').open('x', encoding='utf-8') as stream:
    stream.write(''.join(f'{key}={value}\n' for key, value in values.items()))
print('Created .env. Read ADMIN_PASSWORD locally to sign in as admin. Do not commit .env.')
