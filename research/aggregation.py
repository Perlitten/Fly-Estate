"""Proxy selection of the photo aggregator before any human ratings exist (R3).

Question: does keeping the single strongest outdoor photo help, compared with
averaging all photos? Without ratings the only labelled target is the
listing's own `balcony` field. The listing channels of the spiking stimulus
carry that field directly, so spiking responses would leak the label; this
proxy therefore uses photo-only evidence — the eleven CLIP attribute signals
per photo — through the same two aggregators and the same grouped
validation as `server.readout`. `balcony = false` means "not stated by the
source", not "confirmed absent", so the label is noisy on the negative side.

    .venv/Scripts/python -m research.aggregation   (Windows)
    .venv/bin/python -m research.aggregation       (macOS/Linux)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

from server import readout
from server.gallery import PhotoHashes
from server.vision import SEMANTIC_KEYS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/results/aggregation_proxy.json"


def main() -> int:
    db = sqlite3.connect(f"file:{(ROOT / 'data/state.sqlite').as_posix()}?mode=ro", uri=True)
    listings = [json.loads(r[0]) for r in db.execute("SELECT data FROM listings ORDER BY id")]
    listings = [l for l in listings if (l.get("vision") or {}).get("per_photo")]
    hashes = PhotoHashes()
    group_of = readout.groups(listings, lambda p: hashes(p) if hashes.path(p).exists() else p)
    labels = {l["id"]: int(bool(l.get("balcony"))) for l in listings}

    features = {name: {} for name in readout.AGGREGATORS}
    single = {"mean": {}, "max": {}}
    visible = {1: [], 0: []}
    for l in listings:
        per_photo = l["vision"]["per_photo"]
        vectors = [[p["attributes"].get(k, 0.5) for k in SEMANTIC_KEYS] for p in per_photo]
        evidence = readout.outdoor_evidence(l)
        for name in readout.AGGREGATORS:
            features[name][l["id"]] = readout.aggregate(name, vectors, evidence)
        e = np.asarray([x for x in evidence if x is not None])
        single["mean"][l["id"]], single["max"][l["id"]] = float(e.mean()), float(e.max())
        visible[labels[l["id"]]].append(int((e > 0.5).sum()))

    comparison = readout.compare(features, labels, group_of)
    ids = sorted(labels)
    y = [labels[i] for i in ids]
    report = {
        "question": "Mean of all photos versus mean plus the strongest outdoor photo (R3).",
        "label": "listing field `balcony` (true = stated by source; false = not stated)",
        "features": f"photo-only CLIP attributes {list(SEMANTIC_KEYS)}; spiking responses excluded (label leak)",
        "outdoor_evidence": f"CLIP attribute `{readout.OUTDOOR_ATTRIBUTE}`",
        "listings": len(ids), "groups": len(set(group_of.values())), "positives": sum(y),
        "unaggregated_auc": {name: round(readout.auc([v[i] for i in ids], y), 4) for name, v in single.items()},
        "photos_with_outdoor_evidence_above_0_5": {
            "balcony_stated": {"median": float(np.median(visible[1])), "zero": visible[1].count(0),
                               "listings": len(visible[1])},
            "balcony_not_stated": {"median": float(np.median(visible[0])), "zero": visible[0].count(0),
                                   "listings": len(visible[0])}},
        **comparison,
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
