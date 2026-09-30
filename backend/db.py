"""Short-lived PostgreSQL transactions, compatible with Supavisor transaction mode."""
import os
from contextlib import contextmanager
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from backend.config import integer_setting, ConfigurationError

URL_VARIABLES = ('DATABASE_URL', 'SUPABASE_DB_URL', 'POSTGRES_URL')

def connection_info(url=None):
    if url is None:
        url = next((os.environ[name].strip() for name in URL_VARIABLES if os.environ.get(name, '').strip()), '')
    if not isinstance(url, str) or not url.strip():
        raise ConfigurationError('Chưa kết nối database. Trong Vercel → Settings → Environment Variables, thêm DATABASE_URL bằng PostgreSQL Transaction pooler URL từ Supabase → Connect, chọn đúng Production/Preview rồi Redeploy.')
    url = url.strip()
    if not url.startswith(('postgresql://', 'postgres://')):
        raise ConfigurationError('DATABASE_URL phải là PostgreSQL connection string (postgresql://...), không phải URL https của Supabase hoặc API key. Không thêm dấu nháy quanh giá trị trên Vercel.')
    try:
        info = conninfo_to_dict(url)
    except psycopg.Error:
        raise ConfigurationError('Connection string PostgreSQL không hợp lệ. Sao chép lại từ Supabase → Connect; URL-encode ký tự đặc biệt trong mật khẩu.') from None
    if not all(info.get(key) for key in ('host', 'user', 'dbname')):
        raise ConfigurationError('Connection string thiếu host, user hoặc tên database. Hãy sao chép URL đầy đủ từ Supabase → Connect.')
    if any(marker in url for marker in ('PROJECT_REF', 'POOLER_HOST', '[YOUR-PASSWORD]', ':PASSWORD@', '[YOUR_PASSWORD]')):
        raise ConfigurationError('Connection string còn giá trị mẫu. Thay project, host và mật khẩu bằng thông tin thật từ Supabase → Connect.')
    return info

@contextmanager
def connect(url=None, *, readonly=False, migration=False):
    info = connection_info(url)
    # SSL is mandatory for remote databases; local disposable test databases may disable it.
    if info.get('host') not in ('localhost', '127.0.0.1', '::1'):
        info['sslmode'] = info.get('sslmode') if info.get('sslmode') in ('verify-ca', 'verify-full') else 'require'
    info['connect_timeout'] = integer_setting('DB_CONNECT_TIMEOUT_SECONDS', 5, maximum=30)
    with psycopg.connect(**info, row_factory=dict_row, prepare_threshold=None) as db:
        if readonly:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        db.execute("SET LOCAL search_path TO fuel_app, pg_catalog")
        db.execute("SET LOCAL TIME ZONE 'UTC'")
        db.execute("SELECT set_config('statement_timeout', %s, true)", (str(60000 if migration else integer_setting('DB_STATEMENT_TIMEOUT_MS', 10000)),))
        db.execute("SELECT set_config('lock_timeout', %s, true)", ('5000',))
        yield db
