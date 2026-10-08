"""Vercel Flask entrypoint. No database or network activity at import time."""
import json
import os
from decimal import InvalidOperation
from urllib.parse import urlsplit
from flask import Flask, request, Response, send_from_directory
from werkzeug.exceptions import HTTPException
import psycopg
from backend.config import ROOT
from backend.db import connect, ConfigurationError
from backend.serialization import serialize
from backend import services
from backend.diagnostics import database_problem, check_database

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 20000

def respond(data, status=200):
    return Response(json.dumps(serialize(data), ensure_ascii=False), status=status,
        content_type='application/json; charset=utf-8', headers={'Cache-Control': 'no-store'})

@app.before_request
def validate_origin():
    if request.method != 'POST' or not request.path.startswith('/api/'):
        return None
    origin = request.headers.get('Origin')
    allowed = os.environ.get('APP_ORIGIN', '').rstrip('/')
    if origin:
        parsed = urlsplit(origin)
        # Vercel/preview host may differ from the configured production origin.
        same_host = parsed.scheme in ('http', 'https') and parsed.netloc == request.host and not parsed.path
        if origin.rstrip('/') != allowed and not same_host:
            return respond({'error': 'Origin không hợp lệ.'}, 403)

def read_data():
    # Keep compatibility with the original server, including JSON bodies without a content-type.
    try:
        data = json.loads(request.get_data())
    except (ValueError, UnicodeError):
        raise ValueError('Dữ liệu JSON không hợp lệ.')
    if not isinstance(data, dict):
        raise ValueError('Dữ liệu không hợp lệ.')
    return data

@app.get('/api/state')
def state():
    with connect(readonly=True) as db:
        return respond(services.snapshot(db))

@app.get('/api/health')
def health():
    return respond(check_database())

@app.get('/api/quote')
def quote():
    with connect(readonly=True) as db:
        return respond(services.quote(db, request.args['vehicle_id'], request.args['refueled_on'], request.args.get('refueled_time'), request.args.get('fuel_type_id')))

def mutate(action):
    data = read_data()
    with connect() as db:
        action(db, data)
    with connect(readonly=True) as db:
        return respond(services.snapshot(db))

@app.post('/api/vehicles')
def vehicles():
    return mutate(services.save_vehicle)

@app.post('/api/logs')
def logs():
    return mutate(lambda db, data: services.save_log(db, data, data.get('id') or None))

@app.post('/api/logs/delete')
def delete_log():
    return mutate(lambda db, data: services.delete_log(db, data['id']))

@app.post('/api/prices')
def prices():
    return mutate(lambda db, data: services.put_price(db, {**data, 'source_url':'manual', 'source_updated_at':None}))

@app.post('/api/prices/sync')
def sync():
    read_data()
    services.sync_prices()
    with connect(readonly=True) as db:
        return respond(services.snapshot(db))

@app.post('/api/sample')
def sample():
    return mutate(lambda db, data: services.add_sample(db))

@app.get('/')
def home():
    return send_from_directory(ROOT / 'public', 'index.html')

@app.get('/<path:filename>')
def local_static(filename):
    # Vercel serves existing public/** assets via CDN; this also supports python server.py.
    if filename.startswith('api/'):
        return respond({'error':'Không tìm thấy API.'}, 404)
    return send_from_directory(ROOT / 'public', filename)

def validation_error(error):
    return respond({'error': str(error)}, 400)

for exception in (ValueError, KeyError, TypeError, OverflowError, InvalidOperation):
    app.register_error_handler(exception, validation_error)

@app.errorhandler(ConfigurationError)
def configuration_error(error):
    code, message = database_problem(error)
    return respond({'error': message, 'code': code}, 503)

@app.errorhandler(psycopg.Error)
def database_error(error):
    # Never include a DSN, SQL parameters, or PostgreSQL error details in responses/logs.
    app.logger.error('Database operation failed (%s).', type(error).__name__)
    code, message = database_problem(error)
    return respond({'error':message, 'code':code}, 500 if code == 'database_operation' else 503)

@app.errorhandler(HTTPException)
def http_error(error):
    messages = {400:'Dữ liệu không hợp lệ.', 404:'Không tìm thấy API.', 405:'Phương thức không hợp lệ.', 413:'Dữ liệu quá lớn.'}
    return respond({'error':messages.get(error.code, 'Không thể xử lý yêu cầu.')}, error.code)
