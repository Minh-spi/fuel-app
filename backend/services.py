from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from backend.db import connect
from backend.serialization import serialize
from prices import FUEL_TYPES, VN, fetch_prices

ORDER = "filled_on, COALESCE(filled_time, TIME '23:59'), COALESCE(odometer_tenths, 999999999), id"

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
    db.execute('INSERT INTO metadata(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

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
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(fuel_type,price_zone,effective_at,source) DO UPDATE SET
        unit_price_vnd=excluded.unit_price_vnd,source_updated_at=excluded.source_updated_at,fetched_at=excluded.fetched_at''',
        (fuel, zone, effective.astimezone(VN).isoformat(timespec='minutes'), int(value), row['source'], row.get('source_url', ''), row.get('source_updated_at'), now_text()))

def vehicle_by_id(db, vehicle_id):
    row = db.execute('SELECT * FROM vehicles WHERE id=%s', (int(vehicle_id),)).fetchone()
    if row is None:
        raise ValueError('Xe không tồn tại.')
    return row

def quote(db, vehicle_id, filled_on, filled_time=None):
    vehicle = vehicle_by_id(db, vehicle_id)
    day = date.fromisoformat(filled_on) if isinstance(filled_on, str) else filled_on
    clock = time.fromisoformat(filled_time) if isinstance(filled_time, str) and filled_time else (filled_time or None)
    if clock:
        clock = clock.replace(second=0, microsecond=0, tzinfo=None)
    start = datetime.combine(day, time.min, VN)
    cutoff = datetime.combine(day, clock or time(23, 59), VN)
    row = db.execute("""SELECT * FROM fuel_prices WHERE fuel_type=%s AND price_zone=%s AND effective_at <= %s
        ORDER BY effective_at DESC, CASE source WHEN 'manual' THEN 0 ELSE 1 END, id DESC LIMIT 1""",
        (vehicle['fuel_type'], vehicle['price_zone'], cutoff)).fetchone()
    changes = db.execute("""SELECT 1 FROM fuel_prices WHERE fuel_type=%s AND price_zone=%s
        AND effective_at > %s AND effective_at < %s LIMIT 1""",
        (vehicle['fuel_type'], vehicle['price_zone'], start, start + timedelta(days=1))).fetchone()
    needs_time = bool(not clock and changes)
    return {'price': dict(row) if row else None, 'needs_time': needs_time,
        'fuel_type': vehicle['fuel_type'], 'price_zone': vehicle['price_zone'],
        'message': 'Ngày này có thay đổi giá. Chọn giờ đổ để áp dụng đúng đơn giá.' if needs_time else
        ('' if row else 'Chưa có giá cho ngày này. Hãy cập nhật hoặc bổ sung giá đã áp dụng.')}

def save_log(db, data, log_id=None, imported=False):
    # Serialize writes for a vehicle before reading/validating its ODO history.
    target_id = int(data['vehicle_id'])
    initial = db.execute('SELECT vehicle_id FROM fuel_logs WHERE id=%s', (log_id,)).fetchone() if log_id else None
    ids = sorted({target_id, initial['vehicle_id']} if initial else {target_id})
    for vehicle_id in ids:
        db.execute('SELECT id FROM vehicles WHERE id=%s FOR UPDATE', (vehicle_id,)).fetchone()
    vehicle = vehicle_by_id(db, target_id)
    day = date.fromisoformat(data['filled_on'])
    clock = time.fromisoformat(data['filled_time']).replace(second=0, microsecond=0, tzinfo=None) if data.get('filled_time') else None
    old = db.execute('SELECT * FROM fuel_logs WHERE id=%s', (log_id,)).fetchone() if log_id else None
    if old and initial and old['vehicle_id'] != initial['vehicle_id']:
        raise ValueError('Lần đổ vừa được thay đổi. Hãy tải lại và thử lại.')
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
        others = [dict(r) for r in db.execute('SELECT * FROM fuel_logs WHERE vehicle_id=%s AND id!=%s AND odometer_tenths IS NOT NULL', (vehicle['id'], log_id or -1))]
        if any(r['filled_on'] == day and r['filled_time'] == clock and r['odometer_tenths'] == odo for r in others):
            raise ValueError('Đã có lần đổ cùng ngày, giờ và ODO.')
        others.append(dict(filled_on=day, filled_time=clock, odometer_tenths=odo, id=log_id or 999999999))
        others.sort(key=lambda r: (r['filled_on'], r['filled_time'] or time(23, 59), r['odometer_tenths'], r['id']))
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
        db.execute('UPDATE fuel_logs SET ' + ','.join(f'{key}=%s' for key in values) + ',updated_at=CURRENT_TIMESTAMP WHERE id=%s', (*values.values(), log_id))
    else:
        db.execute('INSERT INTO fuel_logs(' + ','.join(values) + ') VALUES(' + ','.join('%s' for _ in values) + ')', tuple(values.values()))

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
    return serialize({'vehicles': vehicles, 'logs': logs, 'prices': [dict(r) for r in db.execute('SELECT * FROM fuel_prices ORDER BY effective_at DESC,id DESC')], 'fuel_types': FUEL_TYPES, 'sync': {r['key']: r['value'] for r in db.execute('SELECT key,value FROM metadata')}})

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
        db.execute('UPDATE vehicles SET name=%s,license_plate=%s,fuel_type=%s,price_zone=%s,city=%s WHERE id=%s', (*values, int(data['id'])))
    else:
        db.execute('INSERT INTO vehicles(name,license_plate,fuel_type,price_zone,city) VALUES(%s,%s,%s,%s,%s)', values)

def delete_log(db, log_id):
    initial = db.execute('SELECT vehicle_id FROM fuel_logs WHERE id=%s', (log_id,)).fetchone()
    if initial:
        db.execute('SELECT id FROM vehicles WHERE id=%s FOR UPDATE', (initial['vehicle_id'],)).fetchone()
        current = db.execute('SELECT vehicle_id FROM fuel_logs WHERE id=%s', (log_id,)).fetchone()
        if current and current['vehicle_id'] != initial['vehicle_id']:
            raise ValueError('Lần đổ vừa được thay đổi. Hãy tải lại và thử lại.')
        db.execute('DELETE FROM fuel_logs WHERE id=%s', (log_id,))

def add_sample(db):
    # Transaction-scoped advisory lock works with transaction pooling.
    db.execute('SELECT pg_advisory_xact_lock(721604, 1)')
    name = 'Xe mẫu · dữ liệu từ ảnh'
    if db.execute('SELECT id FROM vehicles WHERE name=%s', (name,)).fetchone():
        raise ValueError('Dữ liệu mẫu đã được thêm.')
    vehicle_id = db.execute('INSERT INTO vehicles(name) VALUES(%s) RETURNING id', (name,)).fetchone()['id']
    for day, odo, cost, price in SAMPLE:
        save_log(db, dict(vehicle_id=vehicle_id, filled_on=day, odometer_km=odo,
            total_cost_vnd=cost, unit_price_vnd_per_liter=price), imported=True)

def acquire_sync_lock():
    token = uuid4()
    with connect() as db:
        row = db.execute("""INSERT INTO app_locks(name,token,expires_at)
            VALUES('price_sync',%s,clock_timestamp() + INTERVAL '90 seconds')
            ON CONFLICT(name) DO UPDATE SET token=excluded.token,expires_at=excluded.expires_at
            WHERE app_locks.expires_at <= clock_timestamp() RETURNING token""", (token,)).fetchone()
        if row is None:
            raise ValueError('Đang cập nhật giá, vui lòng chờ một chút.')
    return token

def owns_sync_lock(db, token):
    return db.execute("""SELECT token FROM app_locks WHERE name='price_sync'
        AND token=%s AND expires_at > clock_timestamp() FOR UPDATE""", (token,)).fetchone() is not None

def sync_prices():
    token = acquire_sync_lock()
    try:
        rows = fetch_prices()
        with connect() as db:
            if not owns_sync_lock(db, token):
                raise ValueError('Lượt cập nhật đã hết hạn, vui lòng thử lại.')
            for row in rows:
                put_price(db, row)
            set_meta(db, 'price_sync_at', now_text())
            set_meta(db, 'price_sync_error', '')
        return len(rows)
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = 'Chưa cập nhật được giá Petrolimex. Giá đã lưu vẫn được giữ; bạn có thể bổ sung giá thủ công.'
        with connect() as db:
            if owns_sync_lock(db, token):
                set_meta(db, 'price_sync_error', message)
        raise ValueError(message) from error
    finally:
        with connect() as db:
            db.execute("DELETE FROM app_locks WHERE name='price_sync' AND token=%s", (token,))

