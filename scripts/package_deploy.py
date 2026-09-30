"""Create a source-only deployment archive using an explicit allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = '''
.gitignore .vercelignore .python-version .env.example vercel.json
requirements.txt requirements-dev.txt package.json package-lock.json
app.py server.py prices.py README.md DEPLOYMENT.md
backend/__init__.py backend/config.py backend/db.py backend/serialization.py backend/services.py
backend/diagnostics.py
migrations/001_initial.sql
scripts/setup-ocr.cjs scripts/migrate.py scripts/create_runtime_role.py
scripts/migrate_sqlite_to_postgres.py scripts/package_deploy.py
scripts/check_database.py scripts/setup_database.py
public/index.html public/app.js public/ocr.js public/style.css public/mobile.css public/icon.svg
tests/test_fuel.py tests/test_migration_api.py tests/db_support.py tests/browser.cjs tests/fixtures/legacy_server.py
tests/test_database_config.py
'''.split()

def main():
    for name in FILES:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or symlinked source file: {name}')
    destination = ROOT / 'fuel-vercel-source.zip'
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == FILES
    print(f'Created {destination.name}: {len(FILES)} source files, {destination.stat().st_size:,} bytes.')
    print('Extract into a GitHub repository root. Database, credentials, and generated assets are excluded.')

if __name__ == '__main__':
    main()
