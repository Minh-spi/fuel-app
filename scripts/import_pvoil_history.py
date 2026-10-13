"""Preview or idempotently import a locally captured PVOIL price archive."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.db import connect, ConfigurationError
from backend.pvoil_archive import parse_archive


def load_rows(path, from_year):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    return parse_archive(document, from_year)


def apply_rows(rows):
    inserted = unchanged = 0
    # One transaction: conflicting values abort the complete import.
    with connect() as db:
        fuel_ids = {r['fuel_type_id'] for r in rows}
        known = {r['id'] for r in db.execute('SELECT id FROM fuel_types WHERE id=ANY(%s)', (list(fuel_ids),))}
        if known != fuel_ids:
            raise ValueError('Database fuel catalog does not match captured PVOIL fuel types.')
        for row in rows:
            old = db.execute("""SELECT unit_price_vnd_per_liter FROM fuel_prices
                WHERE fuel_type_id=%s AND price_zone=%s AND effective_at=%s AND source_url=%s""",
                (row['fuel_type_id'], row['price_zone'], row['effective_at'], row['source_url'])).fetchone()
            if old:
                if int(old['unit_price_vnd_per_liter']) != row['unit_price_vnd_per_liter']:
                    raise ValueError(f"Existing PVOIL value conflicts at {row['effective_at']} ({row['fuel_type_id']}, zone {row['price_zone']}); nothing was imported.")
                unchanged += 1
                continue
            db.execute("""INSERT INTO fuel_prices(fuel_type_id,price_zone,effective_at,
                unit_price_vnd_per_liter,source_url,source_updated_at,owner_id)
                VALUES(%s,%s,%s,%s,%s,NULL,NULL)
                ON CONFLICT (fuel_type_id,price_zone,effective_at,source_url)
                WHERE source_url<>'manual' DO NOTHING""",
                (row['fuel_type_id'], row['price_zone'], row['effective_at'],
                 row['unit_price_vnd_per_liter'], row['source_url']))
            inserted += 1
    return inserted, unchanged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='note/pvoil_history.json')
    parser.add_argument('--from-year', type=int)
    parser.add_argument('--apply', action='store_true', help='Write after reviewing the capture; default is preview only.')
    args = parser.parse_args()
    rows, skipped = load_rows(args.input, args.from_year)
    counts = Counter(row['fuel_type_id'] for row in rows)
    print(f"Validated {len(rows)} rows from {len({r['effective_at'] for r in rows})} effective timestamps.")
    print('Catalog counts:', ', '.join(f'{key}={counts[key]}' for key in sorted(counts)))
    print(f'Skipped unsupported products: {skipped}')
    if not args.apply:
        print('Preview only. Inspect the JSON and rerun with --apply to write to DATABASE_URL.')
        return
    inserted, unchanged = apply_rows(rows)
    print(f'Import complete: inserted={inserted}, unchanged={unchanged}.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, ConfigurationError) as error:
        print(f'Import stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
