"""Validation helpers for the one-time PVOIL archive import."""
from datetime import datetime
import re
import unicodedata

PVOIL_URL = 'https://www.pvoil.com.vn/tin-gia-xang-dau'
CATALOG = {
    'F1': ('E10', 'RON95', 'III'),
    'F2': ('E10', 'RON95', 'V'),
    'F3': ('E5', 'RON92', 'II'),
    'F4': ('RON95', 'III'),
}


def normalize(value):
    text = unicodedata.normalize('NFD', str(value)).upper()
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^A-Z0-9]+', ' ', text).strip()


def fuel_id(name):
    text = normalize(name)
    if re.search(r'\bE\s*10\b', text) and re.search(r'RON\s*95', text) and re.search(r'\b(?:III|3)\b', text):
        return 'F1'
    if re.search(r'\bE\s*10\b', text) and re.search(r'RON\s*95', text) and re.search(r'\b(?:V|5)\b', text):
        return 'F2'
    if re.search(r'\bE\s*5\b', text) and re.search(r'RON\s*92', text) and re.search(r'\b(?:II|2)\b', text):
        return 'F3'
    if not re.search(r'\bE\s*(?:10|5)\b', text) and re.search(r'RON\s*95', text) and re.search(r'\b(?:III|3)\b', text):
        return 'F4'
    return None


def integer_price(value):
    digits = re.sub(r'\D', '', str(value))
    if not digits:
        raise ValueError(f'No numeric price in {value!r}.')
    price = int(digits)
    if not 1000 <= price <= 100000:
        raise ValueError(f'Price outside expected VND/liter range: {value!r}.')
    return price


def parse_archive(document, from_year=None):
    if document.get('source_url') != PVOIL_URL:
        raise ValueError('Input source URL does not match the PVOIL archive page.')
    periods = document.get('periods')
    if not isinstance(periods, list) or not periods:
        raise ValueError('Input has no captured history periods.')
    minimum_year = int(from_year or document.get('from_year') or 2000)
    rows = {}
    skipped = 0
    for period in periods:
        effective = datetime.fromisoformat(period['effective_at'])
        if effective.tzinfo is None:
            raise ValueError('Every effective timestamp must include its timezone.')
        if effective.year < minimum_year:
            continue
        headers = [normalize(value) for value in period.get('headers', [])]
        explicit_zones = {1: [], 2: []}
        for index, header in enumerate(headers):
            if 'GIA' not in header or any(word in header for word in ('CHENH LECH', 'TANG GIAM')):
                continue
            if re.search(r'VUNG\s*1', header): explicit_zones[1].append(index)
            if re.search(r'VUNG\s*2', header): explicit_zones[2].append(index)
        has_zone_columns = bool(explicit_zones[1] and explicit_zones[2])
        for product in period.get('products', []):
            cells = [str(value).strip() for value in product.get('cells', [])]
            match_index = next((i for i, cell in enumerate(cells) if fuel_id(cell)), None)
            if match_index is None:
                skipped += 1
                continue
            product_id = fuel_id(cells[match_index])
            price_columns = []
            if has_zone_columns:
                price_columns = [(zone, explicit_zones[zone][0]) for zone in (1, 2)]
            else:
                candidates = [i for i in range(match_index + 1, len(cells)) if cells[i]]
                if not candidates:
                    raise ValueError(f'No price cell next to fuel name {cells[match_index]!r}.')
                # PVOIL's public history page publishes one nationwide price when
                # its table has no separate price-zone columns.
                price_columns = [(1, candidates[0]), (2, candidates[0])]
            for zone, index in price_columns:
                if index >= len(cells):
                    raise ValueError(f'Price column missing for {cells[match_index]!r}.')
                price = integer_price(cells[index])
                key = (product_id, zone, effective.isoformat())
                value = {'fuel_type_id': product_id, 'price_zone': zone,
                    'effective_at': effective.isoformat(), 'unit_price_vnd_per_liter': price,
                    'source_url': PVOIL_URL}
                previous = rows.get(key)
                if previous and previous != value:
                    raise ValueError(f'Conflicting PVOIL prices for {key}.')
                rows[key] = value
    if not rows:
        raise ValueError('No supported catalog fuels were found in the captured archive.')
    return list(rows.values()), skipped
