# Vercel + Supabase: triển khai và nâng cấp

## Nếu đang chạy bản cũ

Migration 002 thay đổi tên bảng/cột và ID; phải nâng cấp backend/frontend cùng schema. Không chạy migration production trong lúc app cũ tiếp tục ghi.

1. Thử migration trên database thử hoặc bản sao. Giữ commit/deployment cũ và backup PostgreSQL trước thay đổi. Dừng ghi/tạm bảo trì app khi chuyển production.
2. Điền `MIGRATION_DATABASE_URL` vào `.env.local` local, dùng admin Session pooler (5432) hoặc direct URL đúng project. `DATABASE_URL` dùng runtime Transaction pooler (6543). Không nhầm với TEST_DATABASE_URL.
3. Chạy `.venv\Scripts\python.exe scripts/migrate.py`. Script chạy migration còn thiếu trong transaction, trước 002 khóa ghi và xuất bản sao các bảng v1/sequence vào `note/backups/`. Nếu không ghi được backup hoặc SQL lỗi, rollback transaction. Bản JSON này dùng đối chiếu/khôi phục thủ công với schema v1; không thay thế backup PostgreSQL đầy đủ và không có nút restore tự động.
4. Chạy `.venv\Scripts\python.exe scripts/create_runtime_role.py` để bảo đảm quyền đọc danh mục và dùng sequence mới. Không đổi mật khẩu role đang có.
5. Chạy `.venv\Scripts\python.exe scripts/check_database.py`, cần `database: ready`.
6. Deploy code mới lên Vercel rồi kiểm tra `/api/health`, `/api/state`, thêm/sửa/xóa, nhiều xe, OCR, giá theo ngày. Mở lại ghi sau khi kiểm tra. Reload các tab cũ để lấy frontend mới.

Nếu có lỗi sau cutover, không chỉ rollback deployment về code cũ: schema mới không tương thích code cũ. Cần khôi phục schema/dữ liệu từ backup trong cửa sổ bảo trì, giữ mọi dữ liệu mới phát sinh để đối chiếu. Không drop bảng production để thử lại.

## Migration đăng nhập và đồng bộ giá

Code mới cần migration `003_ownership_and_sync` sau 001/002. Migration này thêm owner cho xe/giá nhập tay và nhật ký đồng bộ; không xóa log, giá hoặc snapshot cũ.

1. Sao lưu Supabase/PostgreSQL và lên lịch bảo trì ngắn vì app cũ chưa yêu cầu đăng nhập. Cập nhật Env Vars Supabase Auth và URL allowlist trước khi deploy.
2. Chạy `.venv\Scripts\python.exe scripts/migrate.py`, rồi `.venv\Scripts\python.exe scripts/create_runtime_role.py` và `.venv\Scripts\python.exe scripts/check_database.py`.
3. Deploy code mới. Đăng ký/xác nhận email tài khoản đầu tiên ngay sau deploy; xe, log và giá nhập tay chưa có owner sẽ được gán cho tài khoản này một lần. Các tài khoản tiếp theo chỉ xem dữ liệu của họ.

Trước lần đăng nhập đầu tiên, đặt LEGACY_OWNER_EMAIL trên Vercel bằng đúng email sẽ sở hữu dữ liệu cũ; tài khoản phải xác nhận email. Nếu để trống, ứng dụng sẽ từ chối gán dữ liệu cũ để tránh tài khoản đăng ký trước nhận nhầm dữ liệu.
4. Đặt `CRON_SECRET` ngẫu nhiên dài tối thiểu 32 ký tự trong Vercel rồi redeploy. Cron chạy production hàng ngày theo lịch 10:30 UTC (17:30 giờ Việt Nam). Trên Hobby, Vercel có thể gọi vào bất kỳ phút nào trong giờ đó; khóa database chặn lần gọi trùng trong cùng ngày.
5. Kiểm tra đăng nhập, tạo/sửa/xóa xe và log, đăng xuất/đăng nhập tài khoản khác, giá thủ công và `/api/health`. Kiểm tra lịch sử chạy tại Vercel → Cron Jobs/Logs.

Giữ phiên bản database giữa các lần deploy. Vercel chỉ thay code/function; không chạy `DROP`, `TRUNCATE` hay reset schema khi cập nhật. Export JSON hiện có thể dùng làm bản sao dữ liệu tài khoản; khôi phục toàn bộ phải dùng backup PostgreSQL/Supabase.

## Nếu tạo mới

Tạo Supabase project → Connect → sao chép Session/Transaction pooler URL, không suy ra host bằng tên vùng. Trong `.env.local`:

| Biến | Cách dùng |
| --- | --- |
| MIGRATION_DATABASE_URL | Admin Session pooler, chỉ local |
| RUNTIME_DB_PASSWORD | Mật khẩu riêng cho role mới fuel_runtime, chỉ local |
| DATABASE_URL | Transaction pooler; user fuel_runtime.PROJECT_REF; mật khẩu runtime |
| APP_ORIGIN | URL app trên Vercel hoặc http://127.0.0.1:8000 ở local |
| TEST_DATABASE_URL | Database thử riêng, tên kết thúc _test |
| SUPABASE_URL | Project URL dạng https://PROJECT_REF.supabase.co |
| SUPABASE_ANON_KEY | Anon/publishable key cho Auth, không dùng service-role key |
| LEGACY_OWNER_EMAIL | Email đã xác nhận sở hữu dữ liệu cũ; bắt buộc trước đăng nhập đầu tiên nếu database có bản ghi chưa gán chủ |
| CRON_SECRET | Secret cho endpoint Cron giá xăng trên Vercel |

URL-encode ký tự đặc biệt trong mật khẩu của URI. RUNTIME_DB_PASSWORD dùng mật khẩu nguyên bản. Không dùng URL https Supabase, anon/service-role key thay cho PostgreSQL URI. Chạy `scripts/setup_database.py` để tạo schema, role và kiểm tra. Không tự import SQLite.

Runtime URL có thể dùng SUPABASE_DB_URL/POSTGRES_URL nếu chưa có DATABASE_URL, nhưng nên thống nhất DATABASE_URL. Backend tắt prepared statements cho Transaction pooler, bắt buộc SSL với host remote.

## GitHub và Vercel

Commit `backend/`, `migrations/`, `public/` (trừ vendor), `scripts/`, `tests/`, app.py, server.py, prices.py, requirements*.txt, package*.json, vercel.json, .python-version, .gitignore, .vercelignore, .env.example và tài liệu README/DATABASE/DEPLOYMENT.

Không commit `note/`, `.env.local`, `.venv/`, node_modules, public/vendor, __pycache__. Ảnh mẫu từng ở root đã chuyển vào note; Git sẽ ghi nhận xóa đường dẫn cũ khi bạn stage thay đổi. Không commit file chứa mật khẩu.

Vercel preset Flask; entrypoint app.py; build `npm ci && npm run setup:ocr`; không đặt Output Directory thành public. Public assets qua CDN; server.py chỉ dùng local. Vercel cần `DATABASE_URL`, `APP_ORIGIN`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` và `CRON_SECRET`. Không upload `MIGRATION_DATABASE_URL`/admin password. Lưu biến môi trường xong cần redeploy. Preview nên dùng database Supabase thử riêng; Cron chỉ chạy trên production.

API dữ liệu từ chối request không có Supabase access token. Public anon key không phải secret và không cấp quyền PostgreSQL; `fuel_app` không được thêm vào Supabase exposed schemas. Backend lọc dữ liệu xe/log theo user đã xác thực.

Trang thông cáo Petrolimex lưu các kỳ điều chỉnh, nhưng bảng giá trong thông cáo cũ được nhúng thành ảnh. Cron hiện đồng bộ giá hiện hành từ dữ liệu sidebar có cấu trúc; không tự điền giá quá khứ bằng suy đoán. Chỉ import lịch sử sau khi trích xuất và đối chiếu đủ nhiên liệu, vùng, và thời điểm hiệu lực.

## SQLite cũ

Đã chuyển vào `note/data/fuel.sqlite3`. Script import đọc-only, mặc định dry-run; chỉ nhận target chưa có xe/giá/log/metadata:

```powershell
.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py --audit-only
.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py
# Chỉ commit sau khi đã kiểm tra dry-run:
.venv\Scripts\python.exe scripts/migrate_sqlite_to_postgres.py --apply
```

Nếu file nằm nơi khác, thêm `--source <path>`. Không upload SQLite lên GitHub/Vercel.

Tham khảo chính thức: https://vercel.com/docs/frameworks/backend/flask và https://supabase.com/docs/guides/database/connecting-to-postgres.
