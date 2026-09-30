import hashlib
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from db_support import reset, test_url
from backend import services
from backend.db import connect
from app import app
from fixtures import legacy_server as legacy
from scripts.migrate_sqlite_to_postgres import import_sqlite

class MigrationApiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, DATABASE_URL=test_url())
        self.env.start()
        self.addCleanup(self.env.stop)
        reset()
        self.client = app.test_client()

    def post(self, path, data):
        response = self.client.post('/api/'+path, json=data)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_all_api_routes_and_json_contract(self):
        state = self.post('vehicles', {'name':'Xe Đà Nẵng'})
        self.assertEqual(state['vehicles'][0]['tank_capacity_liters'], '4')
        self.post('prices', dict(fuel_type='E10 RON 95-III',price_zone=1,effective_at='2026-01-01T00:00',unit_price_vnd=25000))
        quote = self.client.get('/api/quote?vehicle_id=1&filled_on=2026-06-01').get_json()
        self.assertEqual(quote['price']['effective_at'], '2026-01-01T00:00+07:00')
        state = self.post('logs', dict(vehicle_id=1,filled_on='2026-06-01',filled_time='10:30',total_cost_vnd=50000,odometer_km=1000))
        log=state['logs'][0]
        self.assertEqual(log['volume_liters'],'2.000000')
        self.assertEqual(log['filled_time'],'10:30')
        self.assertIsNone(log['distance_km'])
        self.assertTrue(log['is_baseline'])
        self.assertEqual(self.client.get('/api/state').get_json(),state)
        self.assertEqual(self.post('logs/delete',{'id':log['id']})['logs'],[])
        self.assertEqual(len(self.post('sample',{})['logs']),14)
        self.assertEqual(self.client.post('/api/sample',json={}).status_code,400)
        rows=[dict(fuel_type='E10 RON 95-III',price_zone=1,effective_at='2026-09-24T15:00+07:00',unit_price_vnd=27080,source='petrolimex')]
        with patch('backend.services.fetch_prices',return_value=rows):
            state=self.post('prices/sync',{})
        self.assertEqual(state['sync']['price_sync_error'],'')
        for path in ('/', '/ocr.js'):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code,200)

    def test_invalid_requests_do_not_write(self):
        for body in ('[]','{','null'):
            self.assertEqual(self.client.post('/api/vehicles',data=body).status_code,400)
        self.assertEqual(self.client.post('/api/vehicles',json={'name':'X'},headers={'Origin':'https://foreign.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/vehicles',data='x'*20001).status_code,413)
        self.assertEqual(self.client.get('/api/not-found').status_code,404)
        self.assertEqual(self.client.get('/api/state').get_json()['vehicles'],[])

    def test_health_readonly_and_missing_schema(self):
        self.assertEqual(self.client.get('/api/health').get_json(), {'ok':True,'database':'ready'})
        with connect() as db:
            db.execute('ALTER TABLE fuel_app.metadata RENAME TO metadata_health_test')
        try:
            response=self.client.get('/api/health')
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.get_json()['code'],'database_schema')
        finally:
            with connect() as db:db.execute('ALTER TABLE fuel_app.metadata_health_test RENAME TO metadata')

    def test_import_dry_run_exact_contract_and_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.sqlite3'
            with patch.object(legacy,'DB',path):
                legacy.initialize()
                with legacy.connect() as db:
                    legacy.save_vehicle(db,{'name':'Xe tôi'})
                    legacy.put_price(db,dict(fuel_type='E10 RON 95-III',price_zone=1,effective_at='2026-01-01T00:00',unit_price_vnd=25000,source='manual'))
                    for day,odo in [('2026-06-01',None),('2026-06-02',1000),('2026-06-03',1150)]:
                        legacy.save_log(db,dict(vehicle_id=1,filled_on=day,odometer_km=odo,total_cost_vnd=50000))
                    expected=legacy.snapshot(db)
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertFalse(import_sqlite(path,test_url())['applied'])
            self.assertEqual(self.client.get('/api/state').get_json()['vehicles'],[])
            self.assertTrue(import_sqlite(path,test_url(),apply=True)['verified_all_fields'])
            actual=self.client.get('/api/state').get_json()
            # Price fetch timestamps are equivalent ISO instants; old formatter omitted zero microseconds.
            for state in (actual,expected):
                for price in state['prices']:
                    from datetime import datetime
                    price['fetched_at']=datetime.fromisoformat(price['fetched_at'])
            self.assertEqual(actual,expected)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
            self.assertEqual(self.post('vehicles',{'name':'Next'})['vehicles'][-1]['id'],2)
            with self.assertRaises(ValueError):import_sqlite(path,test_url(),apply=True)

    def test_concurrent_duplicate_odo_is_rejected(self):
        self.post('vehicles',{'name':'A'})
        barrier=Barrier(2)
        def insert():
            barrier.wait()
            try:
                with connect() as db:
                    services.save_log(db,dict(vehicle_id=1,filled_on='2026-06-01',odometer_km=1000,total_cost_vnd=50000,unit_price_vnd_per_liter=25000),imported=True)
                return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _:insert(),range(2))),[False,True])

    def test_v1_import_keeps_legacy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'v1.sqlite3'
            db=sqlite3.connect(path)
            try:
                db.executescript("""CREATE TABLE vehicles(id INTEGER PRIMARY KEY,name TEXT NOT NULL,license_plate TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO vehicles(id,name) VALUES(7,'Legacy');
                CREATE TABLE fuel_logs(id INTEGER PRIMARY KEY,vehicle_id INTEGER NOT NULL,filled_on TEXT NOT NULL,odometer_tenths INTEGER NOT NULL,total_cost_vnd INTEGER NOT NULL,unit_price_vnd_per_liter TEXT NOT NULL,volume_liters TEXT NOT NULL,volume_source TEXT NOT NULL,is_full_tank TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO fuel_logs(id,vehicle_id,filled_on,odometer_tenths,total_cost_vnd,unit_price_vnd_per_liter,volume_liters,volume_source,is_full_tank)
                VALUES(42,7,'2026-06-12',147270,50000,'22060.000000','2.266546','calculated','unknown');""")
            finally:db.close()
            import_sqlite(path,test_url(),apply=True)
            log=self.client.get('/api/state').get_json()['logs'][0]
            self.assertEqual(log['id'],42)
            self.assertEqual(log['volume_liters'],'2.266546')
            self.assertEqual(log['price_source'],'legacy')
            self.assertTrue(log['is_baseline'])
            self.assertIsNone(log['distance_km'])
            self.assertEqual(self.post('vehicles',{'name':'Next'})['vehicles'][-1]['id'],8)

    def test_sync_lease_and_stale_token(self):
        first=services.acquire_sync_lock()
        with self.assertRaises(ValueError):services.acquire_sync_lock()
        with connect() as db:
            db.execute("UPDATE app_locks SET expires_at=clock_timestamp()-INTERVAL '1 second'")
        second=services.acquire_sync_lock()
        with connect() as db:
            self.assertFalse(services.owns_sync_lock(db,first))
            self.assertTrue(services.owns_sync_lock(db,second))
            db.execute('DELETE FROM app_locks WHERE token=%s',(first,))
            self.assertTrue(services.owns_sync_lock(db,second))

if __name__=='__main__':unittest.main()
