"""Read the public data used by Petrolimex's sidebar; no account/API key."""
import base64
import json
import re
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VN = timezone(timedelta(hours=7))
SOURCE = 'https://www.petrolimex.com.vn/'
FUEL_TYPES = ['E10 RON 95-III', 'E10 RON 95-V', 'E5 RON 92-II', 'RON 95-III']

def download(url):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 FuelLog/0.2', 'Accept': 'application/json,text/html', 'Referer': SOURCE})
    timeout = max(1, min(20, int(os.environ.get('PRICE_FETCH_TIMEOUT_SECONDS', '15'))))
    with urlopen(request, timeout=timeout) as response:
        return response.read(2_000_000).decode('utf-8')

def sidebar_url():
    filters = {'SystemID': '6783dc1271ff449e95b74a9520964169', 'RepositoryID': 'a95451e23b474fe5886bfb7cf843f53c', 'RepositoryEntityID': '3801378fe1e045b1afa10de7c5776124', 'Status': 'Published'}
    query = {'FilterBy': {'And': [{key: {'Equals': value}} for key, value in filters.items()]}, 'SortBy': {'LastModified': 'Descending'}, 'Pagination': {'TotalRecords': -1, 'TotalPages': 0, 'PageSize': 0, 'PageNumber': 0}}
    encoded = base64.urlsafe_b64encode(json.dumps(query, separators=(',', ':')).encode()).decode().rstrip('=')
    return SOURCE + '~apis/portals/cms.item/search?' + urlencode({'x-request': encoded})

def parse_sidebar(payload, announcements):
    # Use the announcement's effective time, never the crawler's download time.
    pattern = r'petrolimex-dieu-chinh-gia-xang-dau-tu-(\d{1,2})-gio-(\d{1,2})-phut-ngay-(\d{1,2})-(\d{1,2})-(\d{4})'
    times = []
    for h, m, d, mo, y in re.findall(pattern, announcements):
        times.append(datetime(int(y), int(mo), int(d), tzinfo=VN) + timedelta(hours=int(h), minutes=int(m)))
    if not times:
        raise ValueError('Không đọc được thời điểm áp dụng từ thông báo Petrolimex.')
    effective = max(times)
    result = []
    for item in payload.get('Objects', []):
        title = re.sub(r'\s+', ' ', item.get('Title', '')).strip()
        fuel = re.sub(r'^Xăng\s+', '', title, flags=re.I)
        if fuel not in FUEL_TYPES:
            continue
        modified = datetime.fromisoformat(item['LastModified'].replace('Z', '+00:00'))
        if modified.tzinfo:
            modified = modified.astimezone(VN)
        if modified.date() != effective.date():
            raise ValueError('Ngày bảng giá và ngày thông báo chưa khớp. Vui lòng cập nhật lại sau.')
        for zone in (1, 2):
            raw = item[f'Zone{zone}Price']
            value = int(raw)
            if value != float(raw) or not 1000 <= value <= 100000:
                raise ValueError('Bảng giá trả về giá trị không hợp lệ.')
            result.append(dict(fuel_type=fuel, price_zone=zone, effective_at=effective.isoformat(timespec='minutes'), unit_price_vnd=value, source='petrolimex', source_url=SOURCE, source_updated_at=item['LastModified']))
    if not any(r['fuel_type'] == 'E10 RON 95-III' for r in result):
        raise ValueError('Không tìm thấy E10 RON 95-III trong bảng giá thanh bên.')
    return result

def fetch_prices():
    payload = json.loads(download(sidebar_url()))
    announcements = download(SOURCE + 'ndi/thong-cao-bao-chi.html')
    return parse_sidebar(payload, announcements)

if __name__ == '__main__':
    print(json.dumps(fetch_prices(), ensure_ascii=True, indent=2))
