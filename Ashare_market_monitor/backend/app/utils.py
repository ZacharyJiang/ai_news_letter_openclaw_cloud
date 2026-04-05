import re
from typing import Iterable


PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)")


def parse_percent(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"--", "nan", "None"}:
        return None

    m = PERCENT_RE.search(text)
    if m:
        return float(m.group(1))

    m = NUMBER_RE.search(text)
    if m:
        return float(m.group(1))

    return None


def parse_scale_to_billion(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text or text in {"--", "nan", "None"}:
        return None

    m = NUMBER_RE.search(text)
    if not m:
        return None

    num = float(m.group(1))
    if "万亿" in text:
        return num * 10000
    if "亿" in text:
        return num
    if "万" in text:
        return num / 10000
    return num / 100000000


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"--", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def min_non_none(values: Iterable[float | None]) -> float | None:
    items = [x for x in values if x is not None]
    if not items:
        return None
    return min(items)
