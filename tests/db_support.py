import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg.conninfo import conninfo_to_dict
from backend.db import connect
from scripts.migrate import apply_migrations

def test_url():
    url = os.environ.get('TEST_DATABASE_URL', '')
    if not url or not conninfo_to_dict(url).get('dbname', '').endswith('_test'):
        raise RuntimeError('TEST_DATABASE_URL must point to a dedicated database ending in _test.')
    return url

def reset():
    url = test_url()
    apply_migrations(url)
    with connect(url, migration=True) as db:
        db.execute('TRUNCATE refueling_logs, fuel_prices, vehicles, app_metadata, app_locks RESTART IDENTITY CASCADE')
        for sequence in ('vehicles_id_seq','fuel_prices_id_seq','refueling_logs_id_seq'):
            db.execute('ALTER SEQUENCE fuel_app.'+sequence+' RESTART WITH 1')

if __name__ == '__main__':
    reset()
