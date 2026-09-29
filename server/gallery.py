"""Spiking-model readiness of every photo of a listing (R3).

The HTTP server never runs the engine. It rebuilds the stimulus each photo
would get under the current brief and codec, derives the cache key the worker
would use with the current weights, and looks the result up. A photo is
`ready` only when that exact result exists; an older result for the same
codec (other weights or another brief) is `stale`.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

from . import readout
from .engine import stimuli
from .jobs import ACTIVE, ROOT, Queue
from .vision import MODEL_ID, REVISION


class PhotoHashes:
    """SHA-256 of photo files, memoised by path, size and modification time."""

    def __init__(self, root: Path = ROOT):
        self.root, self.cache, self.lock = root, {}, threading.Lock()

    def path(self, photo: str) -> Path:
        return self.root / photo.lstrip("/")

    def __call__(self, photo: str) -> str:
        path = self.path(photo)
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        sha = stimuli.file_sha256(path)
        with self.lock:
            self.cache[key] = sha
        return sha


def job_params(settings: dict) -> dict:
    """The part of the brief a stimulus depends on, plus the codec mode."""
    return {"mode": settings["mode"],
            "brief": {"ceiling": settings["ceiling"], "ideal": list(settings["ideal"]), "radius": settings["radius"]}}


def _summary(result: dict) -> dict:
    return {"kc_active": result["kc_active"], "kc_active_fraction": result["kc_active_fraction"],
            "mbon_spikes": sum(result["mbon_spikes"]), "pam_hz": result["pam_hz"],
            "total_spikes": result["total_spikes"], "wall_seconds": result["wall_seconds"]}


def gallery(queue: Queue, listing: dict, settings: dict, hashes: PhotoHashes) -> dict:
    params = job_params(settings)
    mode, brief = params["mode"], params["brief"]
    version, fingerprint = queue.state("engine_version"), queue.state("current_fingerprint")
    channels = json.loads(queue.state("channels") or "null")
    per_photo = (listing.get("vision") or {}).get("per_photo") or []
    frozen = queue.get_center(MODEL_ID, REVISION) if mode == "cyborg" else None
    center = stimuli.Center.of(*frozen) if frozen else None

    latest = next((j for j in queue.list(listing["id"], 20) if j["params"] == params), None)
    items = {}
    if latest:
        latest = queue.get(latest["id"])
        items = {i["position"]: i for i in latest.pop("items")}
    running_position = None
    if latest and latest["status"] == "running":
        pending = [p for p, i in items.items() if i["status"] == "pending"]
        running_position = min(pending) if pending else None
    previous = {a["position"]: a for a in queue.listing_activity(listing["id"], stimuli.CODECS[mode])}

    photos, results = [], {}
    for position, photo in enumerate(listing.get("photos") or []):
        entry = {"position": position, "photo": photo, "status": "missing", "signals": None, "result": None}
        photos.append(entry)
        try:
            if position >= len(per_photo):
                raise LookupError("No encoder signals for this photo; import the listing again.")
            sha = hashes(photo)
            embedding = queue.get_embedding(sha, MODEL_ID, REVISION) if mode == "cyborg" else None
            if mode == "cyborg" and (embedding is None or center is None):
                entry.update(status="missing", error="The CLIP embedding or centre is computed when you run the model.")
                continue
            stimulus, provenance = stimuli.encode(mode, per_photo[position], listing, brief,
                                                  channels or [f"channel-{k}" for k in range(stimuli.CHANNELS)],
                                                  embedding, center)
            entry["signals"] = provenance["photo_signals"]
        except (LookupError, OSError, ValueError) as error:
            entry.update(status="unavailable", error=str(error))
            continue
        if version and fingerprint and channels:
            found = queue.get_activity(stimuli.cache_key(sha, stimulus, mode, version, fingerprint, center))
            if found:
                entry.update(status="ready", result=_summary(found["result"]), checkpoint=found["checkpoint"],
                             replay_key=found["cache_key"] if found["result"].get("replay") else None)
                item = items.get(position)
                if not entry["replay_key"] and latest and latest["status"] in ACTIVE and item and item["status"] == "pending":
                    entry["status"] = "running" if position == running_position else "queued"
                results[position] = found["result"]
                continue
        item = items.get(position)
        if latest and latest["status"] in ACTIVE and item and item["status"] == "pending":
            entry["status"] = "running" if position == running_position else "queued"
        elif position in previous:
            old = previous[position]
            entry.update(status="stale", result=_summary(old["result"]),
                         replay_key=old["cache_key"] if old["result"].get("replay") else None)
        elif item and item["status"] == "error":
            entry.update(status="error", error=item["error"])

    counts = {}
    for entry in photos:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    summary = readout.listing_readout(listing, results, len(photos))
    summary.pop("vector")
    live = json.loads(queue.state("live_replay") or "null")
    if (not latest or latest["status"] != "running" or not live
            or live["job_id"] != latest["id"] or live["params"] != params):
        live = None
    elif live:
        live = {"job_id": live["job_id"], "position": live["position"],
                "bins": live["trace"]["bins"], "bin_ms": live["trace"]["bin_ms"]}
    return {"listing_id": listing["id"], "mode": mode, "codec": stimuli.CODECS[mode], "params": params,
            "context": stimuli.context_signals(listing, brief), "photos": photos, "counts": counts,
            "total": len(photos), "job": latest, "readout": summary, "live": live,
            "engine": {"version": version, "fingerprint": fingerprint, "worker": queue.worker_status()}}


def current_results(queue: Queue, listings: list[dict], settings: dict, hashes: PhotoHashes) -> dict[str, dict]:
    """Current-weight results of every photo of many listings, in two queries.

    Returns {listing_id: {position: result}}; a photo is present only when the
    exact result for today's brief, codec and weights exists (`ready`).
    """
    params = job_params(settings)
    mode, brief = params["mode"], params["brief"]
    version, fingerprint = queue.state("engine_version"), queue.state("current_fingerprint")
    channels = json.loads(queue.state("channels") or "null")
    if not (version and fingerprint and channels):
        return {l["id"]: {} for l in listings}
    frozen = queue.get_center(MODEL_ID, REVISION) if mode == "cyborg" else None
    center = stimuli.Center.of(*frozen) if frozen else None
    embeddings = queue.get_embeddings(MODEL_ID, REVISION) if mode == "cyborg" else {}
    keys = {}
    for listing in listings:
        per_photo = (listing.get("vision") or {}).get("per_photo") or []
        for position, photo in enumerate(listing.get("photos") or []):
            try:
                if position >= len(per_photo):
                    continue
                sha = hashes(photo)
                embedding = embeddings.get(sha)
                if mode == "cyborg" and (embedding is None or center is None):
                    continue
                stimulus, _ = stimuli.encode(mode, per_photo[position], listing, brief, channels, embedding, center)
            except (LookupError, OSError, ValueError):
                continue
            keys[stimuli.cache_key(sha, stimulus, mode, version, fingerprint, center)] = (listing["id"], position)
    found = queue.get_activities(keys)
    out = {l["id"]: {} for l in listings}
    for key, result in found.items():
        listing_id, position = keys[key]
        out[listing_id][position] = result
    return out


def portfolio(queue: Queue, listings: list[dict], settings: dict, ratings: dict, comparisons: list,
              hashes: PhotoHashes, fallback: dict | None = None) -> dict:
    """Spiking score of every fully simulated listing (R3).

    Only listings whose every photo has a current result are scored. The
    aggregator is selected on human ratings of such listings with grouped
    validation (`readout.compare`); until there are enough, `fallback` (the
    proxy study) decides. Ratings are read here only, never by a stimulus.
    """
    from .brain import Brain
    results = current_results(queue, listings, settings, hashes)
    complete = [l for l in listings if l.get("photos") and len(results[l["id"]]) == len(l["photos"])]
    labels = {l["id"]: int(ratings[l["id"]] > 0) for l in complete if ratings.get(l["id"]) in (-1, 1)}
    selection = {"source": "proxy", "selected": readout.DEFAULT, **(fallback or {})}
    if len(set(labels.values())) == 2:
        group_of = readout.groups(complete, lambda p: hashes(p) if hashes.path(p).exists() else p)
        features = {name: {l["id"]: readout.listing_readout(l, results[l["id"]], len(l["photos"]), name)["vector"]
                           for l in complete if l["id"] in labels} for name in readout.AGGREGATORS}
        validated = readout.compare(features, labels, group_of)
        if validated.get("results"):
            selection = {"source": "ratings", **validated}
    aggregator = selection["selected"]
    info, scores = {"ready": False, "ratings": 0, "comparisons": 0}, {}
    if complete:
        x = np.array([readout.listing_readout(l, results[l["id"]], len(l["photos"]), aggregator)["vector"]
                      for l in complete])
        ids = {l["id"] for l in complete}
        probability, info = Brain.fit(x, complete, {k: v for k, v in ratings.items() if k in ids},
                                      [p for p in comparisons if p["a"] in ids and p["b"] in ids])
        if info.get("ready"):
            scores = {l["id"]: round(float(p), 5) for l, p in zip(complete, probability)}
    return {"aggregator": aggregator, "selection": selection, "eligible": len(listings), "complete": len(complete),
            "photos_ready": sum(len(r) for r in results.values()),
            "photos_total": sum(len(l.get("photos") or []) for l in listings),
            "readout": {"ready": bool(info.get("ready")), "ratings": info.get("ratings", 0),
                        "comparisons": info.get("comparisons", 0),
                        "task": "Logistic readout of aggregated MBON spikes, KC fraction and PAM rate"},
            "scores": scores, "complete_ids": [l["id"] for l in complete]}
