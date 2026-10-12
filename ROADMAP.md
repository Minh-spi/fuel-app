# Kế hoạch nâng cấp

Các mục dưới đây là ý tưởng đã thống nhất để xem xét ở các phiên bản sau. Chúng chưa được triển khai và không làm thay đổi luồng đang dùng.

## Nhận diện ODO tự động tốt hơn

- Giữ cách chụp ảnh ODO và xác nhận/sửa số trước khi lưu.
- Mặc định tự tìm vùng hiển thị công-tơ-mét để người dùng không phải khoanh vùng thủ công mỗi lần.
- Giảm nhầm các số tốc độ và vạch chia trên mặt đồng hồ; hỗ trợ ảnh xoay, thiếu sáng, lóa và nghiêng.
- Chỉ đề nghị khoanh vùng ODO thủ công khi tự tìm vùng hoặc OCR có độ tin cậy thấp.
- Tính quãng đường từ hai mốc ODO đã xác nhận gần nhất của cùng xe; ODO đầu tiên là baseline.

## Thống nhất cách nhập và hiển thị số

- Dùng một quy ước định dạng theo tiếng Việt trên toàn app: dấu chấm phân tách hàng nghìn, dấu phẩy cho phần thập phân (ví dụ `1.234,5 km`). Tiền VND hiển thị số nguyên có phân tách hàng nghìn.
- Chuẩn hóa dữ liệu số thành giá trị số trước khi lưu/tính toán; chỉ định dạng ở giao diện để phép tính không phụ thuộc dấu phân cách.
- Ô nhập và thông báo lỗi phải theo cùng quy ước; kiểm tra các trường tiền, ODO, lít và đơn giá trên cả điện thoại lẫn máy tính.

## Dữ liệu giá nhiên liệu lịch sử đáng tin cậy

- Khảo sát khả năng lấy bảng giá Petrolimex chính thức cho toàn bộ khoảng thời gian từ đầu năm hiện tại đến ngày cào; lưu ngày giá có hiệu lực, nhiên liệu, vùng, đơn giá, URL nguồn và thời điểm lấy dữ liệu.
- Không tự điền hoặc tạo giá cho những ngày mà nguồn không xác nhận. Đánh dấu khoảng trống để người dùng có thể bổ sung thủ công với nguồn `manual`.
- Tách lịch sử lần cào/kết quả đồng bộ khỏi bảng giá hiệu lực. Cào lại cùng ngày không tạo bản ghi giá trùng nếu giá không đổi; nếu giá đổi thì lưu đúng ngày hiệu lực theo nguồn.
- Ưu tiên cào khi người dùng bấm cập nhật trước. Sau khi xác minh nguồn, múi giờ, giới hạn truy cập và xử lý lỗi, cân nhắc tác vụ chạy tự động mỗi ngày, tối đa một lần/ngày; chưa cấu hình Cron trước khi kiểm thử.
- Khi đối chiếu log cũ, không âm thầm thay đơn giá hoặc số lít đã lưu. Cho phép xem giá tham khảo và chọn áp dụng có chủ ý; không dùng giá hiện tại để suy ngược giá lịch sử.

## Sửa dữ liệu cũ mà không tự điền sai

- Khi sửa log cũ, giữ nguyên snapshot giá/lít đang lưu và không tự thay bằng giá thị trường tra được nếu người dùng chưa chọn.
- Không điền phỏng đoán vào trường thiếu. Để trống trường chưa biết và cho người dùng chủ động nhập hoặc chọn một giá lịch sử đã xác minh.
- Nếu đổi ngày, nhiên liệu, số tiền hoặc đơn giá, báo rõ trường tính toán nào sẽ thay đổi; chỉ tính lại khi người dùng xác nhận lựa chọn đó.
- Giữ khả năng sửa và xóa log, đồng thời kiểm tra lại thứ tự ODO và quãng đường liên quan sau khi sửa.

## Tài khoản và bảo toàn dữ liệu qua phiên bản

- Bổ sung đăng ký, đăng nhập, đăng xuất và khôi phục mật khẩu; mỗi tài khoản chỉ truy cập xe, log và dữ liệu riêng của mình.
- Gắn dữ liệu hiện có với một tài khoản trước khi bật yêu cầu đăng nhập, để dữ liệu cũ không biến mất hoặc bị gán nhầm.
- Mỗi lần đổi schema dùng migration có phiên bản, theo hướng giữ dữ liệu; không xóa/tạo lại database khi cập nhật app.
- Thiết lập và kiểm thử backup/khôi phục trước các thay đổi schema lớn; kiểm tra deployment mới với bản sao dữ liệu trước khi đưa vào dùng.
- Kiểm thử đường nâng cấp từ phiên bản đang chạy và xác nhận dữ liệu còn nguyên sau deploy/rollback.

## Nguyên tắc triển khai

- Chưa thực hiện mục OCR trong phiên bản hiện tại.
- Ưu tiên giải pháp chạy trên thiết bị bằng Tesseract.js hiện có; chỉ cân nhắc dịch vụ OCR ngoài nếu thử nghiệm cho thấy cần thiết.
- Đánh giá bằng ảnh thực tế từ nhiều góc chụp và yêu cầu xác nhận của người dùng trước khi ghi dữ liệu.
- Không thay đổi giao diện hay luồng nhập liệu hiện tại khi chưa bắt đầu hạng mục này.
