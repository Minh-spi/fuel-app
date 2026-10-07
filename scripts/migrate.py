"""Apply versioned PostgreSQL migrations explicitly, never at app startup."""
import os
import sys
import json
from datetime import datetime, timezone
from psycopg import sql
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import ROOT
from backend.db import connect, ConfigurationError
import psycopg

def apply_migrations(url=None, *, backup_dir=None):
    target = url or os.environ.get('MIGRATION_DATABASE_URL')
    if not target:
        raise ValueError('Set MIGRATION_DATABASE_URL before running migrations.')
    with connect(target, migration=True) as db:
        db.execute('SELECT pg_advisory_xact_lock(721604, 2)')
        exists = db.execute("SELECT to_regclass('fuel_app.schema_migrations') AS name").fetchone()['name']
        applied = {r['version'] for r in db.execute('SELECT version FROM schema_migrations')} if exists else set()
        for path in sorted((ROOT / 'migrations').glob('[0-9]*.sql')):
            if path.stem not in applied:
                if path.stem == '002_fuel_catalog':
                    # Take a consistent, private backup before removing obsolete columns.
                    db.execute('LOCK TABLE vehicles, fuel_prices, fuel_logs, metadata IN ACCESS EXCLUSIVE MODE')
                    tables=('vehicles','fuel_prices','fuel_logs','metadata','app_locks','schema_migrations')
                    backup={t:list(db.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(t)))) for t in tables}
                    backup['sequences']={t:db.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier(t+'_id_seq'))).fetchone() for t in tables[:3]}
                    directory=Path(backup_dir) if backup_dir else ROOT/'note'/'backups'
                    directory.mkdir(parents=True,exist_ok=True)
                    filename=directory/('before-002-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
                    with filename.open('x',encoding='utf-8') as output:
                        json.dump(backup,output,ensure_ascii=False,default=str,indent=2)
                db.execute(path.read_text(encoding='utf-8'), prepare=False)

if __name__ == '__main__':
    try:
        apply_migrations()
        print('PostgreSQL migrations applied.')
    except (ValueError, ConfigurationError, psycopg.Error) as error:
        print(f'Migration failed ({type(error).__name__}). Check configuration and database permissions; credentials are not printed.', file=sys.stderr)
        sys.exit(1)
