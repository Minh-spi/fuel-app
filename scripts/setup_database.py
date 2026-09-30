"""Explicit one-time setup: schema, runtime permissions, then readiness check."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from scripts.migrate import apply_migrations
from scripts.create_runtime_role import provision
from scripts.check_database import main as check
from backend.db import ConfigurationError
from backend.diagnostics import database_problem

def main():
    try:
        apply_migrations()
        print('Schema ready.')
        provision()
        print('Runtime permissions ready. Existing data and passwords preserved.')
    except (ConfigurationError, psycopg.Error) as error:
        code, message=database_problem(error)
        print(code+': '+message,file=sys.stderr)
        return 1
    except ValueError as error:
        print(str(error),file=sys.stderr)
        return 1
    return check()

if __name__=='__main__':sys.exit(main())
