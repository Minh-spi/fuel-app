"""Read-only runtime readiness check, with safe actionable diagnostics."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from backend.db import ConfigurationError
from backend.diagnostics import check_database, database_problem

def main():
    try:
        print(json.dumps(check_database()))
    except (ConfigurationError, psycopg.Error) as error:
        code, message = database_problem(error)
        print(json.dumps({'ok':False,'code':code,'error':message},ensure_ascii=True))
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
