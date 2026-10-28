"""Pure parsing and normalisation helpers shared by validation and cleaning."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from html.parser import HTMLParser

UNKNOWN_COUNTRY = "Unknown"
UNSPECIFIED_CITY = "Not specified"

# Hours per year assume a 40-hour week; days assume 5 working days a week.
PERIOD_TO_ANNUAL_FACTOR = {"hour": 2080, "day": 260, "week": 52, "month": 12, "year": 1}
WORK_MODES = ("remote", "hybrid", "onsite", "unknown")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "unknown")

_WORK_MODE_ALIASES = {
    "remote": "remote", "fully remote": "remote", "work from home": "remote", "wfh": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite", "on-site": "onsite", "on site": "onsite", "in office": "onsite",
    "in-office": "onsite", "office": "onsite",
}
_EMPLOYMENT_ALIASES = {
    "full_time": "full_time", "full-time": "full_time", "full time": "full_time",
    "fulltime": "full_time", "permanent": "full_time",
    "part_time": "part_time", "part-time": "part_time", "part time": "part_time",
    "contract": "contract", "contractor": "contract", "freelance": "contract",
    "internship": "internship", "intern": "internship",
}
_COUNTRY_ALIASES = {
    "United States": ("us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"),
    "United Kingdom": ("uk", "u.k.", "gb", "great britain", "united kingdom", "england"),
    "Germany": ("de", "germany", "deutschland"),
    "Canada": ("ca", "canada"),
    "Netherlands": ("nl", "netherlands", "the netherlands"),
    "France": ("fr", "france"),
    "Spain": ("es", "spain"),
    "Ireland": ("ie", "ireland"),
    "India": ("in", "india"),
    "Australia": ("au", "australia"),
    "Poland": ("pl", "poland"),
    "Portugal": ("pt", "portugal"),
}
_COUNTRY_LOOKUP = {alias: country for country, aliases in _COUNTRY_ALIASES.items() for alias in aliases}
# Words that describe a region or "anywhere" rather than a city.
_REGION_WORDS = {"worldwide", "anywhere", "global", "europe", "emea", "apac", "latam",
                 "north america", "americas", "asia"}


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def normalize_key(value: str | None) -> str:
    """Lower-cased, punctuation-free form used only to detect duplicates."""
    text = re.sub(r"[^\w\s+#]", " ", normalize_text(value).lower())
    return re.sub(r"\s+", " ", text).strip()


def parse_iso_date(value: str) -> date:
    """Accept YYYY-MM-DD, optionally followed by a time part (as APIs send)."""
    text = normalize_text(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ].*)?", text):
        raise ValueError(f"expected YYYY-MM-DD, got {value!r}")
    return date.fromisoformat(text[:10])


def parse_amount(value: str) -> float:
    text = value.replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(\.\d+)?", text):
        raise ValueError(f"not a non-negative number: {value!r}")
    return float(text)


def annualize(amount: float, period: str) -> float:
    return round(amount * PERIOD_TO_ANNUAL_FACTOR[period], 2)


def parse_salary_text(text: str) -> tuple[float, float] | None:
    """Read free-text salaries such as "$40,000 - $50,000" or "$70k-$90k".

    Returns (min, max) in the stated units, or None when the text is not a plain
    yearly USD figure. Hourly/monthly wording and other currencies are skipped
    on purpose: guessing would silently corrupt salary statistics.
    """
    if not text or re.search(r"hour|\bhr\b|week|month|day|[\u20ac\u00a3]|\b(eur|gbp|cad|aud)\b", text, re.I):
        return None
    numbers = re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*([kK])?", text)
    if not 1 <= len(numbers) <= 2:
        return None
    values = [float(number.replace(",", "")) * (1000 if suffix else 1) for number, suffix in numbers]
    return min(values), max(values)


def normalize_work_mode(value: str | None, location: str = "") -> str:
    mode = _WORK_MODE_ALIASES.get(normalize_text(value).lower())
    if mode:
        return mode
    return "remote" if re.search(r"\bremote\b", location, re.I) else "unknown"


def normalize_employment_type(value: str | None) -> str:
    return _EMPLOYMENT_ALIASES.get(normalize_text(value).lower(), "unknown")


def normalize_country(value: str) -> str:
    cleaned = normalize_text(value)
    return _COUNTRY_LOOKUP.get(cleaned.lower(), cleaned)


def _tidy_city(value: str) -> str:
    return value.title() if value.islower() or value.isupper() else value


def parse_location(raw: str | None) -> tuple[str, str]:
    """Split "City, Region, Country" style text into (city, country).

    Rules: the last part is the country, the first part is the city, "Remote"
    markers are ignored, and unrecognised single words become the city.
    """
    parts = [part for part in (normalize_text(p) for p in (raw or "").split(",")) if part]
    parts = [part for part in parts if part.lower() != "remote"]
    parts = [part for part in parts if part.lower() not in _REGION_WORDS]
    if not parts:
        return UNSPECIFIED_CITY, UNKNOWN_COUNTRY
    if len(parts) == 1:
        country = _COUNTRY_LOOKUP.get(parts[0].lower())
        if country:
            return UNSPECIFIED_CITY, country
        return _tidy_city(parts[0]), UNKNOWN_COUNTRY
    return _tidy_city(parts[0]), normalize_country(parts[-1])


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS = {"p", "br", "li", "div", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    _SKIPPED_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def strip_html(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    parser.close()
    return normalize_text("".join(parser.parts))
