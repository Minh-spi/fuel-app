"""Provision a least-privileged PostgreSQL login without printing its password."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from backend.db import connect, ConfigurationError

def provision():
    url = os.environ.get('MIGRATION_DATABASE_URL')
    password = os.environ.get('RUNTIME_DB_PASSWORD')
    if not url:
        raise ValueError('Set MIGRATION_DATABASE_URL locally.')
    with connect(url, migration=True) as db:
        db.execute('SELECT pg_advisory_xact_lock(721604, 3)')
        if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='fuel_runtime'").fetchone():
            if not password:
                raise ValueError('Set RUNTIME_DB_PASSWORD to create fuel_runtime.')
            db.execute(sql.SQL('CREATE ROLE fuel_runtime LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT').format(sql.Literal(password)))
        db.execute('GRANT USAGE ON SCHEMA fuel_app TO fuel_runtime')
        for table in ('vehicles', 'fuel_prices', 'refueling_logs', 'app_metadata', 'app_locks'):
            db.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON fuel_app.{} TO fuel_runtime').format(sql.Identifier(table)))
        db.execute('GRANT SELECT ON fuel_app.fuel_types TO fuel_runtime')
        db.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fuel_app TO fuel_runtime')

if __name__ == '__main__':
    try:
        provision()
        print('fuel_runtime permissions ready. Existing passwords are unchanged.')
    except (ValueError, ConfigurationError, psycopg.Error) as error:
        print(f'Role provisioning failed ({type(error).__name__}). Check the local configuration/role existence.', file=sys.stderr)
        sys.exit(1)
