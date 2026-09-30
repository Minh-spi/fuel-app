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
        db.execute('TRUNCATE fuel_logs, fuel_prices, vehicles, metadata, app_locks RESTART IDENTITY CASCADE')

if __name__ == '__main__':
    reset()
