from datetime import datetime, timezone

from .schema import Telemetry


def value(v):
    if 'intValue' in v:
        return int(v['intValue'])
    if 'arrayValue' in v:
        return [value(x) for x in v['arrayValue'].get('values', [])]
    if 'kvlistValue' in v:
        return attributes(v['kvlistValue'].get('values', []))
    return next(iter(v.values()), None)


def attributes(items):
    return {a['key']: value(a.get('value', {})) for a in items}


def timestamp(ns):
    if not ns or int(ns) <= 0:
        raise ValueError('Missing OTLP timestamp; no timestamp will be invented')
    return datetime.fromtimestamp(int(ns) / 1e9, timezone.utc)


def decode(payload, signal):
    # OTLP/HTTP JSON. Collector converts SDK protobuf to JSON for this boundary.
    resource_key, scope_key, item_key = {
        'traces': ('resourceSpans', 'scopeSpans', 'spans'),
        'logs': ('resourceLogs', 'scopeLogs', 'logRecords'),
        'metrics': ('resourceMetrics', 'scopeMetrics', 'metrics'),
    }[signal]
    if resource_key not in payload:
        raise ValueError('Invalid OTLP resource envelope')
    output = []
    for resource in payload[resource_key]:
        res = attributes(resource.get('resource', {}).get('attributes', []))
        if not res.get('service.name'):
            raise ValueError('service.name is required')
        for scope in resource.get(scope_key, []):
            for item in scope.get(item_key, []):
                points = [item] if signal != 'metrics' else next((item[k].get('dataPoints', []) for k in ('gauge', 'sum', 'histogram', 'exponentialHistogram', 'summary') if k in item), [])
                for point in points:
                    attrs = attributes(point.get('attributes', []))
                    base = {'service': res['service.name'], 'origin': res.get('traceforge.origin', 'imported'), 'attributes': attrs,
                            'timestamp': timestamp(point.get('startTimeUnixNano') if signal == 'traces' else point.get('timeUnixNano')),
                            'trace_id': point.get('traceId') or None, 'span_id': point.get('spanId') or None,
                            'parent_span_id': point.get('parentSpanId') or None,
                            'account': attrs.get('account'), 'source': attrs.get('source'), 'request_id': attrs.get('request_id')}
                    if signal == 'traces':
                        base['kind'] = 'span'
                        attrs.update({'name': point.get('name'), 'span_kind': point.get('kind'), 'latency_ms': (int(point['endTimeUnixNano']) - int(point['startTimeUnixNano'])) / 1e6})
                        for dst, src in [('status', 'http.response.status_code'), ('path', 'url.path')]:
                            if src in attrs:
                                attrs[dst] = attrs[src]
                    elif signal == 'logs':
                        base['kind'] = 'auth' if attrs.get('event.kind') == 'auth' else 'log'
                        attrs['body'] = value(point.get('body', {}))
                        attrs['severity'] = point.get('severityText', 'UNSPECIFIED')
                    else:
                        base['kind'] = 'metric'
                        attrs.update({'name': item.get('name'), 'value': float(point.get('asDouble', point.get('asInt', point.get('sum', 0)))), 'aggregation': next((k for k in ('gauge', 'sum', 'histogram', 'exponentialHistogram', 'summary') if k in item), 'unknown'), 'point': point})
                    output.append(Telemetry.model_validate(base).normalized())
    return output
