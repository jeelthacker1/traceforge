"""Verify an exported evidence chain offline; optional separately retained checkpoint."""
import argparse
import hashlib
import hmac
import json
import os


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def verify_export(data, trusted=None):
    previous = '0' * 64
    count = 0
    for record in data['manifest']['records']:
        count += 1
        expected = hashlib.sha256((previous + '\n' + canonical(record['event'])).encode()).hexdigest()
        if record['sequence'] != count or record['previous_hash'] != previous or record['digest'] != expected:
            raise ValueError(f'Integrity failure at record {count}')
        previous = expected
    if trusted:
        if trusted['count'] != count or trusted['head'] != previous:
            raise ValueError('Export does not match separately retained checkpoint')
        if trusted['algorithm'] == 'HMAC-SHA256':
            key = os.environ['CHECKPOINT_SIGNING_KEY']
            signature = hmac.new(key.encode(), canonical({'count': count, 'head': previous}).encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, trusted['signature']):
                raise ValueError('Checkpoint signature mismatch')
    return {'valid': True, 'count': count, 'head': previous, 'trusted_checkpoint_checked': trusted is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('report')
    parser.add_argument('--checkpoint')
    args = parser.parse_args()
    with open(args.report, encoding='utf-8') as f:
        report = json.load(f)
    trusted = None
    if args.checkpoint:
        with open(args.checkpoint, encoding='utf-8') as f:
            trusted = json.load(f)
    print(json.dumps(verify_export(report, trusted), indent=2))
