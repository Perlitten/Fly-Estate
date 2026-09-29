"""Bazaraki connector (D1): the rental market around the brief, read like a visitor.

Reads only what robots.txt allows: public search pages
(`/real-estate-to-rent/apartments-flats/<district>/`), the public map page
(`/map/...`) and advert pages (`/adv/<id>_<slug>/`). It never calls `/api`
and never uses `attrs_*` filters (both disallowed); the brief's hard limit
goes in `price_max`, bedrooms are checked here. Requests are sequential with
a pause, identify the tool in the User-Agent, and a market snapshot is cached.

The pages are Next.js; their data is in the React flight payload
(`self.__next_f.push`), which this module decodes instead of scraping markup.

* `market(settings)` — offers from the search pages: price, bedrooms, area,
  size, first photo. Exact coordinates come from the map page, which lists
  about 100 adverts; the rest are placed at their area centre (`coord_kind`
  "area") or left off the map.
* `advert(url)` — one advert as an importer item (`importers.normalize`):
  stated features, all photos and source coordinates.
"""
from __future__ import annotations

import json
import re
import threading
import time
from urllib.parse import urlparse

from . import importers
from .storage import ROOT

BASE = "https://www.bazaraki.com"
DISTRICT = "lemesos-district-limassol"
CATEGORY = "/real-estate-to-rent/apartments-flats"
PAUSE = 0.8
PAGES = 5
TTL = 15 * 60
PAGE_LIMIT = 4 * 1024 * 1024
ADVERT = re.compile(r"^/adv/(\d+)_[\w-]+/?$")

_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()
_last = [0.0]


def _get(url: str) -> str:
    """One polite GET: at most one request per PAUSE across the process."""
    with _lock:
        wait = _last[0] + PAUSE - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return importers.fetch(url, importers.ALLOWED_SOURCES, PAGE_LIMIT).decode("utf8", errors="replace")
        finally:
            _last[0] = time.monotonic()


def flight(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    if not chunks:
        raise ValueError("Bazaraki page layout changed: no page data found.")
    return "".join(json.loads('"' + c + '"') for c in chunks)


def _value(text: str, key: str, start: int = 0):
    """JSON value following `"key":` in the flight text, or None."""
    i = text.find(f'"{key}":', start)
    if i < 0:
        return None
    return json.JSONDecoder().raw_decode(text, i + len(key) + 3)[0]


def search_url(ceiling: float, page: int = 1, on_map: bool = False) -> str:
    url = f"{BASE}{'/map' if on_map else ''}{CATEGORY}/{DISTRICT}/?price_max={int(ceiling)}"
    return url + (f"&page={page}" if page > 1 else "")


def bedrooms_of(text: str) -> int | None:
    text = str(text).lower()
    if "studio" in text:
        return 0
    found = re.search(r"(\d+)\s*(?:-|\s)?(?:and more|bedroom|bed)", text) or re.fullmatch(r"\s*(\d+)\s*", text)
    return int(found.group(1)) if found else None


def area_of(location: str) -> tuple[str, str]:
    """'Limassol — Limassol - Agia Zoni' → ('Limassol', 'Agia Zoni')."""
    city, _, rest = str(location).partition(" — ")
    return city.strip() or "Limassol", (rest.split(" - ")[-1] if rest else "").strip()


def _areas() -> dict:
    path = ROOT / "data/areas.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _price(value) -> float | None:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return float(digits) if digits else None


def _offer(raw: dict, known: dict) -> dict | None:
    url = str(raw.get("url") or "")
    if not ADVERT.match(url):
        return None
    texts = [f.get("text", "") for f in raw.get("features") or []]
    size = next((float(m.group(1)) for t in texts if (m := re.search(r"([\d.]+)\s*m²", t))), None)
    city, area = area_of(raw.get("location", ""))
    centre = (known.get(area) or {}).get("coords")
    return {"id": str(raw["id"]), "url": BASE + url, "title": str(raw.get("title") or "").strip(),
            "price": _price(raw.get("price_without_currency") or raw.get("price")),
            "bedrooms": bedrooms_of(raw.get("title", "")) if bedrooms_of(raw.get("title", "")) is not None
            else (bedrooms_of(texts[0]) if texts else None),
            "size": size, "city": city, "area": area, "published": raw.get("published"),
            "photos": raw.get("img_count"), "thumb": raw.get("first_thumb"),
            "coords": centre, "coord_kind": "area" if centre else "unknown"}


def market(ceiling: float, min_bedrooms: int, pages: int = PAGES) -> dict:
    """Offers under the hard limit with at least `min_bedrooms`, newest search order."""
    key = (int(ceiling), int(min_bedrooms), pages)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < TTL:
        return cached[1]
    known, offers, total_pages, count = _areas(), {}, None, None
    for page in range(1, pages + 1):
        text = flight(_get(search_url(ceiling, page)))
        total_pages = total_pages or _value(text, "total_pages")
        count = count if count is not None else _value(text, "count")
        for raw in _value(text, "adverts") or []:
            offer = _offer(raw, known)
            if offer:
                offers.setdefault(offer["id"], offer)
        if total_pages and page >= total_pages:
            break
    exact = 0
    try:
        for raw in _value(flight(_get(search_url(ceiling, on_map=True))), "adverts") or []:
            point, offer = raw.get("coordinates") or {}, offers.get(str(raw.get("id")))
            if offer and point.get("lat") is not None:
                offer.update(coords=[float(point["lat"]), float(point["lng"])],
                             coord_kind="area" if raw.get("coordinates_set_auto") else "source")
                exact += 1
    except (ValueError, KeyError, TypeError):
        pass  # the map page is optional: offers keep their area centre
    scanned = len(offers)
    matching = [o for o in offers.values() if o["price"] and o["price"] <= ceiling
                and (o["bedrooms"] is None or o["bedrooms"] >= min_bedrooms)]
    result = {"source": "bazaraki.com", "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "search": search_url(ceiling), "pages": min(pages, total_pages or pages),
              "total_pages": total_pages, "listed": count, "scanned": scanned, "exact_coords": exact,
              "offers": matching}
    _cache[key] = (time.time(), result)
    return result


def advert(url: str) -> dict:
    """Importer item for one advert page, from its schema.org block and page data."""
    parsed = urlparse(url)
    if parsed.hostname not in ("www.bazaraki.com", "bazaraki.com") or not ADVERT.match(parsed.path):
        raise ValueError("A Bazaraki advert URL (/adv/<id>_...) is required.")
    html = _get(f"{BASE}{parsed.path}")
    schema = next((i for i in importers.parse_schema_blocks(html)), {})
    text = flight(html)
    at = text.find('"location":{"name"')
    if at < 0:
        raise ValueError("Bazaraki advert page without location data; it may have been removed.")
    location = _value(text, "location", at) or {}
    features = {f["name"]: str(f.get("value") or "") for f in _value(text, "features", at) or []
                if isinstance(f, dict) and "name" in f}
    point = location.get("coordinates") or {}
    city, area = area_of(location.get("name", ""))
    description = str(schema.get("description") or "")
    included = features.get("Included", "").lower()
    size = re.search(r"([\d.]+)", features.get("Property area", ""))
    parking = features.get("Parking", "").lower()
    furnishing = features.get("Furnishing", "").lower()
    balcony_size = [float(v) for v in re.findall(
        r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm)\s*(?:(?:of\s+)?(?:covered|uncovered)\s+)?(?:veranda|balcony|terrace)", description, re.I)]
    item = {"url": f"{BASE}{parsed.path}", "title": str(schema.get("name") or "").strip() or "Apartment",
            "price": _price((schema.get("offers") or {}).get("price")),
            "bedrooms": bedrooms_of(features.get("Bedrooms", "")),
            "size": float(size.group(1)) if size else None, "area": area, "city": city,
            "parking": {"covered": "covered", "uncovered": "uncovered", "no": "none"}.get(parking, "unknown"),
            "balcony": any(w in included for w in ("balcony", "veranda", "terrace")) or bool(
                re.search(r"\b(?:balcony|balconies|veranda|terrace)\b", description, re.I)),
            "balcony_size": max([v for v in balcony_size if 0 < v < 500], default=None),
            "balcony_covered": True if re.search(r"\bcovered\s+(?:veranda|balcony|terrace)", description, re.I) else None,
            "furnished": furnishing.startswith(("fully", "semi", "partially")),
            "description": description, "photo_urls": [i for i in schema.get("image") or [] if isinstance(i, str)],
            "available": "InStock" in str((schema.get("offers") or {}).get("availability", "InStock"))}
    if point.get("lat") is not None:
        item["coords"] = [float(point["lat"]), float(point["lng"])]
        item["coord_kind"] = "area" if point.get("is_approximate") else "source"
    return item
