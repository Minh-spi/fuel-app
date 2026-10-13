# Kế hoạch nâng cấp

Cập nhật 13/10/2026. Trạng thái ghi theo code trong repo; phần cần cấu hình trên Supabase/Vercel hoặc xác nhận với dữ liệu thật được ghi riêng bên dưới.

## Nhận diện ODO tự động tốt hơn — Đã triển khai

- OCR chạy trên thiết bị bằng Tesseract.js, tự dò cụm số trên ảnh toàn khung; không bắt buộc khoanh vùng.
- Thử nhiều hướng ảnh và lượt tăng tương phản; cho phép xoay ảnh hoặc khoanh vùng thủ công khi cần.
- Hiển thị kết quả để người dùng kiểm tra/sửa trước khi lưu; lưu nguồn ODO là ảnh đã xác nhận.
- ODO đầu tiên vẫn là baseline, không tính quãng đường trước đó.
- Cần kiểm chứng thêm trên bộ ảnh đồng hồ thật đa dạng; OCR có thể đọc sai và không tự ghi log.

## Thống nhất cách nhập và hiển thị số — Đã triển khai

- Dùng quy ước tiếng Việt: dấu chấm phân tách hàng nghìn, dấu phẩy cho thập phân (`1.234,5 km`); VND hiển thị số nguyên.
- Chuyển giá trị nhập thành số chuẩn trước khi gửi API. Giá, tiền, ODO và dung tích bình được định dạng thống nhất trên giao diện.
- Kiểm tra tự động phần parsing/hiển thị trên browser test vẫn cần chạy với PostgreSQL test riêng.

## Dữ liệu giá nhiên liệu lịch sử đáng tin cậy — Công cụ backfill đã có; chưa nhập dữ liệu vào Supabase

- Đã xác minh endpoint sidebar Petrolimex cung cấp giá hiện hành có cấu trúc; lưu giá theo nhiên liệu, vùng, thời điểm hiệu lực, URL và thời điểm lấy.
- Bấm cập nhật ghi kết quả đồng bộ riêng; thống kê giá thêm mới, đổi, giữ nguyên. Cron Vercel chạy lúc 17:30 giờ Việt Nam, khóa tối đa một lượt/ngày.
- Giá cũ không bị sửa theo lần đồng bộ mới. Khi sửa log, giá snapshot được giữ cho tới khi người dùng chủ động dùng giá tham khảo hoặc nhập giá khác.
- Trang lịch sử PVOIL có bộ chọn kỳ giá và bảng hiển thị theo kỳ. Có công cụ chạy một lần bằng Edge thật để thu thập các mốc từ đầu năm, cùng importer preview mặc định và ghi database chỉ khi truyền `--apply`.
- Importer chỉ nhận loại nhiên liệu khớp danh mục app, giữ URL PVOIL làm nguồn, không sửa snapshot log; nếu bảng PVOIL không tách vùng thì mức công bố chung được lưu cho cả hai vùng. Cùng thời điểm, quote ưu tiên giá Petrolimex.
- **Chưa chạy bước thu thập/import thật.** Trang trả thử thách Cloudflare cho môi trường tự động; công cụ không vượt thử thách. Cần chạy capture trên máy người dùng, xác minh file JSON, rồi mới `--apply` vào database đã cấu hình.
- Giao diện hiển thị các mốc đã có từ đầu năm, báo khoảng trống và cho nhập giá thủ công với nguồn `manual`.
- Cron chỉ bắt đầu chạy sau khi deploy production và cấu hình `CRON_SECRET`; cần kiểm tra log lần chạy đầu tiên trên Vercel.

## Sửa dữ liệu cũ mà không tự điền sai — Đã triển khai

- Khi mở log cũ, giữ giá đã lưu; giá tra được chỉ là tham khảo. Chỉ cập nhật snapshot khi người dùng chọn rõ ràng.
- Cho sửa đơn giá thủ công; số lít được tính từ số tiền/đơn giá sau khi chọn. Trường ODO còn thiếu vẫn để trống.
- Sửa/xóa log vẫn kiểm tra thứ tự ODO và tính lại khoảng cách giữa các mốc cùng xe.

## Tài khoản và bảo toàn dữ liệu qua phiên bản — Code đã triển khai, cần cấu hình/xác nhận môi trường

- Có đăng ký, đăng nhập, đăng xuất, làm mới phiên và khôi phục mật khẩu qua Supabase Auth; API dữ liệu yêu cầu token và giới hạn xe/giá thủ công theo tài khoản.
- Migration 003 thêm chủ sở hữu và nhật ký sync theo hướng giữ dữ liệu. Trước lần đăng nhập đầu nếu DB có dữ liệu cũ, phải đặt `LEGACY_OWNER_EMAIL` là email đã xác nhận của chủ sở hữu; nếu thiếu cấu hình, app từ chối gán dữ liệu để tránh chiếm nhầm.
- Cần chạy migration 003 trên Supabase, cấp quyền role runtime, cấu hình biến Supabase/Vercel, xác nhận tài khoản sở hữu dữ liệu cũ và chạy công cụ PVOIL nếu muốn nạp lịch sử.
- Migration lưu bản xuất JSON phục vụ đối chiếu; đây **không thay thế** backup/restore toàn PostgreSQL. Chưa cấu hình hoặc thử khôi phục backup Supabase.

## Điều kiện hoàn tất vận hành

- Cấu hình `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`, `APP_ORIGIN`, `CRON_SECRET` và `LEGACY_OWNER_EMAIL` (nếu có dữ liệu cũ) trên Vercel; đặt URL chuyển hướng Auth đúng domain.
- Chạy migrations 001–003 trên Supabase và kiểm tra `/api/health` trả `database: ready`.
- Thiết lập backup tự động/khôi phục thử trước khi coi việc bảo toàn dữ liệu là hoàn tất.
