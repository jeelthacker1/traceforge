"""Local fictional commerce services with real OTLP traces, logs and metrics."""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE = os.getenv('SERVICE_NAME', 'gateway')
resource = Resource.create({'service.name': SERVICE, 'traceforge.origin': 'local'})
tracer = TracerProvider(resource=resource)
tracer.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(tracer)
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
set_logger_provider(logger_provider)
audit_logger = logging.getLogger('demo.audit')
audit_logger.setLevel(logging.INFO)
audit_logger.addHandler(LoggingHandler(logger_provider=logger_provider))
meter_provider = MeterProvider(resource=resource, metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=5000)])
metrics.set_meter_provider(meter_provider)
latency = metrics.get_meter('demo').create_histogram('demo.request.duration', unit='ms')
counter = metrics.get_meter('demo').create_counter('demo.requests')
HTTPXClientInstrumentor().instrument()


@asynccontextmanager
async def lifespan(app):
    yield
    tracer.shutdown()
    logger_provider.shutdown()
    meter_provider.shutdown()


app = FastAPI(lifespan=lifespan)


@app.middleware('http')
async def monitor(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    latency.record(ms, {'route': request.url.path})
    counter.add(1, {'status': response.status_code})
    print(json.dumps({'service': SERVICE, 'path': request.url.path, 'status': response.status_code, 'duration_ms': ms}), flush=True)
    return response


@app.get('/health')
def health():
    return {'ok': True, 'service': SERVICE}


async def call(service, path):
    # Fixed internal destinations only; no arbitrary URLs accepted from users.
    port = os.getenv('DEMO_' + service.upper() + '_URL', f'http://demo-{service}:8000')
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(port + path)
        response.raise_for_status()
        return response.json()


@app.get('/browse')
async def browse():
    if SERVICE != 'gateway':
        raise HTTPException(404)
    return {'items': ['fictional-widget'], 'environment': 'local-demo'}


@app.get('/login')
async def login(fail: bool = False, account: str = 'demo-user'):
    if SERVICE == 'gateway':
        return await call('auth', '/login?fail=' + str(fail).lower())
    if SERVICE != 'auth':
        raise HTTPException(404)
    # No passwords are collected. The failure switch is a safe local simulation.
    audit_logger.info('Authentication audit', extra={'event.kind': 'auth', 'account': 'demo-user', 'source': 'local-workload', 'outcome': 'failure' if fail else 'success'})
    return {'success': not fail, 'fictional': True}


@app.get('/orders')
async def orders():
    if SERVICE == 'gateway':
        return await call('orders', '/orders')
    if SERVICE != 'orders':
        raise HTTPException(404)
    return {'order': 'fictional-order', 'inventory': await call('inventory', '/inventory'), 'payment': await call('payments', '/pay')}


@app.get('/inventory')
def inventory():
    if SERVICE != 'inventory':
        raise HTTPException(404)
    return {'available': 100, 'fictional': True}


@app.get('/pay')
def pay():
    if SERVICE != 'payments':
        raise HTTPException(404)
    return {'transaction': 'fictional-only', 'status': 'simulated', 'charged': False}


@app.get('/slow')
async def slow():
    await asyncio.sleep(0.4)
    raise HTTPException(503, 'Controlled local service error')


FastAPIInstrumentor.instrument_app(app, excluded_urls='health')
