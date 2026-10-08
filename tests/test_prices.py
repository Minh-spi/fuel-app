import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import prices

class PriceParserTests(unittest.TestCase):
    def row(self,**extra):
        return dict(Title='Xăng E10 RON 95 Mức 3',EnglishTitle='E10 RON 95-III',Alias='e10-ron-95-iii',
            LastModified='2026-10-01T07:58:16.479Z',Zone1Price=27180,Zone2Price=27720,**extra)

    def parse(self,rows):
        return prices.parse_sidebar({'Objects':rows},'petrolimex-dieu-chinh-gia-xang-dau-tu-15-gio-00-phut-ngay-01-10-2026')

    def test_renamed_vietnamese_title(self):
        rows=self.parse([self.row()])
        self.assertEqual([r['unit_price_vnd'] for r in rows],[27180,27720])
        self.assertEqual(rows[0]['fuel_code'],'E10_RON95_III')
        self.assertEqual(rows[0]['effective_at'],'2026-10-01T15:00+07:00')
        self.assertEqual(rows[0]['source_url'],prices.sidebar_url())

    def test_each_identifier_and_whitespace(self):
        for item in ({'Title':'  Xăng  E10 RON 95 Mức 3 '},{'EnglishTitle':'E10 RON 95-III'},{'Alias':'e10-ron-95-iii'}):
            self.assertEqual(prices.resolve_fuel(item),'E10 RON 95-III')

    def test_conflicting_identifiers_rejected(self):
        item=self.row();item['EnglishTitle']='RON 95-III'
        with self.assertRaises(ValueError):self.parse([item])

    def test_does_not_substitute_plain_ron95_or_diesel(self):
        for title in ('Xăng RON 95-III','DO 0,001S Mức 5'):
            item=self.row();item.update(Title=title,EnglishTitle='',Alias='')
            with self.assertRaises(ValueError):self.parse([item])

    def test_duplicates_date_mismatch_and_invalid_prices(self):
        with self.assertRaises(ValueError):self.parse([self.row(),self.row()])
        for field,value in (('LastModified','2026-09-24T08:00:00Z'),('Zone1Price',-5),('Zone1Price',27180.5)):
            item=self.row();item[field]=value
            with self.assertRaises(ValueError):self.parse([item])

    def test_network_and_invalid_json_have_safe_errors(self):
        for error in (URLError('offline'),HTTPError('https://www.petrolimex.com.vn',503,'unavailable',{},None)):
            with patch('prices.download',side_effect=error):
                with self.assertRaises(prices.PriceSourceError):prices.fetch_prices()
        with patch('prices.download',return_value='<html>error</html>'):
            with self.assertRaises(prices.PriceSourceError):prices.fetch_prices()

if __name__=='__main__':unittest.main()
