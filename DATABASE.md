# Database v2

Schema `fuel_app` trong một PostgreSQL database. Không thêm schema này vào Supabase exposed schemas. Backend kết nối PostgreSQL trực tiếp, không dùng Supabase Data API.

| Bảng | ID / khóa | Dữ liệu |
| --- | --- | --- |
| `vehicles` | `V` + sequence | name, default_fuel_type_id, vehicle_type, transmission_type, brand, model, model_year, engine_displacement_cc, tank_capacity_liters, license_plate, purchased_on, city, price_zone, notes, is_active, created_at, updated_at |
| `fuel_types` | `F` + sequence | code UNIQUE, name UNIQUE, category, is_active, created_at, updated_at |
| `fuel_prices` | `P` + sequence | fuel_type_id, price_zone, effective_at, unit_price_vnd_per_liter, source_url, source_updated_at, created_at, updated_at |
| `refueling_logs` | `R` + sequence | vehicle_id, fuel_type_id, fuel_price_id nullable, refueled_on, refueled_time nullable, odometer_tenths nullable, total_cost_vnd, unit_price_vnd_per_liter, volume_liters, price_zone, odo_source, notes, created_at, updated_at |
| `app_metadata` | key | value |
| `app_locks` | name | token UUID, expires_at |
| `schema_migrations` | version | applied_at |

ID là khóa thật, không có ID số thứ hai. Số có thể nhảy do rollback/xóa; không dùng ID để đếm bản ghi. Sequence và PRIMARY KEY bảo vệ việc cấp ID đồng thời. Tiền tố cố định theo đối tượng, không đổi khi đổi tên bảng. Truy vấn dùng phần số làm tie-breaker khi ngày/giờ trùng để R10 không đứng trước R2.

`vehicle_type`: motorcycle/car/other/unknown. `transmission_type`: automatic/semi_automatic/manual/other/unknown. Trên form giải thích ga/số/côn tay; các thông tin bổ sung đều không bắt buộc. Biển số trống lưu NULL. Xe đang có bình 4 lít được giữ; hồ sơ mới mặc định 4 lít trên form và có thể sửa/xóa. Xe ngừng sử dụng vẫn giữ và xem được lịch sử.

Danh mục ban đầu giữ 4 sản phẩm app đang hỗ trợ. Có thể thêm nhiên liệu khác bằng migration/SQL với `code`, `name`, `category`; ID F tự sinh. Chưa có màn hình quản trị danh mục. Crawler đối chiếu code ổn định, không phụ thuộc tên hiển thị bị đổi. Hỗ trợ danh mục diesel không có nghĩa crawler hiện đã hỗ trợ nguồn giá diesel.

`source_url` bắt buộc là `manual` hoặc HTTP(S) URL. Không có source/is_manual. Crawler lưu URL endpoint cung cấp bảng giá; thời điểm hiệu lực vẫn đối chiếu thông báo. Bản ghi giá duy nhất theo `(fuel_type_id, price_zone, effective_at, source_url)`. Tra giá mới nhất trước lúc đổ, ưu tiên manual nếu trùng mốc, rồi updated_at và số ID. Index chính `(fuel_type_id,price_zone,effective_at DESC)`.

Log giữ đơn giá và lít NUMERIC(20,6); tiền nguyên đồng BIGINT, ODO nguyên theo 0,1 km. FK fuel_price_id có thể NULL cho lịch sử/sample; không dựng giá thị trường giả. Sửa tiền/ODO/ghi chú giữ giá và nhiên liệu đã lưu, đổi ngày/giờ/xe tra lại theo mặc định xe. Không suy ra xăng còn lại hoặc mức tiêu hao từ dung tích bình. Log đầu là baseline; ODO đầu tiên được biết cũng chưa có khoảng cách nếu trước đó thiếu ODO.

## API v2

Giữ đường dẫn GET `/api/state`, `/api/quote`, `/api/health`; POST `/api/vehicles`, `/api/logs`, `/api/logs/delete`, `/api/prices`, `/api/prices/sync`, `/api/sample`.

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

`001_initial.sql` giữ nguyên để nâng cấp có phiên bản. `002_fuel_catalog.sql` đổi ID `12 → V12`, `7 → P7`, `42 → R42` và tất cả FK trong transaction, giữ high-water mark sequence kể cả ID đã xóa. Đổi fuel_logs→refueling_logs, metadata→app_metadata. Các cột source/price_source/volume_source/is_full_tank được bỏ theo thiết kế; bản sao trước migration giữ giá trị cũ trong `note/backups/`. Snapshot số tiền, đơn giá, lít và timestamps lịch sử được giữ; bảng giá thêm created_at lấy từ timestamp fetched_at cũ vì không có thời điểm tạo chính xác hơn.

Không tự chuyển dữ liệu thật khi app khởi động. Import SQLite chỉ vào target trống, có dry-run, ánh xạ sang ID/catalog mới và đối chiếu các trường sau chuyển đổi.
