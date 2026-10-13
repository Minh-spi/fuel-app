"""Small Supabase Auth REST client. Never logs tokens, passwords, or responses."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class AuthConfigurationError(RuntimeError):
    pass


class AuthError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def public_config():
    url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = (os.environ.get('SUPABASE_ANON_KEY') or os.environ.get('SUPABASE_PUBLISHABLE_KEY') or '').strip()
    if not url.startswith('https://') or not key:
        raise AuthConfigurationError('Thiếu SUPABASE_URL hoặc SUPABASE_ANON_KEY trong Environment Variables.')
    return url, key


def call(path, *, method='GET', payload=None, token=None):
    url, key = public_config()
    body = None if payload is None else json.dumps(payload, separators=(',', ':')).encode()
    headers = {'apikey': key, 'Accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = Request(url + '/auth/v1/' + path.lstrip('/'), data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=8) as response:
            content = response.read(128_001)
            if len(content) > 128_000:
                raise AuthError('Phản hồi đăng nhập quá lớn.', 502)
            return json.loads(content) if content else {}
    except HTTPError as error:
        try:
            details = json.loads(error.read(16_384))
        except Exception:
            details = {}
        code = error.code
        if code in (401, 403):
            message = 'Email hoặc mật khẩu chưa đúng, hoặc phiên đăng nhập đã hết hạn.'
        elif code == 429:
            message = 'Thử đăng nhập quá nhiều lần. Hãy chờ rồi thử lại.'
        elif 'already registered' in str(details).lower():
            message = 'Email này đã có tài khoản. Hãy đăng nhập.'
        elif 'password' in str(details).lower():
            message = 'Mật khẩu cần có ít nhất 8 ký tự.'
        else:
            message = 'Supabase Auth chưa xử lý được yêu cầu. Kiểm tra cấu hình Auth và thử lại.'
        raise AuthError(message, 401 if code in (400, 401, 403) else code) from None
    except (URLError, TimeoutError, OSError):
        raise AuthError('Không kết nối được Supabase Auth. Hãy thử lại sau.', 503) from None
    except (ValueError, json.JSONDecodeError):
        raise AuthError('Phản hồi Supabase Auth không hợp lệ.', 502) from None


def current_user(token):
    if not token:
        return None
    try:
        result = call('user', token=token)
    except AuthError as error:
        if error.status == 401:
            return None
        raise
    user_id = result.get('id')
    if not user_id:
        return None
    return {'id': user_id, 'email': result.get('email', ''),
        'email_verified': bool(result.get('email_confirmed_at') or result.get('confirmed_at'))}
