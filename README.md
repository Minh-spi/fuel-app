# Fuel — Nhật ký đổ nhiên liệu

Flask/Python 3.12 + Supabase PostgreSQL, frontend HTML/CSS/JavaScript responsive, OCR Tesseract.js chạy trên trình duyệt. Vercel nạp `app` từ `app.py`; `server.py` là launcher local. Không có SQLite runtime, thread đồng bộ nền hoặc Cron.

## Cấu trúc project

```text
backend/       Nghiệp vụ, kết nối PostgreSQL, kiểm tra database
migrations/    SQL có phiên bản, phải giữ cả 001 và 002
public/        Giao diện và OCR; vendor/ sinh từ npm
scripts/       Thiết lập, kiểm tra, migration và import dữ liệu
tests/         Kiểm thử nghiệp vụ, migration, API và trình duyệt
note/          Dữ liệu cũ, ảnh tham chiếu, ZIP, công cụ thử, backup — không lên GitHub/Vercel
```

`note/` giữ những file đã dọn, không phải thư mục runtime. Giữ `.venv/` và `node_modules/` ở root để các lệnh phát triển hoạt động; cả hai được Git bỏ qua. `.env.local` chứa secrets, cũng không được commit.

## Database mới

Một schema `fuel_app`, 7 bảng. Khóa chính nghiệp vụ là TEXT: xe `V1`, nhiên liệu `F1`, giá `P1`, lần đổ `R1`. Sequence riêng sinh số; không dùng MAX+1 hoặc tái sử dụng ID đã xóa.

- `fuel_types`: danh mục có `code` ổn định và `name` hiển thị, hỗ trợ nhóm xăng/diesel/khác.
- `vehicles`: loại xe, truyền động, hãng/dòng, đời xe, cc, dung tích bình, biển số tùy chọn, ngày mua, trạng thái và nhiên liệu mặc định.
- `fuel_prices`: mọi loại nhiên liệu chung một bảng; nguồn là URL thực tế hoặc đúng chuỗi `manual`.
- `refueling_logs`: dữ liệu trung tâm, snapshot giá/lít và loại nhiên liệu thực tế của lần đổ.
- `app_metadata`, `app_locks`, `schema_migrations`: trạng thái, khóa sync và phiên bản schema.

Chi tiết: [DATABASE.md](DATABASE.md). Baseline/quãng đường tính riêng mỗi xe từ lịch sử; không tính khoảng cách trước lần theo dõi đầu tiên. Log thiếu ODO không nội suy. Đổi loại nhiên liệu mặc định không thay đổi snapshot log cũ. Dung tích bình không đủ để suy ra mức tiêu hao hoặc nhiên liệu còn lại.

## Local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
npm.cmd run setup:ocr
# Chỉ sao chép nếu chưa có .env.local; không ghi đè mật khẩu đã lưu.
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
# Điền thông tin kết nối rồi chạy:
.venv\Scripts\python.exe scripts/setup_database.py
.venv\Scripts\python.exe server.py
```

Mở http://127.0.0.1:8000. Có thể thêm `--host 0.0.0.0` để truy cập từ điện thoại cùng mạng. Chỉ sync giá khi bấm cập nhật. Model OCR được pin qua npm, ảnh xử lý tại trình duyệt.

## Kiểm thử

Chỉ dùng database PostgreSQL UTF-8 riêng có tên kết thúc `_test`; test sẽ xóa dữ liệu trong schema của database thử. Python đọc `TEST_DATABASE_URL` từ `.env.local` hoặc environment. Với npm, đặt biến này trong environment trước khi chạy.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd run test:ui
```

UI test dùng Microsoft Edge headless, OCR ảnh số tổng hợp, mobile/desktop, xe mở rộng, giá theo giờ và lịch sử. Screenshots vào `note/test-results/`. Không dùng database production cho test.

## Nâng cấp / triển khai

**Code mới cần migration `002_fuel_catalog`. Không chạy code cũ với schema mới.** Xem [DEPLOYMENT.md](DEPLOYMENT.md) để chuyển đồng bộ code/database và giữ bản backup. Tác vụ refactor này được kiểm thử bằng PostgreSQL local; chưa tự deploy hoặc đổi schema Supabase đang phục vụ app cũ.
