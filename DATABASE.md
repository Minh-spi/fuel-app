# Database v2

Schema `fuel_app` trong một PostgreSQL database. Không thêm schema này vào Supabase exposed schemas. Backend kết nối PostgreSQL trực tiếp, không dùng Supabase Data API.

| Bảng | ID / khóa | Dữ liệu |
| --- | --- | --- |
| `vehicles` | `V` + sequence | owner_id, name, default_fuel_type_id, vehicle_type, transmission_type, brand, model, model_year, engine_displacement_cc, tank_capacity_liters, license_plate, purchased_on, city, price_zone, notes, is_active, created_at, updated_at |
| `fuel_types` | `F` + sequence | code UNIQUE, name UNIQUE, category, is_active, created_at, updated_at |
| `fuel_prices` | `P` + sequence | owner_id nullable for shared Petrolimex rows, fuel_type_id, price_zone, effective_at, unit_price_vnd_per_liter, source_url, source_updated_at, created_at, updated_at |
| `refueling_logs` | `R` + sequence | vehicle_id, fuel_type_id, fuel_price_id nullable, refueled_on, refueled_time nullable, odometer_tenths nullable, total_cost_vnd, unit_price_vnd_per_liter, volume_liters, price_zone, odo_source, notes, created_at, updated_at |
| `app_metadata` | key | value |
| `app_locks` | name | token UUID, expires_at |
| `price_sync_runs` | identity | run_date, trigger, status, started_at, finished_at, observed/inserted/changed/unchanged row counts, safe error message |
| `schema_migrations` | version | applied_at |

ID là khóa thật, không có ID số thứ hai. Số có thể nhảy do rollback/xóa; không dùng ID để đếm bản ghi. Sequence và PRIMARY KEY bảo vệ việc cấp ID đồng thời. Tiền tố cố định theo đối tượng, không đổi khi đổi tên bảng. Truy vấn dùng phần số làm tie-breaker khi ngày/giờ trùng để R10 không đứng trước R2.

`vehicle_type`: motorcycle/car/other/unknown. `transmission_type`: automatic/semi_automatic/manual/other/unknown. Trên form giải thích ga/số/côn tay; các thông tin bổ sung đều không bắt buộc. Biển số trống lưu NULL. Xe đang có bình 4 lít được giữ; hồ sơ mới mặc định 4 lít trên form và có thể sửa/xóa. Xe ngừng sử dụng vẫn giữ và xem được lịch sử.

Danh mục ban đầu giữ 4 sản phẩm app đang hỗ trợ. Có thể thêm nhiên liệu khác bằng migration/SQL với `code`, `name`, `category`; ID F tự sinh. Chưa có màn hình quản trị danh mục. Crawler đối chiếu code ổn định, không phụ thuộc tên hiển thị bị đổi. Hỗ trợ danh mục diesel không có nghĩa crawler hiện đã hỗ trợ nguồn giá diesel.

`source_url` bắt buộc là `manual` hoặc HTTP(S) URL. Giá Petrolimex có `owner_id=NULL` và dùng chung. Giá nhập tay giữ đúng source `manual` và có owner; người khác không nhìn thấy hoặc ghi đè chúng. Tính duy nhất của giá tự động và giá manual được tách bằng partial unique index. Tra giá mới nhất trước lúc đổ, ưu tiên giá manual của chính người dùng nếu trùng mốc, rồi updated_at và số ID.

Mỗi xe có `default_fuel_type_id`; form lần đổ mặc định theo xe nhưng cho chọn loại xăng riêng từng lần. API xác minh Supabase Auth token rồi chỉ truy cập xe của `owner_id`; log được giới hạn theo chủ xe. Giá Petrolimex và danh mục nhiên liệu là dữ liệu tham chiếu dùng chung. `refueling_logs` lưu snapshot đơn giá/lít. Khi sửa log, giá đã lưu được giữ nguyên kể cả đổi ngày/giờ/nhiên liệu; giao diện chỉ dùng giá tra được nếu người dùng bấm áp dụng. Đơn giá tùy chỉnh hoặc tham khảo được xác nhận rõ ràng. Log giữ đơn giá và lít NUMERIC(20,6); tiền nguyên đồng BIGINT, ODO nguyên theo 0,1 km. Không dựng giá thị trường giả hay suy ra xăng còn lại. Log đầu là baseline; ODO đầu tiên được biết cũng chưa có khoảng cách nếu trước đó thiếu ODO.

`price_sync_runs` ghi riêng từng lượt bấm tay và lượt Cron. Cron có một lượt tối đa mỗi ngày Việt Nam, ghi số mức giá được thêm/thay đổi/giữ nguyên. Nó chỉ đọc bảng dữ liệu cấu trúc hiện tại của Petrolimex, không tạo giá mới nếu ngày hiệu lực không thay đổi.

## API v2

Giữ đường dẫn GET `/api/state`, `/api/quote`, `/api/health`; POST `/api/vehicles`, `/api/logs`, `/api/logs/delete`, `/api/prices`, `/api/prices/sync`, `/api/sample`. Các API dữ liệu yêu cầu `Authorization: Bearer <Supabase access token>`. `/api/config` chỉ trả Supabase URL và public anon/publishable key; `/api/prices/cron` yêu cầu `Authorization: Bearer <CRON_SECRET>`.

Payload/response dùng ID dạng chuỗi; `filled_on/time` đổi thành `refueled_on/time`; `price_id` thành `fuel_price_id`; giá dùng `unit_price_vnd_per_liter`; xe dùng `default_fuel_type_id`; giá dùng `fuel_type_id`. `state.fuel_types` là danh sách object, không còn mảng tên chuỗi. Các API cũ theo tên đường dẫn vẫn tồn tại nhưng client cũ cần nâng cấp payload cùng frontend mới.

Ví dụ nhập giá:

```json
{"fuel_type_id":"F1","price_zone":1,"effective_at":"2026-10-01T15:00+07:00","unit_price_vnd_per_liter":25000}
```

POST `/api/prices` luôn gán `source_url=manual`. POST `/api/logs`:

```json
{"vehicle_id":"V1","refueled_on":"2026-10-02","total_cost_vnd":50000,"odometer_km":17200}
```

## Dữ liệu cũ

`001_initial.sql` giữ nguyên. `002_fuel_catalog.sql` đổi ID `12 → V12`, `7 → P7`, `42 → R42` và tên bảng/cột; bản sao trước thay đổi được giữ trong `note/backups/`. `003_ownership_and_sync.sql` thêm owner cho xe/giá nhập tay, nhật ký đồng bộ và index duy nhất mà không xóa snapshot dữ liệu. Giá lịch sử/log cũ vẫn nguyên trạng. Khi tài khoản đầu tiên gọi API sau nâng cấp, các xe chưa có owner được gán một lần cho tài khoản đó; các tài khoản tiếp theo không thể nhận dữ liệu này.

Không tự chuyển dữ liệu thật khi app khởi động. Import SQLite chỉ vào target trống, có dry-run, ánh xạ sang ID/catalog mới và đối chiếu các trường sau chuyển đổi.
