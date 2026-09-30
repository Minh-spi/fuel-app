import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import os
from backend import services as server
from db_support import reset, test_url
import prices

class FuelTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, DATABASE_URL=test_url())
        self.env.start()
        self.addCleanup(self.env.stop)
        reset()
        with server.connect() as db:
            db.execute("INSERT INTO vehicles(name) VALUES('A'),('B')")
            self.price(db, '2026-01-01T00:00', 20000)

    def price(self, db, at, value, zone=1, fuel='E10 RON 95-III'):
        server.put_price(db, dict(fuel_type=fuel, price_zone=zone, effective_at=at, unit_price_vnd=value, source='manual'))

    def add(self, db, day, odo=None, vehicle=1, **extra):
        data = dict(vehicle_id=vehicle, filled_on=day, odometer_km=odo, total_cost_vnd=50000, **extra)
        server.save_log(db, data)
        return data

    def test_backfill_delete_and_vehicle_isolation(self):
        with server.connect() as db:
            self.add(db,'2026-06-17',14898.4)
            self.add(db,'2026-06-12',14727)
            self.add(db,'2026-06-15',500,vehicle=2)
            logs=server.snapshot(db)['logs']
            self.assertIsNone(logs[0]['distance_km'])
            self.assertTrue(logs[0]['is_baseline'])
            self.assertEqual(logs[1]['distance_km'],171.4)
            self.assertIsNone(logs[2]['distance_km'])
            db.execute('DELETE FROM fuel_logs WHERE id=%s',(logs[0]['id'],))
            self.assertIsNone(server.snapshot(db)['logs'][0]['distance_km'])

    def test_sample_total_and_precision(self):
        with server.connect() as db:
            for day,odo,cost,price in server.SAMPLE:
                server.save_log(db,dict(vehicle_id=1,filled_on=day,odometer_km=odo,total_cost_vnd=cost,unit_price_vnd_per_liter=price),imported=True)
            logs=server.snapshot(db)['logs']
            self.assertEqual(len(logs),14)
            self.assertAlmostEqual(sum(l['distance_km'] or 0 for l in logs),2327.5)
            self.assertEqual(sum(l['total_cost_vnd'] for l in logs),720000)
            self.assertEqual(logs[0]['volume_liters'],'2.266546')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM fuel_prices').fetchone()['count'],1)

    def test_invalid_odo_and_duplicates(self):
        with server.connect() as db:
            self.add(db,'2026-06-12',14727)
            for day,odo in [('2026-06-13',14000),('2026-06-12',14727),('2026-06-10',15000)]:
                with self.assertRaises(ValueError): self.add(db,day,odo)
            for value in ['NaN','Infinity',-1,10.25]:
                with self.assertRaises(ValueError): self.add(db,'2026-06-13',value)

    def test_money_and_date_only_and_missing_odo(self):
        with server.connect() as db:
            self.add(db,'2026-06-10')
            self.add(db,'2026-06-11',1000)
            self.add(db,'2026-06-12')
            self.add(db,'2026-06-13',1150)
            logs=server.snapshot(db)['logs']
            self.assertTrue(logs[0]['is_baseline'])
            self.assertIsNone(logs[1]['distance_km'])
            self.assertFalse(logs[1]['is_baseline'])
            self.assertIsNone(logs[2]['distance_km'])
            self.assertEqual(logs[3]['distance_km'],150)
            self.assertEqual(logs[3]['distance_from_id'],logs[1]['id'])
            self.assertEqual(logs[0]['volume_liters'],'2.500000')

    def test_price_day_time_region_and_product(self):
        with server.connect() as db:
            self.price(db,'2026-06-12T15:00',25000)
            self.price(db,'2026-06-12T15:00',26000,zone=2)
            self.price(db,'2026-06-12T15:00',27000,fuel='E10 RON 95-V')
            self.assertTrue(server.quote(db,1,'2026-06-12')['needs_time'])
            self.assertEqual(server.quote(db,1,'2026-06-12','14:59')['price']['unit_price_vnd'],20000)
            self.assertEqual(server.quote(db,1,'2026-06-12','15:00')['price']['unit_price_vnd'],25000)
            self.assertIsNone(server.quote(db,1,'2025-12-31')['price'])
            self.assertEqual(server.quote(db,1,'2026-06-13')['price']['unit_price_vnd'],25000)
            with self.assertRaises(ValueError):self.add(db,'2026-06-12')
            db.execute('UPDATE vehicles SET price_zone=2 WHERE id=2')
            self.assertEqual(server.quote(db,2,'2026-06-13')['price']['unit_price_vnd'],26000)

    def test_saved_price_does_not_change_after_sync_or_edit(self):
        with server.connect() as db:
            data=self.add(db,'2026-06-10',1000)
            row=server.snapshot(db)['logs'][0]
            self.price(db,'2026-01-01T00:00',30000)
            server.save_log(db,{**data,'total_cost_vnd':60000},row['id'])
            saved=server.snapshot(db)['logs'][0]
            self.assertEqual(saved['unit_price_vnd_per_liter'],'20000.000000')
            self.assertEqual(saved['volume_liters'],'3.000000')
            server.save_log(db,{**data,'filled_on':'2026-06-11'},row['id'])
            self.assertEqual(server.snapshot(db)['logs'][0]['unit_price_vnd_per_liter'],'30000.000000')

    def test_same_day_order_and_edit_revalidation(self):
        with server.connect() as db:
            self.add(db,'2026-06-10',1000,filled_time='10:00')
            data=self.add(db,'2026-06-10',1100,filled_time='15:00')
            with self.assertRaises(ValueError):self.add(db,'2026-06-10',1200,filled_time='12:00')
            row=server.snapshot(db)['logs'][1]
            with self.assertRaises(ValueError):server.save_log(db,{**data,'odometer_km':900},row['id'])

    def test_sync_failure_keeps_saved_prices(self):
        with patch('backend.services.fetch_prices',side_effect=OSError('network')):
            with self.assertRaises(ValueError):server.sync_prices()
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM fuel_prices').fetchone()['count'],1)
            self.assertTrue(server.snapshot(db)['sync']['price_sync_error'])

    def test_sidebar_parser_strict_product_effective_date(self):
        payload={'Objects':[dict(Title='Xăng E10 RON 95-III',Zone1Price=27080,Zone2Price=27620,LastModified='2026-09-24T07:47:51.496Z')]}
        html='petrolimex-dieu-chinh-gia-xang-dau-tu-15-gio-00-phut-ngay-24-9-2026'
        rows=prices.parse_sidebar(payload,html)
        self.assertEqual(rows[0]['effective_at'],'2026-09-24T15:00+07:00')
        self.assertEqual(rows[1]['unit_price_vnd'],27620)
        with self.assertRaises(ValueError):prices.parse_sidebar(payload,html.replace('24-9','25-9'))
        payload['Objects'][0]['Title']='Xăng RON 95-III'
        with self.assertRaises(ValueError):prices.parse_sidebar(payload,html)

    def test_vehicle_defaults_and_update(self):
        with server.connect() as db:
            v=server.vehicle_by_id(db,1)
            self.assertEqual(str(v['tank_capacity_liters']),'4.000')
            self.assertEqual(v['city'],'Đà Nẵng')
            server.save_vehicle(db,dict(id=1,name='Xe tôi',fuel_type='E10 RON 95-III',price_zone=2))
            self.assertEqual(server.vehicle_by_id(db,1)['price_zone'],2)

if __name__ == '__main__':unittest.main()
