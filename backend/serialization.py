"""Preserve the existing frontend's JSON types and date formats."""
from datetime import date, datetime, time, timezone
from decimal import Decimal
from prices import VN

def serialize(value, key=None):
    if isinstance(value, dict):
        return {k: serialize(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    if isinstance(value, Decimal):
        if key == 'tank_capacity_liters':
            return format(value.normalize(), 'f')
        return format(value, '.6f')
    if isinstance(value, datetime):
        if key in ('created_at', 'updated_at'):
            return value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        return value.astimezone(VN).isoformat(timespec='minutes' if key == 'effective_at' else 'microseconds')
    if isinstance(value, time):
        return value.strftime('%H:%M')
    if isinstance(value, date):
        return value.isoformat()
    return value
