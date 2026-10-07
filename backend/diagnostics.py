"""Safe operational errors: never include database messages, DSNs, or credentials."""
import psycopg
from backend.db import connect, ConfigurationError

def database_problem(error):
    if isinstance(error, ConfigurationError):
        return 'database_configuration', str(error)
    if isinstance(error, (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedColumn)):
        return 'database_schema', 'Database chưa có schema đúng phiên bản. Chạy scripts/migrate.py với MIGRATION_DATABASE_URL, chạy đầy đủ các migration theo thứ tự, rồi kiểm tra lại.'
    if isinstance(error, psycopg.errors.InsufficientPrivilege):
        return 'database_permissions', 'Tài khoản database chưa đủ quyền. Chạy scripts/create_runtime_role.py để cấp lại quyền cho fuel_runtime, rồi kiểm tra DATABASE_URL dùng đúng tài khoản.'
    if isinstance(error, (psycopg.errors.InvalidPassword, psycopg.errors.InvalidAuthorizationSpecification)):
        return 'database_authentication', 'Đăng nhập PostgreSQL thất bại. Kiểm tra user, mật khẩu database và project trong connection string; cập nhật biến trên Vercel rồi Redeploy.'
    if isinstance(error, psycopg.OperationalError):
        return 'database_connection', 'Không kết nối được PostgreSQL. Kiểm tra project Supabase đang hoạt động, user/mật khẩu, host Transaction pooler cổng 6543 và SSL. Cập nhật Environment Variables đúng môi trường rồi Redeploy.'
    return 'database_operation', 'Thao tác database thất bại. Dữ liệu của transaction lỗi không được lưu. Kiểm tra cấu hình/schema bằng scripts/check_database.py.'

def check_database():
    with connect(readonly=True) as db:
        # Exercise every column used by the application without returning user data.
        for table in ('vehicles', 'refueling_logs', 'fuel_prices', 'app_metadata', 'app_locks','fuel_types'):
            columns = {
                'vehicles':'id,name,license_plate,default_fuel_type_id,price_zone,city,tank_capacity_liters,created_at,vehicle_type,transmission_type,brand,model,model_year,engine_displacement_cc,purchased_on,notes,is_active,updated_at',
                'refueling_logs':'id,vehicle_id,refueled_on,refueled_time,odometer_tenths,total_cost_vnd,unit_price_vnd_per_liter,volume_liters,notes,fuel_price_id,fuel_type_id,price_zone,odo_source,created_at,updated_at',
                'fuel_prices':'id,fuel_type_id,price_zone,effective_at,unit_price_vnd_per_liter,source_url,source_updated_at,created_at,updated_at',
                'fuel_types':'id,code,name,category,is_active,created_at,updated_at',
                'app_metadata':'key,value', 'app_locks':'name,token,expires_at',
            }[table]
            db.execute(f'SELECT {columns} FROM {table} LIMIT 0')
            for privilege in (('SELECT',) if table=='fuel_types' else ('SELECT', 'INSERT', 'UPDATE', 'DELETE')):
                if not db.execute("SELECT has_table_privilege(current_user,%s,%s) AS allowed", ('fuel_app.'+table, privilege)).fetchone()['allowed']:
                    raise psycopg.errors.InsufficientPrivilege()
        for sequence in ('vehicles_id_seq','refueling_logs_id_seq','fuel_prices_id_seq'):
            if not db.execute("SELECT has_sequence_privilege(current_user,%s,'USAGE') AS allowed", ('fuel_app.'+sequence,)).fetchone()['allowed']:
                raise psycopg.errors.InsufficientPrivilege()
    return {'ok': True, 'database': 'ready'}
