"""Listing-level readout of the spiking model: aggregation across photos (R3).

Every photo of a listing gets its own episode. A listing is scored from the
per-photo responses, so the photos must be combined. Two versioned
aggregators are compared:

* `mean-v1` — the mean of the photo vectors.
* `outdoor-v1` — the mean plus the vector of the single photo with the
  strongest outdoor evidence and that evidence itself, so one clear balcony
  photo is not diluted by twenty interior shots.

A photo vector is the MBON spike counts followed by the KC active fraction
and the PAM rate. Outdoor evidence is the CLIP `balcony` attribute of the
photo (a zero-shot contrast "balcony, loggia or terrace" versus "indoor
room"); it is a visual estimate, not a confirmed listing field.

Selection uses held-out apartment groups: listings that share any photo
file are one group and never straddle a split. `outdoor-v1` is selected only
when it beats `mean-v1` on validation AUC by more than the spread of the
difference across folds; otherwise the simpler mean is kept.
"""
from __future__ import annotations

import numpy as np
from scipy import optimize
from scipy.special import expit

AGGREGATORS = ("mean-v1", "outdoor-v1")
DEFAULT = "mean-v1"
OUTDOOR_ATTRIBUTE = "balcony"
FOLDS = 5
SPLIT_SEED = 783
L2 = 1.0


def photo_vector(result: dict) -> np.ndarray:
    return np.r_[np.asarray(result["mbon_spikes"], dtype=np.float64), result["kc_active_fraction"], result["pam_hz"]]


def outdoor_evidence(listing: dict) -> list[float | None]:
    per_photo = (listing.get("vision") or {}).get("per_photo") or []
    return [(p.get("attributes") or {}).get(OUTDOOR_ATTRIBUTE) for p in per_photo]


def aggregate(name: str, vectors, evidence) -> np.ndarray:
    """Listing vector from per-photo vectors (rows) and their outdoor evidence."""
    vectors = np.atleast_2d(np.asarray(vectors, dtype=np.float64))
    if not len(vectors):
        raise ValueError("no photo vectors to aggregate")
    mean = vectors.mean(axis=0)
    if name == "mean-v1":
        return mean
    if name == "outdoor-v1":
        e = np.asarray([-1.0 if x is None else float(x) for x in evidence])
        top = int(np.argmax(e))
        return np.r_[mean, vectors[top], max(e[top], 0.0)]
    raise ValueError(f"unknown aggregator {name!r}")


def strongest_outdoor(evidence, positions) -> dict | None:
    known = [(e, p) for e, p in zip(evidence, positions) if e is not None]
    if not known:
        return None
    e, p = max(known)
    return {"position": int(p), "evidence": round(float(e), 4)}


def listing_readout(listing: dict, results: dict[int, dict], total: int, aggregator: str = DEFAULT) -> dict:
    """Summary of a listing's current per-photo results; `vector` feeds the score readout."""
    positions = sorted(results)
    out = {"aggregator": aggregator, "photos": len(positions), "total": total,
           "complete": bool(total) and len(positions) == total, "mean": None, "strongest_outdoor": None,
           "vector": None}
    if not positions:
        return out
    rows = [results[p] for p in positions]
    evidence_all = outdoor_evidence(listing)
    evidence = [evidence_all[p] if p < len(evidence_all) else None for p in positions]
    out["mean"] = {"kc_active_fraction": round(float(np.mean([r["kc_active_fraction"] for r in rows])), 6),
                   "mbon_spikes": round(float(np.mean([sum(r["mbon_spikes"]) for r in rows])), 2),
                   "pam_hz": round(float(np.mean([r["pam_hz"] for r in rows])), 3)}
    out["strongest_outdoor"] = strongest_outdoor(evidence, positions)
    out["vector"] = aggregate(aggregator, [photo_vector(r) for r in rows], evidence)
    return out


def groups(listings: list[dict], photo_key) -> dict[str, int]:
    """Apartment groups: listings sharing any photo (by `photo_key`) are merged."""
    parent = list(range(len(listings)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for i, listing in enumerate(listings):
        for photo in listing.get("photos") or []:
            key = photo_key(photo)
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i
    roots = {}
    return {l["id"]: roots.setdefault(find(i), len(roots)) for i, l in enumerate(listings)}


def auc(scores, labels) -> float | None:
    s, y = np.asarray(scores, dtype=np.float64), np.asarray(labels, dtype=bool)
    pos, neg = s[y], s[~y]
    if not len(pos) or not len(neg):
        return None
    diff = pos[:, None] - neg[None, :]
    return float((diff > 0).mean() + 0.5 * (diff == 0).mean())


def fit(x, y, l2: float = L2):
    """L2 logistic regression on standardised features; returns a scoring function."""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    center, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
    design = np.c_[(x - center) / scale, np.ones(len(x))]
    penalty = np.r_[np.ones(x.shape[1]), 0.0]

    def loss(w):
        logits = design @ w
        cost = np.mean(np.logaddexp(0, logits) - y * logits) + 0.5 * l2 * np.sum(penalty * w * w) / len(y)
        grad = design.T @ (expit(logits) - y) / len(y) + l2 * penalty * w / len(y)
        return cost, grad

    w = optimize.minimize(loss, np.zeros(design.shape[1]), jac=True, method="L-BFGS-B",
                          options={"maxiter": 200}).x
    return lambda z: expit(np.c_[(np.asarray(z, dtype=np.float64) - center) / scale,
                                 np.ones(len(z))] @ w)


def folds(group_of: dict[str, int], labels: dict[str, int], k: int, seed: int) -> list[set[str]]:
    """Assign whole groups to k folds, balancing positives, deterministically."""
    rng = np.random.default_rng(seed)
    members: dict[int, list[str]] = {}
    for listing_id in labels:
        members.setdefault(group_of[listing_id], []).append(listing_id)
    order = list(members)
    rng.shuffle(order)
    order.sort(key=lambda g: -sum(labels[i] for i in members[g]))  # stable: spread positives first
    out = [set() for _ in range(k)]
    sizes = [[0, 0] for _ in range(k)]
    for g in order:
        pos = sum(labels[i] for i in members[g])
        target = min(range(k), key=lambda f: (sizes[f][0] if pos else sizes[f][1], sizes[f][0] + sizes[f][1]))
        out[target].update(members[g])
        sizes[target][0] += pos
        sizes[target][1] += len(members[g]) - pos
    return out


def compare(features: dict[str, dict[str, np.ndarray]], labels: dict[str, int], group_of: dict[str, int],
            k: int = FOLDS, seeds=range(SPLIT_SEED, SPLIT_SEED + 20)) -> dict:
    """Grouped k-fold validation AUC of each aggregator on the same splits."""
    ids = sorted(labels)
    n_pos = sum(labels[i] for i in ids)
    k = min(k, n_pos, len(ids) - n_pos)
    if k < 2:
        return {"selected": DEFAULT, "reason": "Too few labelled apartments of each class to validate.",
                "labelled": len(ids), "positives": n_pos}
    per_split = {name: [] for name in features}
    for seed in seeds:
        for held in folds(group_of, {i: labels[i] for i in ids}, k, seed):
            train = [i for i in ids if i not in held]
            test = [i for i in ids if i in held]
            y_train = [labels[i] for i in train]
            if len(set(y_train)) < 2 or len({labels[i] for i in test}) < 2:
                continue
            for name, rows in features.items():
                score = fit([rows[i] for i in train], y_train)
                per_split[name].append(auc(score([rows[i] for i in test]), [labels[i] for i in test]))
    summary = {name: {"auc_mean": round(float(np.mean(v)), 4), "auc_sd": round(float(np.std(v)), 4),
                      "splits": len(v)} for name, v in per_split.items() if v}
    selected, reason = DEFAULT, "Kept the mean: no validated advantage."
    if {"mean-v1", "outdoor-v1"} <= set(summary):
        diff = np.asarray(per_split["outdoor-v1"]) - np.asarray(per_split["mean-v1"])
        summary["difference"] = {"mean": round(float(diff.mean()), 4), "sd": round(float(diff.std()), 4),
                                 "outdoor_better": int((diff > 0).sum()), "splits": int(len(diff))}
        if diff.mean() > diff.std():
            selected, reason = "outdoor-v1", "Outdoor evidence improved validation AUC beyond its spread."
    return {"selected": selected, "reason": reason, "labelled": len(ids), "positives": n_pos, "folds": k,
            "seeds": [min(seeds), max(seeds)], "results": summary}
