"""Read-only SQLite import. Dry-run by default; only --apply commits to an EMPTY target."""
import argparse
from contextlib import closing
import json
import os
import sqlite3
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from backend.db import connect
from backend import services
from prices import VN

TABLES = ('vehicles', 'fuel_prices', 'fuel_logs', 'metadata')
DATE_FIELDS = {'filled_on'}
TIME_FIELDS = {'filled_time'}
STAMP_FIELDS = {'created_at', 'updated_at', 'effective_at', 'source_updated_at', 'fetched_at'}
NUMERIC_FIELDS = {'tank_capacity_liters', 'unit_price_vnd_per_liter', 'volume_liters'}
DEFAULTS = {
    'vehicles': dict(fuel_type='E10 RON 95-III', price_zone=1, city='Đà Nẵng', tank_capacity_liters='4'),
    'fuel_logs': dict(filled_time=None, price_id=None, price_source='legacy', fuel_type='E10 RON 95-III', price_zone=1, odo_source='manual'),
}

def normalize(key, value):
    if value is None:
        return None
    if key in DATE_FIELDS:
        return date.fromisoformat(value)
    if key in TIME_FIELDS:
        return time.fromisoformat(value)
    if key in STAMP_FIELDS:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # SQLite CURRENT_TIMESTAMP is UTC. Price dates without an offset are Vietnam time.
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc if key in ('created_at', 'updated_at') else VN)
    if key in NUMERIC_FIELDS:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError(f'Non-finite value in {key}.')
        return result
    return value

def read_source(path):
    path = Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('BEGIN')
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed.')
        if source.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('SQLite foreign key check failed.')
        names = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'vehicles','fuel_logs'} <= names:
            raise ValueError('Missing vehicles/fuel_logs in source.')
        rows = {}
        for table in TABLES:
            rows[table] = [{k: normalize(k, v) for k, v in {**DEFAULTS.get(table, {}), **dict(row)}.items()}
                for row in source.execute(f'SELECT * FROM {table} ORDER BY {"key" if table == "metadata" else "id"}')] if table in names else []
        source.rollback()
    return rows

def summaries(rows):
    totals = {}
    for vehicle in rows['vehicles']:
        logs = sorted((r for r in rows['fuel_logs'] if r['vehicle_id']==vehicle['id']),
            key=lambda r:(r['filled_on'],r['filled_time'] or time(23,59),r['odometer_tenths'] if r['odometer_tenths'] is not None else 999999999,r['id']))
        odos = [r['odometer_tenths'] for r in logs if r['odometer_tenths'] is not None]
        totals[str(vehicle['id'])] = dict(logs=len(logs),cost=sum(r['total_cost_vnd'] for r in logs),
            liters=str(sum((r['volume_liters'] for r in logs),Decimal(0))),
            distance_tenths=odos[-1]-odos[0] if len(odos)>1 else 0,baseline_id=logs[0]['id'] if logs else None)
    return {'counts':{t:len(rows[t]) for t in TABLES},'vehicles':totals}

def convert_rows(rows, fuels):
    """Translate legacy SQLite records without recalculating historical money/volume."""
    result={t:[] for t in ('vehicles','fuel_prices','refueling_logs','app_metadata')}
    for table in TABLES:
        for original in rows[table]:
            row=dict(original)
            if table=='vehicles':
                row['id']='V'+str(row['id'])
                row['default_fuel_type_id']=fuels[row.pop('fuel_type')]
                row['license_plate']=row.get('license_plate') or None
                row['updated_at']=row['created_at']
            elif table=='fuel_prices':
                row['id']='P'+str(row['id'])
                row['fuel_type_id']=fuels[row.pop('fuel_type')]
                source=row.pop('source')
                row['source_url']='manual' if source=='manual' else row['source_url'] or 'https://www.petrolimex.com.vn/'
                row['unit_price_vnd_per_liter']=row.pop('unit_price_vnd')
                row['created_at']=row['updated_at']=row.pop('fetched_at')
            elif table=='fuel_logs':
                row['id']='R'+str(row['id'])
                row['vehicle_id']='V'+str(row['vehicle_id'])
                row['fuel_type_id']=fuels[row.pop('fuel_type')]
                row['fuel_price_id']='P'+str(row.pop('price_id')) if row.get('price_id') is not None else None
                row.pop('price_id',None)
                row['refueled_on']=row.pop('filled_on')
                row['refueled_time']=row.pop('filled_time')
                for key in ('volume_source','is_full_tank','price_source'):row.pop(key,None)
            target={'fuel_logs':'refueling_logs','metadata':'app_metadata'}.get(table,table)
            result[target].append(row)
    return result

def import_sqlite(path, url, apply=False):
    original=read_source(path)
    source_summary=summaries(original)
    with connect(url,migration=True) as db:
        db.execute('LOCK TABLE vehicles,fuel_prices,refueling_logs,app_metadata,fuel_types IN ACCESS EXCLUSIVE MODE')
        targets=('vehicles','fuel_prices','refueling_logs','app_metadata')
        for table in targets:
            if db.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(sql.Identifier(table))).fetchone():
                raise ValueError('Target must be empty. No data was overwritten.')
        fuels={r['name']:r['id'] for r in db.execute('SELECT id,name FROM fuel_types')}
        for table in TABLES[:3]:
            for row in original[table]:
                name=row['fuel_type']
                if name not in fuels:
                    record=db.execute("INSERT INTO fuel_types(code,name,category) VALUES('LEGACY_'||md5(%s),%s,'other') RETURNING id",(name,name)).fetchone()
                    fuels[name]=record['id']
        rows=convert_rows(original,fuels)
        for table in targets:
            for row in rows[table]:
                query=sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),
                    sql.SQL(',').join(map(sql.Identifier,row)),sql.SQL(',').join(sql.Placeholder() for _ in row))
                db.execute(query,tuple(row.values()))
        for table in targets:
            actual=list(db.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))))
            key='key' if table=='app_metadata' else 'id'
            by_id={r[key]:r for r in actual}
            if len(actual)!=len(rows[table]):raise ValueError('Count mismatch: '+table)
            for row in rows[table]:
                if any(by_id[row[key]][k]!=v for k,v in row.items()):raise ValueError('Value mismatch: '+table)
        state=services.snapshot(db)
        for vehicle_id,expected in source_summary['vehicles'].items():
            logs=[l for l in state['logs'] if l['vehicle_id']=='V'+vehicle_id]
            if round(sum(l['distance_km'] or 0 for l in logs)*10)!=expected['distance_tenths']:
                raise ValueError('Distance mismatch: '+vehicle_id)
        if apply:
            for table in targets[:3]:
                maximum=max((int(r['id'][1:]) for r in rows[table]),default=0)
                seq=table+'_id_seq'
                last=db.execute(sql.SQL('SELECT last_value,is_called FROM fuel_app.{}').format(sql.Identifier(seq))).fetchone()
                next_id=max(maximum+1,last['last_value']+int(last['is_called']))
                db.execute(sql.SQL('ALTER SEQUENCE fuel_app.{} RESTART WITH {}').format(sql.Identifier(seq),sql.Literal(next_id)))
        else:db.rollback()
    return {**source_summary,'applied':apply,'verified_all_fields':True}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='note/data/fuel.sqlite3')
    parser.add_argument('--apply', action='store_true', help='Commit into an empty target after full verification.')
    parser.add_argument('--audit-only', action='store_true', help='Inspect SQLite without connecting to PostgreSQL.')
    args=parser.parse_args()
    try:
        if args.audit_only:
            result=summaries(read_source(args.source))
        else:
            url=os.environ.get('MIGRATION_DATABASE_URL')
            if not url:
                raise ValueError('Set MIGRATION_DATABASE_URL; use --audit-only to inspect SQLite offline.')
            result=import_sqlite(args.source,url,args.apply)
        print(json.dumps(result,ensure_ascii=True,indent=2))
    except (ValueError, OSError, sqlite3.Error, psycopg.Error) as error:
        # Don't echo database error strings that can contain credentials/record contents.
        print(f'Import failed ({type(error).__name__}). Destination transaction rolled back; source is read-only.',file=sys.stderr)
        if isinstance(error,ValueError):print(str(error),file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':main()
