# Fuel — Nhật ký đổ nhiên liệu

Flask/Python 3.12 + Supabase PostgreSQL, Supabase Auth, frontend HTML/CSS/JavaScript responsive, OCR Tesseract.js chạy trên trình duyệt. Vercel nạp `app` từ `app.py`; `server.py` là launcher local. Giá hiện tại được đồng bộ theo nút bấm và Cron một lần mỗi ngày; không có background thread.

## Cấu trúc project

```text
backend/       Nghiệp vụ, kết nối PostgreSQL, kiểm tra database
migrations/    SQL có phiên bản, phải giữ 001, 002 và 003
public/        Giao diện và OCR; vendor/ sinh từ npm
scripts/       Thiết lập, kiểm tra, migration và import dữ liệu
tests/         Kiểm thử nghiệp vụ, migration, API và trình duyệt
note/          Dữ liệu cũ, ảnh tham chiếu, ZIP, công cụ thử, backup — không lên GitHub/Vercel
```

`note/` giữ những file đã dọn, không phải thư mục runtime. Giữ `.venv/` và `node_modules/` ở root để các lệnh phát triển hoạt động; cả hai được Git bỏ qua. `.env.local` chứa secrets, cũng không được commit.

## Database mới

Một schema `fuel_app`, hiện có 8 bảng. Khóa chính nghiệp vụ là TEXT: xe `V1`, nhiên liệu `F1`, giá `P1`, lần đổ `R1`. Sequence riêng sinh số; không dùng MAX+1 hoặc tái sử dụng ID đã xóa.

- `fuel_types`: danh mục có `code` ổn định và `name` hiển thị, hỗ trợ nhóm xăng/diesel/khác.
- `vehicles`: loại xe, truyền động, hãng/dòng, đời xe, cc, dung tích bình, biển số tùy chọn, ngày mua, trạng thái và nhiên liệu mặc định.
- `fuel_prices`: mọi loại nhiên liệu chung một bảng; nguồn là URL thực tế hoặc đúng chuỗi `manual`.
- `refueling_logs`: dữ liệu trung tâm, snapshot giá/lít và loại nhiên liệu thực tế của lần đổ.
- `app_metadata`, `app_locks`, `price_sync_runs`, `schema_migrations`: trạng thái, khóa đồng bộ, nhật ký từng lượt lấy giá và phiên bản schema.

Supabase Auth quản lý đăng ký/đăng nhập/khôi phục mật khẩu. API xác minh access token với Supabase Auth; `vehicles.owner_id` giới hạn dữ liệu từng tài khoản. Giá tự động là dữ liệu tham chiếu dùng chung; giá nhập tay thuộc tài khoản tạo nó. Nếu database còn dữ liệu cũ chưa gán chủ, phải cấu hình `LEGACY_OWNER_EMAIL` bằng email đã xác nhận của chủ sở hữu trước khi đăng nhập đầu tiên.

Chi tiết: [DATABASE.md](DATABASE.md). Baseline/quãng đường tính riêng mỗi xe từ lịch sử; không tính khoảng cách trước lần theo dõi đầu tiên. Log thiếu ODO không nội suy. Đổi loại nhiên liệu mặc định không thay đổi snapshot log cũ. Dung tích bình không đủ để suy ra mức tiêu hao hoặc nhiên liệu còn lại.

## Local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
npm.cmd run setup:ocr
# Điền các biến trong .env.local theo hướng dẫn tại CONFIGURATION.md rồi chạy:
.venv\Scripts\python.exe scripts/setup_database.py
.venv\Scripts\python.exe server.py
```

Mở http://127.0.0.1:8000. Có thể thêm `--host 0.0.0.0` để truy cập từ điện thoại cùng mạng. Chỉ sync giá khi bấm cập nhật. Model OCR được pin qua npm, ảnh xử lý tại trình duyệt.

Trong `.env.local`, lấy `SUPABASE_URL` ở Supabase Dashboard → **Connect** → **Project URL** (hoặc **Integrations → Data API → API URL**); lấy `SUPABASE_ANON_KEY`/`SUPABASE_PUBLISHABLE_KEY` riêng ở **Settings → API Keys**. URL phải dạng `https://<project-ref>.supabase.co`, không phải key hay database connection string. Thêm `http://127.0.0.1:8000` vào Supabase Auth → URL Configuration → Redirect URLs để xác nhận email và đặt lại mật khẩu hoạt động local.

## Nhập lịch sử giá PVOIL một lần

Trang [Tin giá xăng dầu PVOIL](https://www.pvoil.com.vn/tin-gia-xang-dau) có bộ chọn các kỳ giá. Công cụ dưới đây mở Microsoft Edge thường để bạn hoàn tất xác minh trang nếu được yêu cầu; nó không tự vượt Cloudflare. Mặc định chỉ thu thập từ đầu năm hiện tại. Bản chụp thô được ghi vào `note/` (không lên Git).

```powershell
node scripts/capture_pvoil_history.cjs 2026
.venv\Scripts\python.exe scripts/import_pvoil_history.py --input note/pvoil_history.json
# Kiểm tra bản chụp, rồi mới ghi dữ liệu:
.venv\Scripts\python.exe scripts/import_pvoil_history.py --input note/pvoil_history.json --apply
```

Lệnh đầu chỉ chụp; lệnh import mặc định chỉ preview. `--apply` mới ghi vào `DATABASE_URL` trong `.env.local`, theo cách idempotent và dừng toàn transaction nếu giá xung đột. PVOIL không tách vùng trong bảng thì cùng mức giá công bố được lưu cho cả hai vùng. Giá có nguồn Petrolimex được ưu tiên khi cùng thời điểm; các log đã lưu không bị đổi. Chỉ các loại nhiên liệu khớp danh mục app được nhập, các loại dầu diesel khác được đếm là bỏ qua.

## Kiểm thử

Run the unit tests that do not connect to PostgreSQL:


```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```


## Nâng cấp / triển khai

**Code mới cần migration `003_ownership_and_sync` sau 001/002.** Xem [DEPLOYMENT.md](DEPLOYMENT.md) để cấu hình Auth, giữ dữ liệu cũ và nâng schema. Deploy Vercel không xóa PostgreSQL; migrations được áp dụng riêng, có phiên bản.
