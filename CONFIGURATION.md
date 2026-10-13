# Cấu hình kết nối local, Vercel và Supabase

## Ai làm việc gì?

- **Vercel** chạy Flask API và phục vụ frontend.
- **Supabase Auth** đăng ký, đăng nhập và xác nhận tài khoản.
- **Supabase PostgreSQL** lưu xe, lần đổ xăng, giá nhiên liệu và schema của app.
- Đăng ký Auth không tự tạo bảng PostgreSQL. Cần chạy setup database một lần từ máy local.

```text
Trình duyệt ── app/API ──> Vercel ── DATABASE_URL ──> Supabase PostgreSQL
     └──────── đăng nhập/xác nhận ──────────────────> Supabase Auth
```

## File cấu hình local

Điền các biến trong `.env.local` ở thư mục gốc. File này được Git và Vercel bỏ qua; không commit, không gửi qua chat và không đưa nguyên file lên Vercel. Các giá trị trong file hiện để trống có chủ ý.

| Biến | Nơi lấy / cách dùng |
| --- | --- |
| `DATABASE_URL` | Supabase → **Connect** → **Transaction pooler**. Runtime connection cho local và Vercel, thường dùng cổng 6543. Khi role đã được tạo, dùng user `fuel_runtime.<project-ref>` và mật khẩu runtime. |
| `MIGRATION_DATABASE_URL` | Supabase → **Connect** → **Session pooler**, dùng tài khoản quản trị để tạo/cập nhật schema và cấp quyền; thường cổng 5432. Chỉ dùng local, không đưa lên Vercel. |
| `RUNTIME_DB_PASSWORD` | Mật khẩu riêng role PostgreSQL `fuel_runtime`, do bạn đặt khi khởi tạo role. Nếu role đã tồn tại, phải nhập đúng mật khẩu hiện tại; script không tự đổi mật khẩu. |
| `SUPABASE_URL` | Trong Supabase Dashboard, mở **Connect** và sao chép **Project URL**; hoặc **Integrations → Data API → API URL**. Giá trị có dạng `https://<project-ref>.supabase.co`. Đây là URL Auth dùng, không phải API key và không phải chuỗi kết nối PostgreSQL. |
| `SUPABASE_ANON_KEY` hoặc `SUPABASE_PUBLISHABLE_KEY` | **Settings → API Keys**: chọn public `anon` hoặc `publishable` key. Chỉ cần điền một biến; không dùng `service_role`/secret key. |
| `APP_ORIGIN` | Khi chạy local, domain local app; trên Vercel, domain deployment chính. Không thêm dấu `/` cuối. |
| `CRON_SECRET` | Chuỗi ngẫu nhiên riêng dài tối thiểu 32 ký tự để bảo vệ endpoint Cron. Local có thể để trống nếu không thử Cron; Vercel Production cần đặt. |
| `LEGACY_OWNER_EMAIL` | Chỉ cần nếu PostgreSQL có dữ liệu cũ chưa gán chủ. Điền email đã xác nhận của tài khoản sẽ sở hữu dữ liệu đó. Nếu database mới hoàn toàn, để trống. |

Không cần thêm các biến timeout trừ khi muốn thay đổi mặc định của backend. Không dán dấu nháy quanh giá trị. Với connection string, ký tự đặc biệt trong mật khẩu phải được URL-encode.

## Khởi tạo PostgreSQL một lần

1. Điền `MIGRATION_DATABASE_URL` và `RUNTIME_DB_PASSWORD` trong `.env.local`.
2. Điền `DATABASE_URL` với user runtime và cùng mật khẩu runtime. Nếu chưa có role, tạo chuỗi runtime theo thông tin Transaction pooler và username `fuel_runtime.<project-ref>`.
3. Tại PowerShell, từ `D:\fuel-app`, chạy:

   ```powershell
   .venv\Scripts\python.exe scripts/setup_database.py
   ```

4. Kết quả thành công phải có `database: ready`. Script chạy tất cả migration còn thiếu theo thứ tự, cấp quyền cho role runtime và kiểm tra kết nối. Chỉ chạy lại khi cần bổ sung migration/quyền; không chạy khi khởi động app trên Vercel.

Nếu đây không phải database mới, hãy sao lưu trước. Migration 002 ghi bản sao các bảng cũ vào `note/backups/` trước khi thay đổi cấu trúc; bản sao này không thay thế backup đầy đủ của Supabase.

## Biến cần đặt trên Vercel

Điền giá trị thật vào file `.env.vercel` riêng (file này bị Git bỏ qua), rồi vào Vercel → project → **Settings → Environment Variables** và chọn **Import .env**. Chọn `.env.vercel`, áp dụng cho **Production**; thêm **Preview** nếu cần. Mỗi lần thay đổi biến phải redeploy. Vercel nhập từng cặp tên/giá trị thành Environment Variables; thao tác này không upload file vào source code của deployment.

| Biến | Giá trị cần đặt |
| --- | --- |
| `DATABASE_URL` | PostgreSQL **Transaction pooler** của Supabase, user `fuel_runtime.<project-ref>`, mật khẩu runtime, SSL. |
| `SUPABASE_URL` | Project URL Supabase có dạng `https://<project-ref>.supabase.co`; không phải key. |
| `SUPABASE_ANON_KEY` hoặc `SUPABASE_PUBLISHABLE_KEY` | Public key lấy riêng trong **Settings → API Keys**; không dùng service-role/secret key. |
| `APP_ORIGIN` | Domain Vercel chính của app. |
| `CRON_SECRET` | Cùng secret dài tối thiểu 32 ký tự được dùng cho Cron. |
| `LEGACY_OWNER_EMAIL` | Chỉ khi database có dữ liệu cũ chưa gán chủ; phải khớp email tài khoản đã xác nhận. |


## URL đăng nhập Supabase

Trong Supabase → **Authentication → URL Configuration**:

- Đặt Site URL là domain Vercel chính.
- Thêm domain Vercel và `http://127.0.0.1:8000` vào Redirect URLs nếu dùng local.
- Sau khi thay cấu hình Auth hoặc Environment Variables, thử lại bằng deployment mới.

## File cấu hình khác

- `.gitignore` bỏ qua `.env.local` và mọi file `.env*`; không đưa credential vào Git.
- `.vercelignore` loại file bí mật và dữ liệu local khỏi gói deploy.
- `vercel.json` chỉ cấu hình Flask build, function và lịch Cron; không chứa URL hay secret.
- `.env.example` đã được bỏ vì app không tự đọc file đó. Các biến local được ghi trực tiếp trong `.env.local`; hướng dẫn có thể đưa lên GitHub nằm trong file này.
