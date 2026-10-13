import unittest
from backend.pvoil_archive import PVOIL_URL, fuel_id, parse_archive


class PvoilArchiveTests(unittest.TestCase):
    def test_maps_supported_products_and_nationwide_prices_to_both_zones(self):
        document = {
            'source_url': PVOIL_URL,
            'from_year': 2026,
            'periods': [{
                'effective_at': '2026-10-08T15:00:00+07:00',
                'headers': ['TT', 'Mặt hàng', 'Giá điều chỉnh lúc 15:00 ngày 08/10/2026'],
                'products': [
                    {'cells': ['1', 'Xăng E10 RON 95-III', '28.250 đ']},
                    {'cells': ['2', 'Xăng E5 RON 92-II', '27.700 đ']},
                    {'cells': ['3', 'Dầu DO 0,05S-II', '29.120 đ']},
                ],
            }],
        }
        rows, skipped = parse_archive(document)
        self.assertEqual(len(rows), 4)
        self.assertEqual(skipped, 1)
        self.assertEqual({(row['fuel_type_id'], row['price_zone'], row['unit_price_vnd_per_liter']) for row in rows}, {
            ('F1', 1, 28250), ('F1', 2, 28250), ('F3', 1, 27700), ('F3', 2, 27700),
        })

    def test_recognizes_current_catalog_names_and_rejects_unknown_prices(self):
        self.assertEqual(fuel_id('Xăng E10 RON95 Mức 3'), 'F1')
        self.assertEqual(fuel_id('Xăng E5 RON92 Mức 2'), 'F3')
        with self.assertRaises(ValueError):
            parse_archive({'source_url':PVOIL_URL,'from_year':2026,'periods':[{
                'effective_at':'2026-10-08T15:00:00+07:00','headers':[],
                'products':[{'cells':['Xăng E10 RON 95-III','không rõ']}]
            }]})

    def test_keeps_explicit_zone_prices_separate(self):
        document = {'source_url':PVOIL_URL,'from_year':2026,'periods':[{
            'effective_at':'2026-10-08T15:00:00+07:00',
            'headers':['TT','Mặt hàng','Giá vùng 1','Giá vùng 2'],
            'products':[{'cells':['1','Xăng E10 RON 95-III','28.250 đ','28.500 đ']}]
        }]}
        rows, _ = parse_archive(document)
        self.assertEqual({r['price_zone']:r['unit_price_vnd_per_liter'] for r in rows},{1:28250,2:28500})

    def test_rejects_wrong_source_and_timezone_less_timestamp(self):
        with self.assertRaises(ValueError):
            parse_archive({'source_url':'https://example.com','periods':[{}]})
        with self.assertRaises(ValueError):
            parse_archive({'source_url':PVOIL_URL,'from_year':2026,'periods':[{
                'effective_at':'2026-10-08T15:00:00','headers':[],
                'products':[{'cells':['Xăng E10 RON 95-III','28.250']}]
            }]})


if __name__ == '__main__':
    unittest.main()
