import argparse
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from prices import FUEL_TYPES, VN, fetch_prices

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('FUEL_DB', ROOT / 'data' / 'fuel.sqlite3'))
SYNC_LOCK = threading.Lock()
ORDER = "filled_on, COALESCE(filled_time, '23:59'), COALESCE(odometer_tenths, 999999999), id"
LOG_SCHEMA = '''CREATE TABLE fuel_logs (
 id INTEGER PRIMARY KEY, vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
 filled_on TEXT NOT NULL, filled_time TEXT, odometer_tenths INTEGER,
 total_cost_vnd INTEGER NOT NULL, unit_price_vnd_per_liter TEXT NOT NULL,
 volume_liters TEXT NOT NULL, volume_source TEXT NOT NULL DEFAULT 'calculated',
 is_full_tank TEXT NOT NULL DEFAULT 'unknown', notes TEXT NOT NULL DEFAULT '',
 price_id INTEGER REFERENCES fuel_prices(id), price_source TEXT NOT NULL DEFAULT 'legacy',
 fuel_type TEXT NOT NULL DEFAULT 'E10 RON 95-III', price_zone INTEGER NOT NULL DEFAULT 1,
 odo_source TEXT NOT NULL DEFAULT 'manual', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''

@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS vehicles (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, license_plate TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS fuel_prices (
          id INTEGER PRIMARY KEY, fuel_type TEXT NOT NULL, price_zone INTEGER NOT NULL,
          effective_at TEXT NOT NULL, unit_price_vnd INTEGER NOT NULL CHECK(unit_price_vnd > 0),
          source TEXT NOT NULL, source_url TEXT NOT NULL DEFAULT '', source_updated_at TEXT,
          fetched_at TEXT NOT NULL, UNIQUE(fuel_type,price_zone,effective_at,source));
        CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        db.execute('BEGIN')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(vehicles)')}
        for name, definition in [('fuel_type', "TEXT NOT NULL DEFAULT 'E10 RON 95-III'"), ('price_zone', 'INTEGER NOT NULL DEFAULT 1'), ('city', "TEXT NOT NULL DEFAULT 'Đà Nẵng'"), ('tank_capacity_liters', "TEXT NOT NULL DEFAULT '4'")]:
            if name not in columns:
                db.execute(f'ALTER TABLE vehicles ADD COLUMN {name} {definition}')
        old_columns = [r['name'] for r in db.execute('PRAGMA table_info(fuel_logs)')]
        if not old_columns:
            db.execute(LOG_SCHEMA)
        elif 'price_id' not in old_columns:
            db.execute('ALTER TABLE fuel_logs RENAME TO fuel_logs_v1')
            db.execute(LOG_SCHEMA)
            names = ','.join(old_columns)
            db.execute(f'INSERT INTO fuel_logs({names}) SELECT {names} FROM fuel_logs_v1')
            db.execute('DROP TABLE fuel_logs_v1')
        db.execute('CREATE INDEX IF NOT EXISTS fuel_history ON fuel_logs(vehicle_id,filled_on,filled_time)')
        db.execute('CREATE INDEX IF NOT EXISTS price_history ON fuel_prices(fuel_type,price_zone,effective_at)')

def number(value, label, minimum=Decimal('0.000001'), maximum=Decimal('1000000000')):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(label + ' không hợp lệ.')
    if not result.is_finite() or not minimum <= result <= maximum:
        raise ValueError(label + ' nằm ngoài khoảng hợp lệ.')
    return result

def decimal_text(value):
    return str(value.quantize(Decimal('.000001'), rounding=ROUND_HALF_UP))

def now_text():
    return datetime.now(VN).isoformat(timespec='seconds')

def set_meta(db, key, value):
    db.execute('INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

def put_price(db, row):
    fuel, zone = row['fuel_type'], int(row['price_zone'])
    if fuel not in FUEL_TYPES or zone not in (1, 2):
        raise ValueError('Loại xăng hoặc vùng giá không hợp lệ.')
    effective = datetime.fromisoformat(row['effective_at'])
    if not effective.tzinfo:
        effective = effective.replace(tzinfo=VN)
    value = number(row['unit_price_vnd'], 'Đơn giá', Decimal(1000), Decimal(100000))
    if value != value.to_integral_value():
        raise ValueError('Đơn giá phải là số đồng nguyên.')
    db.execute('''INSERT INTO fuel_prices(fuel_type,price_zone,effective_at,unit_price_vnd,source,source_url,source_updated_at,fetched_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(fuel_type,price_zone,effective_at,source) DO UPDATE SET
        unit_price_vnd=excluded.unit_price_vnd,source_updated_at=excluded.source_updated_at,fetched_at=excluded.fetched_at''',
        (fuel, zone, effective.astimezone(VN).isoformat(timespec='minutes'), int(value), row['source'], row.get('source_url', ''), row.get('source_updated_at'), now_text()))

def sync_prices():
    if not SYNC_LOCK.acquire(blocking=False):
        raise ValueError('Đang cập nhật giá, vui lòng chờ một chút.')
    try:
        rows = fetch_prices()
        with connect() as db:
            for row in rows:
                put_price(db, row)
            set_meta(db, 'price_sync_at', now_text())
            set_meta(db, 'price_sync_error', '')
        return len(rows)
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = 'Chưa cập nhật được giá Petrolimex. Giá đã lưu vẫn được giữ; bạn có thể bổ sung giá thủ công.'
        with connect() as db:
            set_meta(db, 'price_sync_error', message)
        raise ValueError(message) from error
    finally:
        SYNC_LOCK.release()

def auto_sync():
    while True:
        try:
            sync_prices()
        except ValueError as error:
            print(str(error), flush=True)
        threading.Event().wait(6 * 60 * 60)

def vehicle_by_id(db, vehicle_id):
    row = db.execute('SELECT * FROM vehicles WHERE id=?', (int(vehicle_id),)).fetchone()
    if row is None:
        raise ValueError('Xe không tồn tại.')
    return row

def quote(db, vehicle_id, filled_on, filled_time=None):
    vehicle = vehicle_by_id(db, vehicle_id)
    day = date.fromisoformat(filled_on).isoformat()
    clock = time.fromisoformat(filled_time).strftime('%H:%M') if filled_time else None
    cutoff = f'{day}T{clock or "23:59"}+07:00'
    rows = db.execute('''SELECT * FROM fuel_prices WHERE fuel_type=? AND price_zone=? AND effective_at <= ?
        ORDER BY effective_at DESC, CASE source WHEN 'manual' THEN 0 ELSE 1 END, id DESC''', (vehicle['fuel_type'], vehicle['price_zone'], cutoff)).fetchall()
    changes_today = db.execute('SELECT 1 FROM fuel_prices WHERE fuel_type=? AND price_zone=? AND substr(effective_at,1,10)=? AND substr(effective_at,12,5)>? LIMIT 1', (vehicle['fuel_type'], vehicle['price_zone'], day, '00:00')).fetchone()
    needs_time = bool(not clock and changes_today)
    selected = dict(rows[0]) if rows else None
    return {'price': selected, 'needs_time': needs_time, 'fuel_type': vehicle['fuel_type'], 'price_zone': vehicle['price_zone'], 'message': 'Ngày này có thay đổi giá. Chọn giờ đổ để áp dụng đúng đơn giá.' if needs_time else ('' if selected else 'Chưa có giá cho ngày này. Hãy cập nhật hoặc bổ sung giá đã áp dụng.')}

def save_log(db, data, log_id=None, imported=False):
    vehicle = vehicle_by_id(db, data['vehicle_id'])
    day = date.fromisoformat(data['filled_on']).isoformat()
    clock = time.fromisoformat(data['filled_time']).strftime('%H:%M') if data.get('filled_time') else None
    old = db.execute('SELECT * FROM fuel_logs WHERE id=?', (log_id,)).fetchone() if log_id else None
    if log_id and old is None:
        raise ValueError('Không tìm thấy lần đổ.')
    odo = None
    if data.get('odometer_km') not in ('', None):
        odo = number(data['odometer_km'], 'ODO', Decimal(0), Decimal('9999999')) * 10
        if odo != odo.to_integral_value():
            raise ValueError('ODO hỗ trợ tối đa một chữ số thập phân.')
        odo = int(odo)
    cost = number(data['total_cost_vnd'], 'Số tiền', Decimal(1))
    if cost != cost.to_integral_value():
        raise ValueError('Số tiền phải là số đồng nguyên.')
    price_id = None
    if imported:
        price = number(data['unit_price_vnd_per_liter'], 'Đơn giá')
        price_source, fuel, zone = 'sample', vehicle['fuel_type'], vehicle['price_zone']
    elif old and old['vehicle_id'] == vehicle['id'] and old['filled_on'] == day and old['filled_time'] == clock:
        price = Decimal(old['unit_price_vnd_per_liter'])
        price_id, price_source, fuel, zone = old['price_id'], old['price_source'], old['fuel_type'], old['price_zone']
    else:
        result = quote(db, vehicle['id'], day, clock)
        if result['needs_time'] or result['price'] is None:
            raise ValueError(result['message'])
        chosen = result['price']
        price = Decimal(chosen['unit_price_vnd'])
        price_id, price_source, fuel, zone = chosen['id'], chosen['source'], chosen['fuel_type'], chosen['price_zone']
    if odo is not None:
        others = [dict(r) for r in db.execute('SELECT * FROM fuel_logs WHERE vehicle_id=? AND id!=? AND odometer_tenths IS NOT NULL', (vehicle['id'], log_id or -1))]
        if any(r['filled_on'] == day and r['filled_time'] == clock and r['odometer_tenths'] == odo for r in others):
            raise ValueError('Đã có lần đổ cùng ngày, giờ và ODO.')
        others.append(dict(filled_on=day, filled_time=clock, odometer_tenths=odo, id=log_id or 999999999))
        others.sort(key=lambda r: (r['filled_on'], r['filled_time'] or '23:59', r['odometer_tenths'], r['id']))
        if any(a['odometer_tenths'] > b['odometer_tenths'] for a, b in zip(others, others[1:])):
            raise ValueError('ODO nhỏ hơn mốc trước hoặc lớn hơn mốc sau. Kiểm tra lại số km và ngày giờ đổ.')
    odo_source = data.get('odo_source', 'manual')
    if odo_source not in ('manual', 'photo_confirmed'):
        raise ValueError('Nguồn ODO không hợp lệ.')
    values = dict(vehicle_id=vehicle['id'], filled_on=day, filled_time=clock, odometer_tenths=odo,
        total_cost_vnd=int(cost), unit_price_vnd_per_liter=decimal_text(price), volume_liters=decimal_text(cost / price),
        volume_source='calculated', notes=str(data.get('notes', '')).strip()[:2000], price_id=price_id,
        price_source=price_source, fuel_type=fuel, price_zone=zone, odo_source=odo_source)
    if old:
        db.execute('UPDATE fuel_logs SET ' + ','.join(f'{key}=?' for key in values) + ',updated_at=CURRENT_TIMESTAMP WHERE id=?', (*values.values(), log_id))
    else:
        db.execute('INSERT INTO fuel_logs(' + ','.join(values) + ') VALUES(' + ','.join('?' for _ in values) + ')', tuple(values.values()))

SAMPLE = [('2026-06-12','14727.0',50000,22060),('2026-06-17','14898.4',50000,20750),('2026-06-23','15063.0',50000,20750),('2026-06-28','15241.3',50000,19910),('2026-07-03','15424.4',50000,20410),('2026-07-11','15605.0',50000,20000),('2026-07-19','15788.4',50000,20550),('2026-08-14','15977.9',50000,22110),('2026-08-23','16173.5',50000,22660),('2026-08-28','16329.3',50000,22660),('2026-09-03','16494.0',50000,23270),('2026-09-06','16653.1',50000,23270),('2026-09-11','16813.3',60000,24230),('2026-09-23','17054.5',60000,25630)]

def snapshot(db):
    vehicles = [dict(r) for r in db.execute('SELECT * FROM vehicles ORDER BY id')]
    logs, previous, seen = [], {}, set()
    for row in db.execute('SELECT * FROM fuel_logs ORDER BY vehicle_id,' + ORDER):
        log = dict(row)
        vehicle, odo = log['vehicle_id'], log['odometer_tenths']
        prior = previous.get(vehicle)
        log['is_baseline'] = vehicle not in seen
        log['distance_km'] = None if odo is None or prior is None else (odo - prior['odometer_tenths']) / 10
        log['distance_from_id'] = prior['id'] if prior and odo is not None else None
        log['distance_from_date'] = prior['filled_on'] if prior and odo is not None else None
        log['odometer_km'] = odo / 10 if odo is not None else None
        if odo is not None:
            previous[vehicle] = log
        seen.add(vehicle)
        logs.append(log)
    return {'vehicles': vehicles, 'logs': logs, 'prices': [dict(r) for r in db.execute('SELECT * FROM fuel_prices ORDER BY effective_at DESC,id DESC')], 'fuel_types': FUEL_TYPES, 'sync': dict(db.execute('SELECT key,value FROM metadata').fetchall())}

def save_vehicle(db, data):
    name = str(data.get('name', '')).strip()
    if not name or len(name) > 100:
        raise ValueError('Tên xe cần từ 1 đến 100 ký tự.')
    fuel, zone = data.get('fuel_type', FUEL_TYPES[0]), int(data.get('price_zone', 1))
    if fuel not in FUEL_TYPES or zone not in (1, 2):
        raise ValueError('Loại xăng hoặc vùng giá không hợp lệ.')
    values = (name, str(data.get('license_plate', '')).strip()[:30], fuel, zone, str(data.get('city', 'Đà Nẵng')).strip()[:100])
    if data.get('id'):
        vehicle_by_id(db, data['id'])
        db.execute('UPDATE vehicles SET name=?,license_plate=?,fuel_type=?,price_zone=?,city=? WHERE id=?', (*values, int(data['id'])))
    else:
        db.execute('INSERT INTO vehicles(name,license_plate,fuel_type,price_zone,city) VALUES(?,?,?,?,?)', values)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)

    def respond(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        route = urlsplit(self.path)
        try:
            with connect() as db:
                if route.path == '/api/state':
                    return self.respond(snapshot(db))
                if route.path == '/api/quote':
                    params = {k: v[0] for k, v in parse_qs(route.query).items()}
                    return self.respond(quote(db, params['vehicle_id'], params['filled_on'], params.get('filled_time')))
            if route.path.startswith('/api/'):
                return self.respond({'error': 'Không tìm thấy API.'}, 404)
            super().do_GET()
        except (ValueError, KeyError, TypeError) as error:
            self.respond({'error': str(error)}, 400)

    def do_POST(self):
        try:
            origin = self.headers.get('Origin')
            if origin and origin not in ('http://' + self.headers.get('Host', ''), 'https://' + self.headers.get('Host', '')):
                return self.respond({'error': 'Origin không hợp lệ.'}, 403)
            size = int(self.headers.get('Content-Length', 0))
            if size < 0 or size > 20000:
                raise ValueError('Dữ liệu quá lớn.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Dữ liệu không hợp lệ.')
            if self.path == '/api/prices/sync':
                sync_prices()
            else:
                with connect() as db:
                    if self.path == '/api/vehicles':
                        save_vehicle(db, data)
                    elif self.path == '/api/logs':
                        save_log(db, data, int(data['id']) if data.get('id') else None)
                    elif self.path == '/api/logs/delete':
                        db.execute('DELETE FROM fuel_logs WHERE id=?', (int(data['id']),))
                    elif self.path == '/api/prices':
                        put_price(db, {**data, 'source': 'manual', 'source_url': '', 'source_updated_at': None})
                    elif self.path == '/api/sample':
                        if db.execute("SELECT id FROM vehicles WHERE name='Xe mẫu · dữ liệu từ ảnh'").fetchone():
                            raise ValueError('Dữ liệu mẫu đã được thêm.')
                        vehicle_id = db.execute("INSERT INTO vehicles(name) VALUES('Xe mẫu · dữ liệu từ ảnh')").lastrowid
                        for day, odo, cost, price in SAMPLE:
                            save_log(db, dict(vehicle_id=vehicle_id, filled_on=day, odometer_km=odo, total_cost_vnd=cost, unit_price_vnd_per_liter=price), imported=True)
                    else:
                        return self.respond({'error': 'Không tìm thấy API.'}, 404)
            with connect() as db:
                self.respond(snapshot(db))
        except (ValueError, KeyError, TypeError, OverflowError, InvalidOperation) as error:
            self.respond({'error': str(error)}, 400)
        except sqlite3.Error:
            self.respond({'error': 'Không thể lưu dữ liệu. Vui lòng thử lại.'}, 500)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8000')))
    parser.add_argument('--no-auto-sync', action='store_true')
    parser.add_argument('--sync-prices', action='store_true')
    args = parser.parse_args()
    initialize()
    if args.sync_prices:
        print(f'Saved {sync_prices()} prices.')
    else:
        if not args.no_auto_sync:
            threading.Thread(target=auto_sync, daemon=True).start()
        print(f'Fuel app: http://{args.host}:{args.port}', flush=True)
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
