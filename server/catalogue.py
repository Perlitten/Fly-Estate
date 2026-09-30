"""Conservative listing identity, source history and gallery provenance."""
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import hashlib
import re
from pathlib import Path
from functools import lru_cache

ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=10000)
def photo_hash(path,modified,size):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024**2),b''): h.update(block)
    return h.hexdigest()


def identity(url):
    p = urlsplit(url or "")
    path = p.path.rstrip("/")
    if p.hostname and p.hostname.endswith("bazaraki.com"):
        match = re.match(r"/adv/(\d+)_", path)
        if match:
            path = "/adv/" + match.group(1)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query)
                             if not k.startswith("utm_") and k not in ("fbclid", "gclid")))
    return urlunsplit(("https", (p.hostname or "").removeprefix("www."), path, query, "")) if url else None


def photo_keys(listing):
    keys=set()
    for photo in listing.get("photos") or []:
        path=ROOT/photo.lstrip('/')
        if path.exists():
            stat=path.stat(); keys.add(photo_hash(str(path),stat.st_mtime_ns,stat.st_size))
        else: keys.add(photo)
    return keys


def same_apartment(a, b):
    urls = {identity(a.get("url"))} | {identity(s.get("url")) for s in a.get("sources", [])}
    if identity(b.get("url")) and identity(b.get("url")) in urls:
        return True
    # One common stock photograph is insufficient for consolidating an advert.
    x, y = photo_keys(a), photo_keys(b)
    return len(x) >= 2 and x == y and all(a.get(k) == b.get(k) for k in ("city", "area", "bedrooms", "size"))


def enrich(listing, previous=None):
    stamp = listing["updated_at"]
    prior = previous or {}
    incoming_id = listing["id"]
    listing["id"] = prior.get("id", listing["id"])
    listing["captured_at"] = prior.get("captured_at", listing["captured_at"])
    listing["last_checked_at"] = stamp
    listing["gallery_version"] = hashlib.sha256("|".join(sorted(photo_keys(listing))).encode()).hexdigest()
    listing["gallery_changed"] = bool(previous and photo_keys(prior) != photo_keys(listing))
    listing["aliases"] = sorted((set(prior.get("aliases", [])) | {incoming_id}) - {listing["id"]})
    source = {k: listing.get(k) for k in ("url", "source", "price", "available", "published_at", "updated_at", "gallery_version")}
    history = [s for s in prior.get("sources", []) if identity(s.get("url")) != identity(source["url"])]
    if previous and prior.get("url") and not prior.get("sources") and identity(prior["url"]) != identity(source["url"]):
        history.append({k: prior.get(k) for k in source})
    listing["sources"] = history + [source]
    changes = list(prior.get("source_history", []))
    if previous:
        changed = {k: {"before": prior.get(k), "after": listing.get(k)}
                   for k in ("price", "available", "gallery_version") if prior.get(k) != listing.get(k)}
        if changed:
            changes.append({"checked_at": stamp, "url": listing.get("url"), "changes": changed})
    listing["source_history"] = changes
    return listing


def freshness(listing):
    stamp = listing.get("last_checked_at") or listing.get("updated_at") or listing.get("captured_at")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp).astimezone(timezone.utc)).total_seconds() / 86400
    except (ValueError, TypeError):
        age = None
    return {"checked_at": stamp, "age_days": round(age, 1) if age is not None else None,
            "stale": age is None or age > 7, "available": listing.get("available"),
            "gallery_version": listing.get("gallery_version"), "sources": len(listing.get("sources", [])) or 1}
