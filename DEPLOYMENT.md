# Triển khai Vercel + Supabase

Đã kiểm tra `https://fuel-app-sandy.vercel.app/api/state`: Function chạy nhưng trả 503 vì thiếu `DATABASE_URL`. Người dùng xác nhận chưa tạo Supabase; chưa có database cloud để kết nối hoặc import.

## Sửa lỗi trên bản Vercel hiện tại

Upload code không tự tạo Supabase hoặc biến môi trường. `.env.example` là mẫu; `.env.local` không upload lên Vercel.

1. Supabase → tạo/mở project → **Connect** → **Transaction pooler**. Lấy PostgreSQL URI, không dùng URL `https`, anon key hay service-role key. Chưa tạo `fuel_runtime` thì không tự đổi username thành role này trước bước 3.
2. Điền `.env.local`: `MIGRATION_DATABASE_URL` dùng Session pooler/admin; `RUNTIME_DB_PASSWORD` là mật khẩu riêng cho runtime role; `DATABASE_URL` dùng Transaction pooler, user `fuel_runtime.PROJECT_REF` và mật khẩu runtime. Giữ host/project từ dashboard; URL-encode ký tự đặc biệt trong mật khẩu.
3. Chạy `.venv\Scripts\python.exe scripts/setup_database.py`. Lệnh tạo schema, tạo role nếu thiếu/cấp lại quyền nếu đã có, kiểm tra runtime. Không import/xóa dữ liệu hoặc đổi mật khẩu role đã tồn tại. Chạy script import riêng nếu cần lịch sử SQLite.
4. **Vercel → project → Settings → Environment Variables**: thêm `DATABASE_URL` bằng runtime URL đã kiểm tra, chọn **Production** cho domain chính. Đặt `APP_ORIGIN=https://fuel-app-sandy.vercel.app`. Preview dùng database thử riêng. Không đặt admin URL lên Vercel.
5. Upload code mới rồi **Deployments → Redeploy**. Chỉ Save biến môi trường không cập nhật deployment đang chạy.
6. Mở `/api/health`: kết quả đúng là `{"ok":true,"database":"ready"}`. Endpoint chỉ kiểm tra đọc/quyền, không tạo bảng hoặc trả dữ liệu cá nhân. Sau đó kiểm tra `/api/state` và lưu log.

`scripts/check_database.py` kiểm tra runtime riêng. Backend cũng chấp nhận `SUPABASE_DB_URL` hoặc `POSTGRES_URL` khi chưa có `DATABASE_URL`; không tự chuyển database nếu biến ưu tiên đã có nhưng sai.

| Mã lỗi | Cách xử lý |
| --- | --- |
| `database_configuration` | Thiếu/sai URI, còn placeholder hoặc timeout sai |
| `database_connection` | Kiểm tra pooler, user/mật khẩu, project pause, mạng/SSL; không phải lỗi kết nối nào cũng phân biệt được nguyên nhân xác thực |
| `database_authentication` | PostgreSQL trả mã xác thực thất bại |
| `database_schema` | Chạy migration vào đúng project/database |
| `database_permissions` | Chạy lại script cấp quyền; không đổi mật khẩu role hiện có |
| `database_operation` | Kiểm tra schema và log Function; API không trả SQL/credentials |

## 1. Supabase và biến môi trường

Tạo project Supabase. Trong **Connect**, lấy session pooler URL để migration và transaction pooler URL để chạy app. Dùng host dashboard cung cấp. Mật khẩu có ký tự đặc biệt cần URL-encode trong URL.

Sao chép `.env.example` thành `.env.local` nếu chưa có, điền:

| Biến | Nơi dùng | Nội dung |
| --- | --- | --- |
| `MIGRATION_DATABASE_URL` | Chỉ local | Login quản trị, session pooler 5432 hoặc direct connection phù hợp mạng, `sslmode=require` |
| `RUNTIME_DB_PASSWORD` | Chỉ local lúc tạo role | Mật khẩu riêng đủ mạnh cho `fuel_runtime` |
| `DATABASE_URL` | Local/Vercel | Transaction pooler 6543, user `fuel_runtime.PROJECT_REF`, mật khẩu runtime, `sslmode=require` |
| `APP_ORIGIN` | Local/Vercel | URL app; local `http://127.0.0.1:8000` |
| `DB_CONNECT_TIMEOUT_SECONDS` | Tùy chọn | Mặc định 5 |
| `DB_STATEMENT_TIMEOUT_MS` | Tùy chọn | Mặc định 10000 |
| `PRICE_FETCH_TIMEOUT_SECONDS` | Tùy chọn | Mặc định 15, tối đa 20 cho mỗi request nguồn giá |
| `TEST_DATABASE_URL` | Chỉ test | Database UTF-8 riêng, tên kết thúc `_test`, quyền tạo schema/truncate |

Không cần Supabase anon/service-role key; backend dùng PostgreSQL trực tiếp. Không đưa secrets vào JavaScript, GitHub hoặc chat. `.env.local` chỉ tự nạp local; Vercel đọc environment variables của project.

## 2. Schema và runtime role

```powershell
.venv\Scripts\python.exe scripts/migrate.py
.venv\Scripts\python.exe scripts/create_runtime_role.py
```

Migration có transaction, khóa advisory và bảng phiên bản. Chạy lại không tạo dữ liệu mẫu. Script role tạo nếu thiếu và cấp lại quyền nếu đã có, không tự đổi mật khẩu. Sau khi tạo role, điền URL runtime; có thể bỏ `RUNTIME_DB_PASSWORD` khỏi môi trường.

Schema `fuel_app` gồm `vehicles`, `fuel_prices`, `fuel_logs`, `metadata`, `app_locks`, `schema_migrations`. Không thêm schema vào Supabase **exposed schemas**. Runtime role có CRUD năm bảng nghiệp vụ và quyền dùng sequence, không có quyền migration. Khóa xe bảo vệ ODO khi ghi đồng thời. Sync dùng lease 90 giây và token chống request hết hạn ghi đè request mới; tải web ngoài transaction.

## 3. Chuyển SQLite

Trước cutover, dừng ghi trên app SQLite cũ và sao lưu `data/fuel.sqlite3`. Nếu dùng WAL, dùng SQLite backup hoặc dừng server/checkpoint trước khi sao chép. Giữ code cũ và backup riêng; JSON export không thay thế backup database.

```powershell
# Kiểm tra nguồn, không cần PostgreSQL:
.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py --audit-only
# Import thử, đối chiếu mọi trường và rollback:
.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py
# Sau khi dry-run đạt, commit vào target trống:
.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py --apply
```

Thêm `--source <đường-dẫn-backup>` nếu cần. SQLite mở chỉ đọc; bốn bảng dữ liệu ở target phải trống. Script giữ ID, liên kết giá, ODO null, snapshot Decimal và timestamp, không tính lại lít lịch sử. Đối chiếu mọi trường/quãng đường trước commit và chỉnh sequence. Lỗi rollback toàn bộ. Chạy lại trên target có dữ liệu sẽ bị từ chối, không ghi đè.

Thử local bằng runtime URL; đối chiếu số xe/log, tiền, lít, ODO và baseline với audit. Không tiếp tục ghi song song SQLite sau cutover. Nếu PostgreSQL đã có dữ liệu mới, rollback phải bảo toàn dữ liệu mới đó trước khi quay lại app cũ.

## 4. File upload GitHub

Có thể chạy `.venv\Scripts\python.exe scripts/package_deploy.py` để tạo `fuel-vercel-source.zip` chỉ chứa mã nguồn theo danh sách cố định, không kèm secrets/database. Giải nén rồi upload **nội dung bên trong** vào root GitHub repository; không upload riêng file ZIP để deploy.

Giữ cấu trúc sau:

```text
.gitignore
.vercelignore
.python-version
.env.example
vercel.json
requirements.txt
requirements-dev.txt
package.json
package-lock.json
app.py
server.py
prices.py
README.md
DEPLOYMENT.md
backend/__init__.py
backend/config.py
backend/db.py
backend/diagnostics.py
backend/serialization.py
backend/services.py
migrations/001_initial.sql
scripts/setup-ocr.cjs
scripts/migrate.py
scripts/create_runtime_role.py
scripts/migrate_sqlite_to_postgres.py
scripts/package_deploy.py
scripts/check_database.py
scripts/setup_database.py
public/index.html
public/app.js
public/ocr.js
public/style.css
public/mobile.css
public/icon.svg
tests/test_fuel.py
tests/test_database_config.py
tests/test_migration_api.py
tests/db_support.py
tests/browser.cjs
tests/fixtures/legacy_server.py
```

Không upload `.env.local`, `.env`, `data/`, database/backup, `.venv/`, `.tools/`, `.vercel/`, `node_modules/`, `public/vendor/`, `test-results/` hoặc ZIP. Ảnh tham chiếu không cần deploy. Legacy server chỉ là fixture đối chiếu test, bị loại khỏi deployment.

## 5. Vercel

Import repository; root là thư mục chứa `app.py`. Preset **Flask** đã ghi trong `vercel.json`, build `npm ci && npm run setup:ocr`, Function tối đa 60 giây. Không đặt Output Directory thành `public`, không chọn static-only, không chạy `python server.py`. Vercel nạp `app` từ `app.py`; assets `public/**` qua CDN; OCR được tạo bằng npm lúc build.

Model OCR `@tesseract.js-data/eng` được pin cùng `package-lock.json`; bước `setup:ocr` chỉ sao chép tài nguyên đã cài, không tải thêm từ CDN.

Nếu dùng CLI thay GitHub Import: chạy `npx vercel login`, đăng nhập qua trình duyệt, rồi `npx vercel link`. Sau khi cấu hình biến môi trường, chạy `npx vercel --prod`. Nếu CLI báo token không hợp lệ, đăng nhập lại trước; không gửi token vào chat. Lần kiểm tra local hiện tại chưa chạy được Vercel build vì CLI báo token lưu trên máy không hợp lệ.

Đặt `DATABASE_URL`, `APP_ORIGIN` và timeout tùy chọn trong Vercel Environment Variables. Không đưa migration URL/password quản trị lên Vercel. Preview thử ghi dùng database riêng. Redeploy khi đổi biến môi trường.

App chưa có đăng nhập; API đọc/ghi toàn bộ dữ liệu. Origin check không phải xác thực. Trước khi dùng dữ liệu cá nhân, bảo vệ truy cập cho cả domain production và `/api/*`, hoặc giữ deployment thử với dữ liệu mẫu đến khi có xác thực. Schema Supabase riêng tư không bảo vệ HTTP API Flask.

Sau deploy: kiểm tra tám API, static assets, OCR, mobile/desktop, reload, thêm/sửa/xóa trên database thử và sync Petrolimex từ Vercel. Theo dõi lỗi SSL/quyền DB, cold start, connection pool và timeout. Test parser bằng mock local không xác minh khả năng truy cập nguồn giá từ cloud.

Không Cron/background thread. UI vẫn giữ câu chữ cũ về tự sync 6 giờ theo yêu cầu không sửa UI; thực tế chỉ sync khi gọi API.

Tham khảo: [Flask trên Vercel](https://vercel.com/docs/frameworks/backend/flask), [kết nối Supabase PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres). Transaction pooler không hỗ trợ prepared statements; code đặt `prepare_threshold=None` và dùng transaction ngắn.
