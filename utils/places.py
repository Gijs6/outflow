import re
import string

BASE62 = string.digits + string.ascii_lowercase + string.ascii_uppercase


def to_base62(num):
    if num == 0:
        return "0"
    digits = []
    while num:
        num, rem = divmod(num, 62)
        digits.append(BASE62[rem])
    return "".join(reversed(digits))


def from_base62(s):
    num = 0
    for char in s:
        num = num * 62 + BASE62.index(char)
    return num


PLACE_ID_LENGTH = 9


def encode_place_id(lat, lon, precision=5):
    lat_int = int((lat + 90) * 10**precision)
    lon_int = int((lon + 180) * 10**precision)
    combined = (lat_int << 26) + lon_int
    return to_base62(combined).zfill(PLACE_ID_LENGTH)


def decode_place_id(encoded, precision=5):
    combined = from_base62(encoded)
    lon_mask = (1 << 26) - 1
    lon_int = combined & lon_mask
    lat_int = combined >> 26
    lat = lat_int / 10**precision - 90
    lon = lon_int / 10**precision - 180
    return round(lat, precision), round(lon, precision)


COORD_REGEX = re.compile(r"^(-?\d{1,3}(?:\.\d+)?)[,\s]+(-?\d{1,3}(?:\.\d+)?)$")


def parse_as_location(query):
    stripped = query.strip()
    coord_match = COORD_REGEX.match(stripped)
    if coord_match:
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    if len(stripped) == PLACE_ID_LENGTH and re.match(r"^[0-9a-zA-Z]+$", stripped):
        try:
            lat, lon = decode_place_id(stripped)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except Exception:
            pass
    return None
