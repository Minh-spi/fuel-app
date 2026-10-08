from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
import re
from urllib.parse import urlsplit
from backend.db import connect
from backend.serialization import serialize
from prices import VN, FUEL_CODES, fetch_prices, PriceSourceError

ORDER = "refueled_on, COALESCE(refueled_time, TIME '23:59'), COALESCE(odometer_tenths, 999999999), substring(id from 2)::bigint"

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
    db.execute('INSERT INTO app_metadata(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

def record_id(value, prefix):
    value = str(value)
    if not re.fullmatch(prefix + r'[1-9][0-9]{0,18}', value):
        raise ValueError('ID không hợp lệ.')
    return value

def fuel_by_id(db, fuel_id):
    row = db.execute('SELECT * FROM fuel_types WHERE id=%s', (record_id(fuel_id, 'F'),)).fetchone()
    if row is None:
        raise ValueError('Loại nhiên liệu không tồn tại.')
    return row

def put_price(db, row):
    fuel = fuel_by_id(db, row['fuel_type_id'])
    zone = int(row['price_zone'])
    if zone not in (1, 2):
        raise ValueError('Vùng giá không hợp lệ.')
    effective = datetime.fromisoformat(row['effective_at'])
    if not effective.tzinfo:
        effective = effective.replace(tzinfo=VN)
    value = number(row['unit_price_vnd_per_liter'], 'Đơn giá', Decimal(1000), Decimal(100000))
    if value != value.to_integral_value():
        raise ValueError('Đơn giá phải là số đồng nguyên.')
    source = row['source_url'].strip()
    parsed = urlsplit(source)
    if source != 'manual' and (parsed.scheme not in ('https', 'http') or not parsed.hostname or any(c.isspace() for c in source)):
        raise ValueError('Nguồn giá phải là manual hoặc URL http/https.')
    db.execute("""INSERT INTO fuel_prices(fuel_type_id,price_zone,effective_at,unit_price_vnd_per_liter,source_url,source_updated_at)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(fuel_type_id,price_zone,effective_at,source_url) DO UPDATE SET
        unit_price_vnd_per_liter=excluded.unit_price_vnd_per_liter,source_updated_at=excluded.source_updated_at,updated_at=now()""",
        (fuel['id'],zone,effective.replace(second=0,microsecond=0),int(value),source,row.get('source_updated_at')))

def vehicle_by_id(db, vehicle_id):
    row = db.execute('SELECT * FROM vehicles WHERE id=%s', (record_id(vehicle_id, 'V'),)).fetchone()
    if row is None:
        raise ValueError('Xe không tồn tại.')
    return row

def quote(db, vehicle_id, refueled_on, refueled_time=None, fuel_type_id=None):
    vehicle = vehicle_by_id(db, vehicle_id)
    fuel_id = fuel_type_id or vehicle['default_fuel_type_id']
    fuel_by_id(db, fuel_id)
    day = date.fromisoformat(refueled_on) if isinstance(refueled_on, str) else refueled_on
    clock = time.fromisoformat(refueled_time) if isinstance(refueled_time, str) and refueled_time else (refueled_time or None)
    if clock:
        clock = clock.replace(second=0, microsecond=0, tzinfo=None)
    start = datetime.combine(day, time.min, VN)
    cutoff = datetime.combine(day, clock or time(23, 59), VN)
    row = db.execute("""SELECT * FROM fuel_prices WHERE fuel_type_id=%s AND price_zone=%s AND effective_at <= %s
        ORDER BY effective_at DESC, CASE source_url WHEN 'manual' THEN 0 ELSE 1 END, updated_at DESC, substring(id from 2)::bigint DESC LIMIT 1""",
        (fuel_id, vehicle['price_zone'], cutoff)).fetchone()
    changes = db.execute("""SELECT 1 FROM fuel_prices WHERE fuel_type_id=%s AND price_zone=%s
        AND effective_at > %s AND effective_at < %s LIMIT 1""",
        (fuel_id, vehicle['price_zone'], start, start + timedelta(days=1))).fetchone()
    needs_time = bool(not clock and changes)
    return {'price': dict(row) if row else None, 'needs_time': needs_time,
        'fuel_type_id': fuel_id, 'price_zone': vehicle['price_zone'],
        'message': 'Ngày này có thay đổi giá. Chọn giờ đổ để áp dụng đúng đơn giá.' if needs_time else
        ('' if row else 'Chưa có giá cho ngày này. Hãy cập nhật hoặc bổ sung giá đã áp dụng.')}

def save_log(db, data, log_id=None, imported=False):
    # Serialize writes for a vehicle before reading/validating its ODO history.
    target_id = record_id(data['vehicle_id'], 'V')
    log_id = record_id(log_id, 'R') if log_id else None
    initial = db.execute('SELECT vehicle_id FROM refueling_logs WHERE id=%s', (log_id,)).fetchone() if log_id else None
    ids = sorted({target_id, initial['vehicle_id']} if initial else {target_id})
    for vehicle_id in ids:
        db.execute('SELECT id FROM vehicles WHERE id=%s FOR UPDATE', (vehicle_id,)).fetchone()
    vehicle = vehicle_by_id(db, target_id)
    day = date.fromisoformat(data['refueled_on'])
    clock = time.fromisoformat(data['refueled_time']).replace(second=0, microsecond=0, tzinfo=None) if data.get('refueled_time') else None
    old = db.execute('SELECT * FROM refueling_logs WHERE id=%s', (log_id,)).fetchone() if log_id else None
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
    requested_fuel = data.get('fuel_type_id')
    if requested_fuel in ('', None):
        requested_fuel = old['fuel_type_id'] if old else vehicle['default_fuel_type_id']
    requested_fuel = fuel_by_id(db, requested_fuel)['id']
    fuel_price_id = None
    if imported:
        price = number(data['unit_price_vnd_per_liter'], 'Đơn giá')
        fuel, zone = requested_fuel, vehicle['price_zone']
    elif old and old['vehicle_id'] == vehicle['id'] and old['refueled_on'] == day and old['refueled_time'] == clock and old['fuel_type_id'] == requested_fuel:
        price = Decimal(old['unit_price_vnd_per_liter'])
        fuel_price_id, fuel, zone = old['fuel_price_id'], old['fuel_type_id'], old['price_zone']
    else:
        result = quote(db, vehicle['id'], day, clock, requested_fuel)
        if result['needs_time'] or result['price'] is None:
            raise ValueError(result['message'])
        chosen = result['price']
        price = Decimal(chosen['unit_price_vnd_per_liter'])
        fuel_price_id, fuel, zone = chosen['id'], chosen['fuel_type_id'], chosen['price_zone']
    if odo is not None:
        others = [dict(r) for r in db.execute('SELECT * FROM refueling_logs WHERE vehicle_id=%s AND id!=%s AND odometer_tenths IS NOT NULL', (vehicle['id'], log_id or ''))]
        if any(r['refueled_on'] == day and r['refueled_time'] == clock and r['odometer_tenths'] == odo for r in others):
            raise ValueError('Đã có lần đổ cùng ngày, giờ và ODO.')
        others.append(dict(refueled_on=day, refueled_time=clock, odometer_tenths=odo, id=log_id or 'R9223372036854775807'))
        others.sort(key=lambda r: (r['refueled_on'], r['refueled_time'] or time(23, 59), r['odometer_tenths'], int(r['id'][1:])))
        if any(a['odometer_tenths'] > b['odometer_tenths'] for a, b in zip(others, others[1:])):
            raise ValueError('ODO nhỏ hơn mốc trước hoặc lớn hơn mốc sau. Kiểm tra lại số km và ngày giờ đổ.')
    odo_source = data.get('odo_source', 'manual')
    if odo_source not in ('manual', 'photo_confirmed'):
        raise ValueError('Nguồn ODO không hợp lệ.')
    values = dict(vehicle_id=vehicle['id'], refueled_on=day, refueled_time=clock, odometer_tenths=odo,
        total_cost_vnd=int(cost), unit_price_vnd_per_liter=decimal_text(price), volume_liters=decimal_text(cost / price),
        notes=str(data.get('notes', '')).strip()[:2000], fuel_price_id=fuel_price_id,
        fuel_type_id=fuel, price_zone=zone, odo_source=odo_source)
    if old:
        db.execute('UPDATE refueling_logs SET ' + ','.join(f'{key}=%s' for key in values) + ',updated_at=CURRENT_TIMESTAMP WHERE id=%s', (*values.values(), log_id))
    else:
        db.execute('INSERT INTO refueling_logs(' + ','.join(values) + ') VALUES(' + ','.join('%s' for _ in values) + ')', tuple(values.values()))

SAMPLE = [('2026-06-12','14727.0',50000,22060),('2026-06-17','14898.4',50000,20750),('2026-06-23','15063.0',50000,20750),('2026-06-28','15241.3',50000,19910),('2026-07-03','15424.4',50000,20410),('2026-07-11','15605.0',50000,20000),('2026-07-19','15788.4',50000,20550),('2026-08-14','15977.9',50000,22110),('2026-08-23','16173.5',50000,22660),('2026-08-28','16329.3',50000,22660),('2026-09-03','16494.0',50000,23270),('2026-09-06','16653.1',50000,23270),('2026-09-11','16813.3',60000,24230),('2026-09-23','17054.5',60000,25630)]

def snapshot(db):
    vehicles = [dict(r) for r in db.execute('SELECT * FROM vehicles ORDER BY substring(id from 2)::bigint')]
    logs, previous, seen = [], {}, set()
    for row in db.execute('SELECT * FROM refueling_logs ORDER BY substring(vehicle_id from 2)::bigint,' + ORDER):
        log = dict(row)
        vehicle, odo = log['vehicle_id'], log['odometer_tenths']
        prior = previous.get(vehicle)
        log['is_baseline'] = vehicle not in seen
        log['distance_km'] = None if odo is None or prior is None else (odo - prior['odometer_tenths']) / 10
        log['distance_from_id'] = prior['id'] if prior and odo is not None else None
        log['distance_from_date'] = prior['refueled_on'] if prior and odo is not None else None
        log['odometer_km'] = odo / 10 if odo is not None else None
        if odo is not None:
            previous[vehicle] = log
        seen.add(vehicle)
        logs.append(log)
    prices=list(db.execute("SELECT * FROM fuel_prices ORDER BY effective_at DESC, CASE source_url WHEN 'manual' THEN 0 ELSE 1 END, updated_at DESC, substring(id from 2)::bigint DESC"))
    return serialize({'vehicles': vehicles, 'logs': logs, 'prices': prices, 'fuel_types': list(db.execute('SELECT * FROM fuel_types ORDER BY substring(id from 2)::bigint')), 'sync': {r['key']: r['value'] for r in db.execute('SELECT key,value FROM app_metadata')}})

def save_vehicle(db, data):
    old = vehicle_by_id(db, data['id']) if data.get('id') else {}
    values = {**old, **data}
    name = str(values.get('name', '')).strip()
    if not name or len(name)>100:
        raise ValueError('Tên xe cần từ 1 đến 100 ký tự.')
    fuel = fuel_by_id(db, values.get('default_fuel_type_id', 'F1'))
    if not fuel['is_active'] and old.get('default_fuel_type_id') != fuel['id']:
        raise ValueError('Loại nhiên liệu này đã ngừng sử dụng.')
    zone = int(values.get('price_zone', 1))
    if zone not in (1,2): raise ValueError('Vùng giá không hợp lệ.')
    kind=values.get('vehicle_type','unknown')
    transmission=values.get('transmission_type','unknown')
    if kind not in ('motorcycle','car','other','unknown') or transmission not in ('automatic','semi_automatic','manual','other','unknown'):
        raise ValueError('Loại xe hoặc truyền động không hợp lệ.')
    def optional_int(key, minimum, maximum):
        value=values.get(key)
        if value in ('',None): return None
        result=number(value,key,Decimal(minimum),Decimal(maximum))
        if result!=result.to_integral_value(): raise ValueError(key+' phải là số nguyên.')
        return int(result)
    capacity=values.get('tank_capacity_liters',4)
    capacity=None if capacity in ('',None) else number(capacity,'Dung tích bình',Decimal('.001'),Decimal('99999.999'))
    if capacity is not None and capacity != capacity.quantize(Decimal('.001')):
        raise ValueError('Dung tích bình hỗ trợ tối đa 3 chữ số thập phân.')
    purchased=values.get('purchased_on')
    purchased=date.fromisoformat(purchased) if isinstance(purchased,str) and purchased else purchased or None
    active=values.get('is_active',True)
    if isinstance(active,str):
        if active not in ('true','false'): raise ValueError('Trạng thái xe không hợp lệ.')
        active=active=='true'
    if not isinstance(active,bool): raise ValueError('Trạng thái xe không hợp lệ.')
    fields=dict(name=name,default_fuel_type_id=fuel['id'],price_zone=zone,vehicle_type=kind,
        transmission_type=transmission,model_year=optional_int('model_year',1886,9999),
        engine_displacement_cc=optional_int('engine_displacement_cc',1,100000),
        tank_capacity_liters=capacity,purchased_on=purchased,is_active=active)
    for key,limit in (('license_plate',30),('brand',100),('model',100),('city',100),('notes',2000)):
        value=values.get(key,'Đà Nẵng' if key=='city' else '')
        fields[key]=str(value or '').strip()[:limit] or ('' if key=='city' else None)
    if old:
        db.execute('UPDATE vehicles SET '+','.join(k+'=%s' for k in fields)+',updated_at=now() WHERE id=%s',(*fields.values(),old['id']))
    else:
        db.execute('INSERT INTO vehicles('+','.join(fields)+') VALUES('+','.join('%s' for _ in fields)+')',tuple(fields.values()))

def delete_log(db, log_id):
    log_id = record_id(log_id, 'R')
    initial = db.execute('SELECT vehicle_id FROM refueling_logs WHERE id=%s', (log_id,)).fetchone()
    if initial:
        db.execute('SELECT id FROM vehicles WHERE id=%s FOR UPDATE', (initial['vehicle_id'],)).fetchone()
        current = db.execute('SELECT vehicle_id FROM refueling_logs WHERE id=%s', (log_id,)).fetchone()
        if current and current['vehicle_id'] != initial['vehicle_id']:
            raise ValueError('Lần đổ vừa được thay đổi. Hãy tải lại và thử lại.')
        db.execute('DELETE FROM refueling_logs WHERE id=%s', (log_id,))

def add_sample(db):
    # Transaction-scoped advisory lock works with transaction pooling.
    db.execute('SELECT pg_advisory_xact_lock(721604, 1)')
    name = 'Xe mẫu · dữ liệu từ ảnh'
    if db.execute('SELECT id FROM vehicles WHERE name=%s', (name,)).fetchone():
        raise ValueError('Dữ liệu mẫu đã được thêm.')
    vehicle_id = db.execute('INSERT INTO vehicles(name) VALUES(%s) RETURNING id', (name,)).fetchone()['id']
    for day, odo, cost, price in SAMPLE:
        save_log(db, dict(vehicle_id=vehicle_id, refueled_on=day, odometer_km=odo,
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
        with connect() as db:
            if not owns_sync_lock(db,token):raise ValueError('Lượt cập nhật đã hết hạn.')
        rows = fetch_prices()
        with connect() as db:
            if not owns_sync_lock(db, token):
                raise ValueError('Lượt cập nhật đã hết hạn, vui lòng thử lại.')
            for row in rows:
                code=row.get('fuel_code') or FUEL_CODES.get(row.get('fuel_type'))
                fuel = db.execute('SELECT id FROM fuel_types WHERE code=%s',(code,)).fetchone()
                if fuel is None: raise ValueError('Nguồn trả loại nhiên liệu chưa có trong danh mục.')
                put_price(db, {**row, 'fuel_type_id':fuel['id'], 'unit_price_vnd_per_liter':row['unit_price_vnd']})
            set_meta(db, 'price_sync_at', now_text())
            set_meta(db, 'price_sync_error', '')
        return len(rows)
    except (ValueError, KeyError, TypeError, OSError) as error:
        reason=str(error) if isinstance(error,PriceSourceError) else 'Chưa cập nhật được giá Petrolimex.'
        message = reason+' Giá đã lưu vẫn được giữ; bạn có thể bổ sung giá thủ công.'
        with connect() as db:
            if owns_sync_lock(db, token):
                set_meta(db, 'price_sync_error', message)
        raise ValueError(message) from error
    finally:
        with connect() as db:
            db.execute("DELETE FROM app_locks WHERE name='price_sync' AND token=%s", (token,))

