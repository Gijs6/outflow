import json
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote
import math


def to_datetime(value, tz=None):
    zone = ZoneInfo(tz) if tz else None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=zone)
    return value


def ucfirst_filter(value):
    if not value:
        return value
    try:
        return value[0].upper() + value[1:]
    except TypeError:
        return value


def strftime_filter(value, fmt="%d-%m-%Y", tz=None):
    return ucfirst_filter(to_datetime(value, tz).strftime(fmt))


def to_iso_filter(value, tz=None):
    return to_datetime(value, tz).isoformat()


def urlescape_filter(value):
    return quote(str(value), safe="")


def jsondump_filter(value, indent=4):
    return json.dumps(value, ensure_ascii=False, indent=indent)


def to_bft_filter(speed_ms):
    bft = int(math.floor((speed_ms / 0.836) ** (2 / 3)))
    return min(bft, 12)


def to_kmh_filter(speed_ms):
    return round(speed_ms * 3.6, 1)


FILTERS = {
    "ucfirst": ucfirst_filter,
    "strftime": strftime_filter,
    "to_iso": to_iso_filter,
    "urlescape": urlescape_filter,
    "jsondump": jsondump_filter,
    "to_bft": to_bft_filter,
    "to_kmh": to_kmh_filter,
}


def register_filters(app):
    for name, fn in FILTERS.items():
        app.template_filter(name)(fn)
