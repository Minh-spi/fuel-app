# Fuel — Nhật ký đổ xăng

Frontend HTML/CSS/JavaScript và Tesseract.js giữ nguyên. Backend Flask/Python 3.12 dùng PostgreSQL (Supabase), entrypoint `app.py` cho Vercel Functions. `server.py` chạy cùng backend ở local. SQLite chỉ còn dùng để đọc dữ liệu cũ khi migration.

Nếu Vercel báo thiếu `DATABASE_URL`: cần tạo Supabase project trước, sau đó thiết lập database và biến môi trường theo [hướng dẫn sửa lỗi deployment](DEPLOYMENT.md#sửa-lỗi-trên-bản-vercel-hiện-tại). Code không tự tạo dịch vụ database. Dùng `scripts/setup_database.py` để tạo schema/cấp quyền và `scripts/check_database.py` hoặc `/api/health` để kiểm tra.

## Chạy local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd ci
npm.cmd run setup:ocr
Copy-Item .env.example .env.local
```

Điền connection strings trong `.env.local`, tạo schema theo [DEPLOYMENT.md](DEPLOYMENT.md), rồi chạy:

```powershell
.venv\Scripts\python.exe server.py
```

Mở http://127.0.0.1:8000. Thêm `--host 0.0.0.0` để dùng trên điện thoại cùng Wi-Fi. App cần PostgreSQL, không tự fallback về SQLite.

## Nghiệp vụ

- Nhiều xe; mặc định E10 RON 95-III, Đà Nẵng, vùng 1, bình 4 lít. Vùng giá có thể đổi theo cửa hàng.
- Nhập tiền/ngày; tra giá có hiệu lực để tính lít bằng Decimal. Ngày đổi giá giữa ngày cần giờ đổ.
- ODO tùy chọn, nhập tay hoặc OCR phía trình duyệt, người dùng xác nhận trước khi lưu; ảnh không gửi lên backend.
- Fuel log đầu mỗi xe là baseline. Log thiếu ODO không nội suy; mốc có ODO tiếp theo so với mốc đã biết gần nhất. Không tính khoảng cách trước mốc theo dõi.
- Đơn giá/số lít là snapshot. Sửa tiền/ODO giữ đơn giá; đổi ngày/giờ tra lại giá. Baseline và quãng đường tính lại từ lịch sử.
- Không suy ra mức tiêu hao hoặc xăng còn lại từ dung tích bình. `is_full_tank` chỉ giữ dữ liệu cũ.

## Sync giá

Chỉ chạy khi bấm **Cập nhật từ Petrolimex**, gọi `POST /api/prices/sync`. Không có background thread, sync lúc startup hoặc Cron. Parser đối chiếu giá thanh bên với thông báo hiệu lực; lỗi nguồn giữ giá cũ. Giá thủ công ưu tiên khi trùng mốc.

Do yêu cầu giữ nguyên UI, câu chữ cũ về tự đồng bộ lúc mở app/mỗi 6 giờ vẫn còn trong giao diện; câu đó không mô tả backend mới. Chưa sửa trong phase migration.

## Kiểm thử

Tạo database PostgreSQL UTF-8 riêng có tên kết thúc `_test`. Điền `TEST_DATABASE_URL` trỏ database thử. Test xóa dữ liệu trong schema `fuel_app` của database đó; không dùng database thật.

```powershell
# Python tự đọc TEST_DATABASE_URL từ .env.local hoặc biến môi trường.
.venv\Scripts\python.exe -m unittest discover -s tests -v
# Với Node, truyền TEST_DATABASE_URL qua biến môi trường trước khi chạy:
npm.cmd run test:ui
```

Test backend kiểm tra API, Decimal, baseline, giá theo giờ, migration, ghi đồng thời và khóa sync. Test UI dùng Microsoft Edge headless, OCR thật trên ảnh số tổng hợp, mobile/desktop, sửa/xóa/lưu và nhiều xe. Chưa xác minh OCR bằng ảnh đồng hồ thực tế.

Schema: `migrations/001_initial.sql`. Hướng dẫn tạo Supabase, import SQLite, deploy và danh sách file GitHub: [DEPLOYMENT.md](DEPLOYMENT.md).
