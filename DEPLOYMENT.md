# Vercel + Supabase: triển khai và nâng cấp v2

## Nếu đang chạy bản cũ

Migration 002 thay đổi tên bảng/cột và ID; phải nâng cấp backend/frontend cùng schema. Không chạy migration production trong lúc app cũ tiếp tục ghi.

1. Thử migration trên database thử hoặc bản sao. Giữ commit/deployment cũ và backup PostgreSQL trước thay đổi. Dừng ghi/tạm bảo trì app khi chuyển production.
2. Điền `MIGRATION_DATABASE_URL` vào `.env.local` local, dùng admin Session pooler (5432) hoặc direct URL đúng project. `DATABASE_URL` dùng runtime Transaction pooler (6543). Không nhầm với TEST_DATABASE_URL.
3. Chạy `.venv\Scripts\python.exe scripts/migrate.py`. Script chạy migration còn thiếu trong transaction, trước 002 khóa ghi và xuất bản sao các bảng v1/sequence vào `note/backups/`. Nếu không ghi được backup hoặc SQL lỗi, rollback transaction. Bản JSON này dùng đối chiếu/khôi phục thủ công với schema v1; không thay thế backup PostgreSQL đầy đủ và không có nút restore tự động.
4. Chạy `.venv\Scripts\python.exe scripts/create_runtime_role.py` để bảo đảm quyền đọc danh mục và dùng sequence mới. Không đổi mật khẩu role đang có.
5. Chạy `.venv\Scripts\python.exe scripts/check_database.py`, cần `database: ready`.
6. Deploy code mới lên Vercel rồi kiểm tra `/api/health`, `/api/state`, thêm/sửa/xóa, nhiều xe, OCR, giá theo ngày. Mở lại ghi sau khi kiểm tra. Reload các tab cũ để lấy frontend mới.

Nếu có lỗi sau cutover, không chỉ rollback deployment về code cũ: schema mới không tương thích code cũ. Cần khôi phục schema/dữ liệu từ backup trong cửa sổ bảo trì, giữ mọi dữ liệu mới phát sinh để đối chiếu. Không drop bảng production để thử lại.

## Nếu tạo mới

Tạo Supabase project → Connect → sao chép Session/Transaction pooler URL, không suy ra host bằng tên vùng. Trong `.env.local`:

| Biến | Cách dùng |
| --- | --- |
| MIGRATION_DATABASE_URL | Admin Session pooler, chỉ local |
| RUNTIME_DB_PASSWORD | Mật khẩu riêng cho role mới fuel_runtime, chỉ local |
| DATABASE_URL | Transaction pooler; user fuel_runtime.PROJECT_REF; mật khẩu runtime |
| APP_ORIGIN | URL app trên Vercel hoặc http://127.0.0.1:8000 ở local |
| TEST_DATABASE_URL | Database thử riêng, tên kết thúc _test |

URL-encode ký tự đặc biệt trong mật khẩu của URI. RUNTIME_DB_PASSWORD dùng mật khẩu nguyên bản. Không dùng URL https Supabase, anon/service-role key thay cho PostgreSQL URI. Chạy `scripts/setup_database.py` để tạo schema, role và kiểm tra. Không tự import SQLite.

Runtime URL có thể dùng SUPABASE_DB_URL/POSTGRES_URL nếu chưa có DATABASE_URL, nhưng nên thống nhất DATABASE_URL. Backend tắt prepared statements cho Transaction pooler, bắt buộc SSL với host remote.

## GitHub và Vercel

Commit `backend/`, `migrations/`, `public/` (trừ vendor), `scripts/`, `tests/`, app.py, server.py, prices.py, requirements*.txt, package*.json, vercel.json, .python-version, .gitignore, .vercelignore, .env.example và tài liệu README/DATABASE/DEPLOYMENT.

Không commit `note/`, `.env.local`, `.venv/`, node_modules, public/vendor, __pycache__. Ảnh mẫu từng ở root đã chuyển vào note; Git sẽ ghi nhận xóa đường dẫn cũ khi bạn stage thay đổi. Không commit file chứa mật khẩu.

Vercel preset Flask; entrypoint app.py; build `npm ci && npm run setup:ocr`; không đặt Output Directory thành public. Public assets qua CDN; server.py chỉ dùng local. Vercel Environment Variables chỉ cần DATABASE_URL, APP_ORIGIN và timeout nếu tùy chỉnh. Không upload MIGRATION_DATABASE_URL/admin password. Save biến môi trường xong cần redeploy. Preview dùng database thử riêng.

App chưa có đăng nhập/phân quyền người dùng; bảo vệ deployment trước khi dùng dữ liệu cá nhân. Origin check không thay thế xác thực. Không thêm fuel_app vào Supabase exposed schemas.

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
