import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from db_support import test_url, reset
from backend.db import connect
from backend import services
from scripts.migrate import apply_migrations

ROOT=Path(__file__).resolve().parents[1]

class CatalogMigrationTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,DATABASE_URL=test_url())
        self.env.start();self.addCleanup(self.env.stop)
        reset()

    def test_upgrade_preserves_rows_foreign_keys_and_deleted_id_highwater(self):
        # Only the isolated *_test DB may be rebuilt. No production DSN is used.
        with connect(test_url(),migration=True) as db:
            db.execute('DROP SCHEMA fuel_app CASCADE')
            db.execute((ROOT/'migrations/001_initial.sql').read_text(encoding='utf-8'),prepare=False)
            db.execute("INSERT INTO vehicles(id,name) VALUES(12,'Legacy'),(13,'Second')")
            db.execute("SELECT setval('vehicles_id_seq',99)")
            db.execute("INSERT INTO fuel_prices(id,fuel_type,price_zone,effective_at,unit_price_vnd,source,fetched_at) VALUES(7,'E10 RON 95-III',1,'2026-01-01+07',25000,'manual',now())")
            db.execute("""INSERT INTO fuel_logs(id,vehicle_id,filled_on,odometer_tenths,total_cost_vnd,unit_price_vnd_per_liter,volume_liters,price_id)
                VALUES(2,12,'2026-06-01',NULL,50000,25000,2,7),(10,12,'2026-06-02',10000,50000,25000,2,7),
                (11,12,'2026-06-03',11500,60000,25000,2.4,7),(12,13,'2026-06-01',50,10000,25000,0.4,7)""")
        with tempfile.TemporaryDirectory() as directory:
            apply_migrations(test_url(),backup_dir=directory)
            apply_migrations(test_url(),backup_dir=directory)
            backups=list(Path(directory).glob('*.json'))
            self.assertEqual(len(backups),1)
            self.assertEqual(len(json.loads(backups[0].read_text(encoding='utf-8'))['fuel_logs']),4)
        with connect() as db:
            state=services.snapshot(db)
            self.assertEqual([v['id'] for v in state['vehicles']],['V12','V13'])
            self.assertEqual([l['id'] for l in state['logs']],['R2','R10','R11','R12'])
            self.assertEqual([l['distance_km'] for l in state['logs']],[None,None,150,None])
            self.assertTrue(state['logs'][-1]['is_baseline'])
            self.assertEqual(state['logs'][2]['volume_liters'],'2.400000')
            self.assertEqual(state['logs'][0]['fuel_price_id'],'P7')
            self.assertEqual(state['prices'][0]['source_url'],'manual')
            self.assertEqual(db.execute("INSERT INTO vehicles(name) VALUES('Next') RETURNING id").fetchone()['id'],'V100')
            tables={r['tablename'] for r in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='fuel_app'")}
            self.assertEqual(tables,{'vehicles','fuel_types','fuel_prices','refueling_logs','app_metadata','app_locks','schema_migrations','price_sync_runs'})

    def test_vehicle_details_partial_edit_and_historical_fuel(self):
        with connect() as db:
            services.save_vehicle(db,dict(name='A',vehicle_type='motorcycle',transmission_type='automatic',brand='Honda',model='Vision',model_year=2024,engine_displacement_cc=110,tank_capacity_liters='4.9',license_plate='',purchased_on='2025-01-02'))
            services.save_log(db,dict(vehicle_id='V1',refueled_on='2026-06-01',total_cost_vnd=50000,unit_price_vnd_per_liter=25000),imported=True)
            services.save_vehicle(db,dict(id='V1',name='B',default_fuel_type_id='F2'))
            vehicle=services.vehicle_by_id(db,'V1')
            self.assertEqual(vehicle['brand'],'Honda')
            self.assertIsNone(vehicle['license_plate'])
            self.assertEqual(vehicle['tank_capacity_liters'],Decimal('4.9'))
            log=services.snapshot(db)['logs'][0]
            self.assertEqual(log['fuel_type_id'],'F1')
            services.save_log(db,dict(vehicle_id='V1',refueled_on='2026-06-01',total_cost_vnd=60000),log['id'])
            self.assertEqual(services.snapshot(db)['logs'][0]['fuel_type_id'],'F1')

    def test_manual_price_priority_and_required_source(self):
        with connect() as db:
            services.save_vehicle(db,{'name':'A'})
            base=dict(fuel_type_id='F1',price_zone=1,effective_at='2026-01-01T00:00')
            services.put_price(db,{**base,'source_url':'manual','unit_price_vnd_per_liter':25000})
            services.put_price(db,{**base,'source_url':'https://example.com/prices','unit_price_vnd_per_liter':26000})
            self.assertEqual(services.quote(db,'V1','2026-06-01')['price']['unit_price_vnd_per_liter'],25000)
            services.put_price(db,{**base,'fuel_type_id':'F2','source_url':'https://www.pvoil.com.vn/tin-gia-xang-dau','unit_price_vnd_per_liter':24000})
            services.put_price(db,{**base,'fuel_type_id':'F2','source_url':'https://portals.petrolimex.com.vn/prices','unit_price_vnd_per_liter':24500})
            self.assertEqual(services.quote(db,'V1','2026-06-01',fuel_type_id='F2')['price']['unit_price_vnd_per_liter'],24500)
            with self.assertRaises(ValueError):services.put_price(db,{**base,'source_url':'','unit_price_vnd_per_liter':25000})

    def test_legacy_owner_claim_and_account_isolation(self):
        first='11111111-1111-4111-8111-111111111111';second='22222222-2222-4222-8222-222222222222'
        with patch.dict(os.environ,LEGACY_OWNER_EMAIL='owner@example.com'),connect() as db:
            services.save_vehicle(db,{'name':'Xe cũ'})
            services.put_price(db,dict(fuel_type_id='F1',price_zone=1,effective_at='2026-01-01T00:00',unit_price_vnd_per_liter=25000,source_url='manual'))
            services.claim_legacy_data(db,first,'owner@example.com',True)
            services.claim_legacy_data(db,second,'other@example.com',True)
            self.assertEqual([v['id'] for v in services.snapshot(db,first)['vehicles']],['V1'])
            self.assertEqual(services.snapshot(db,second)['vehicles'],[])
            self.assertEqual(services.snapshot(db,first)['prices'][0]['owner_id'],first)
            self.assertEqual(services.snapshot(db,second)['prices'],[])
            services.save_vehicle(db,{'name':'Xe riêng'},second)
            self.assertEqual([v['id'] for v in services.snapshot(db,second)['vehicles']],['V2'])
            with self.assertRaises(ValueError):services.vehicle_by_id(db,'V1',second)

    def test_price_sync_counts_and_daily_idempotency(self):
        rows=[dict(fuel_type='E10 RON 95-III',fuel_code='E10_RON95_III',price_zone=1,effective_at='2026-10-08T15:00+07:00',unit_price_vnd=28250,source_url='https://www.petrolimex.com.vn/prices',source_updated_at='2026-10-08T08:00:00Z')]
        with patch('backend.services.fetch_prices',return_value=rows):
            self.assertEqual(services.sync_prices(),{'observed_rows':1,'inserted_rows':1,'changed_rows':0,'unchanged_rows':0})
            self.assertEqual(services.sync_prices(),{'observed_rows':1,'inserted_rows':0,'changed_rows':0,'unchanged_rows':1})
            services.sync_prices_daily()
            self.assertTrue(services.sync_prices_daily()['skipped'])

    def test_concurrent_id_generation(self):
        def create(_):
            with connect() as db:
                return db.execute("INSERT INTO vehicles(name) VALUES('Concurrent') RETURNING id").fetchone()['id']
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(create,range(12)))
        self.assertEqual(len(set(ids)),12)
        self.assertEqual(set(ids),{'V'+str(n) for n in range(1,13)})

if __name__=='__main__':unittest.main()
