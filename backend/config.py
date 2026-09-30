import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

class ConfigurationError(RuntimeError):
    pass

if not os.environ.get('VERCEL'):
    load_dotenv(ROOT / '.env.local', override=False)

def integer_setting(name, default, minimum=1, maximum=60000):
    try:
        value = int(os.environ.get(name, default))
    except (ValueError, TypeError):
        raise ConfigurationError(f'Biến {name} phải là số nguyên.') from None
    if not minimum <= value <= maximum:
        raise ConfigurationError(f'Biến {name} phải nằm trong khoảng {minimum}–{maximum}.')
    return value
