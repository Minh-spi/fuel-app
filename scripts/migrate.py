"""Apply versioned PostgreSQL migrations explicitly, never at app startup."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT
from backend.db import connect, ConfigurationError
import psycopg

def apply_migrations(url=None):
    target = url or os.environ.get('MIGRATION_DATABASE_URL')
    if not target:
        raise ValueError('Set MIGRATION_DATABASE_URL before running migrations.')
    with connect(target, migration=True) as db:
        db.execute('SELECT pg_advisory_xact_lock(721604, 2)')
        exists = db.execute("SELECT to_regclass('fuel_app.schema_migrations') AS name").fetchone()['name']
        applied = {r['version'] for r in db.execute('SELECT version FROM schema_migrations')} if exists else set()
        for path in sorted((ROOT / 'migrations').glob('[0-9]*.sql')):
            if path.stem not in applied:
                db.execute(path.read_text(encoding='utf-8'), prepare=False)

if __name__ == '__main__':
    try:
        apply_migrations()
        print('PostgreSQL migrations applied.')
    except (ValueError, ConfigurationError, psycopg.Error) as error:
        print(f'Migration failed ({type(error).__name__}). Check configuration and database permissions; credentials are not printed.', file=sys.stderr)
        sys.exit(1)
