"""Reserve unseen apartment groups before collecting their feedback."""
import json
import uuid
from . import learning, readout, protocol
from .jobs import now
from .storage import filter_reasons

SCHEMA = "CREATE TABLE IF NOT EXISTS prospective_cohorts (id TEXT PRIMARY KEY, data TEXT NOT NULL);"


def cohorts(store):
    with store.connect() as db:
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM prospective_cohorts ORDER BY rowid DESC")]


def protected(store):
    rows = cohorts(store)
    return ({i for row in rows for i in row["test_ids"]},
            {sha for row in rows for sha in row["test_sha256"]})


def protected_ids(store, listings, hashes):
    ids, sha = protected(store)
    if not sha:
        return ids
    group_of = readout.groups(listings, lambda p: hashes(p) if hashes.path(p).exists() else p)
    touched = {group_of[l["id"]] for l in listings if l["id"] in ids
               or any(hashes(p) in sha for p in l.get("photos", []) if hashes.path(p).exists())}
    return ids | {i for i,group in group_of.items() if group in touched}


def training(data, store, hashes):
    held = protected_ids(store, data["listings"], hashes)
    return ({i: v for i, v in data["ratings"].items() if i not in held},
            [p for p in data["comparisons"] if p["a"] not in held and p["b"] not in held], held)


def feedback_is_held(db, payload, validate=True):
    ids = {l["id"] for l in payload["listings"]}
    sha = {s for l in payload["listings"] for s in l["photo_sha256"] if s}
    rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM prospective_cohorts")]
    protected_id = {i for row in rows for i in row["test_ids"]}
    protected_sha = {s for row in rows for s in row["test_sha256"]}
    if not rows: return False
    # Check the displayed gallery against the frozen one before saving a label.
    for row in rows:
        if not (ids.intersection(row["test_ids"]) or sha.intersection(row["test_sha256"])): continue
        frozen = {l["id"]:l for l in row["context"]["listings"]}
        if validate and (payload["params"] != row["context"]["params"] or payload.get("settings",row["settings"]) != row["settings"]):
            raise ValueError("Use the reserved experiment's original brief and sensory mode when rating its apartments.")
        if validate and not ids <= set(frozen):
            raise ValueError("Compare reserved apartments with another apartment from the same frozen experiment.")
        for listing in payload["listings"]:
            original = frozen.get(listing["id"])
            if validate and original and any(listing.get(k) != original.get(k) for k in
                    ("photo_sha256","price","size","bedrooms","coords","balcony","balcony_size","balcony_covered")):
                raise ValueError("This reserved apartment changed since the model was frozen. Its new gallery or fields cannot label the original experiment.")
    from .catalogue import photo_keys
    listings = [json.loads(r[0]) for r in db.execute("SELECT data FROM listings")]
    group_of = readout.groups(listings, lambda p: next(iter(photo_keys({"photos":[p]}))))
    touched = {group_of[l["id"]] for l in listings if l["id"] in protected_id or photo_keys(l) & protected_sha}
    protected_id |= {i for i,g in group_of.items() if g in touched}
    return bool(ids & protected_id or sha & protected_sha)


def reserve(store, queue, hashes, count=10, candidate_ids=None):
    with store.lock:
        if any(row["status"] == "collecting" for row in cohorts(store)):
            raise ValueError("A prospective cohort is already collecting choices.")
        status = learning.status(store, queue)
        if status["pending"] or status["progress"] or not status["checkpoint"]:
            raise ValueError("Wait for saved memory to finish before freezing a cohort.")
        data = store.get()
        ratings, pairs, held_before = training(data, store, hashes)
        reviewed = set(ratings) | {p[k] for p in pairs for k in ("a", "b")}
        eligible = [l for l in data["listings"] if l.get("photos") and l.get("vision") and not filter_reasons(l, data["settings"])]
        valid={l['id'] for l in eligible}
        ratings={i:v for i,v in ratings.items() if i in valid}
        pairs=[p for p in pairs if p['a'] in valid and p['b'] in valid]
        reviewed=set(ratings)|{p[k] for p in pairs for k in ('a','b')}
        group_of = readout.groups(eligible, hashes)
        seen = {group_of[i] for i in reviewed if i in group_of}
        journal_sha = {s for r in learning.events(store) for l in r["payload"]["listings"] for s in l["photo_sha256"] if s}
        seen |= {group_of[l["id"]] for l in eligible if any(hashes(p) in journal_sha for p in l["photos"])}
        candidate = [l for l in eligible if l["id"] not in held_before and group_of[l["id"]] not in seen]
        if candidate_ids is not None:
            candidate = [l for l in candidate if l["id"] in set(candidate_ids)]
        # Deterministic round-robin across areas, then price. No model score enters selection.
        areas = {}
        for l in sorted(candidate, key=lambda l: (l["price"], l["id"])):
            areas.setdefault(l.get("area", ""), []).append(l)
        chosen, groups = [], set()
        while areas and len(groups) < count:
            for area in sorted(list(areas)):
                l = areas[area].pop(0)
                if group_of[l["id"]] not in groups:
                    groups.add(group_of[l["id"]]); chosen.append(l["id"])
                if not areas[area]: del areas[area]
                if len(groups) >= count: break
        if len(groups) < 3:
            raise ValueError("Import at least three unseen apartment groups to reserve a cohort.")
        test = [l for l in eligible if group_of[l["id"]] in groups]
        train = [l for l in eligible if l["id"] in reviewed]
        if len(ratings) + len(pairs) < 5 or not train:
            raise ValueError("Save at least five training choices before freezing a cohort.")
        rows = learning.events(store, active=True)
        row = {"id": uuid.uuid4().hex, "status": "collecting", "created": now(),
               "protocol": "prospective-groups-v1", "checkpoint": status["checkpoint"],
               "design": protocol.design(),
               "base_checkpoint": queue.state("memory_base_checkpoint"), "revision": status["revision"],
               "settings": data["settings"], "train_ratings": ratings, "train_pairs": pairs,
               "feedback_provenance":data.get("feedback_provenance",{}),
               "train_ids": [l["id"] for l in train], "test_ids": [l["id"] for l in test],
               "test_sha256": sorted({hashes(p) for l in test for p in l["photos"]}),
               "group_of": group_of, "held_groups": len(groups),
               "candidate_pool_ids":candidate_ids,
               "context": learning.snapshot(train + test, data["settings"], [], hashes, queue),
               "events": [r for r in rows if not any(l["id"] in held_before for l in r["payload"]["listings"])]}
        with store.connect() as db:
            db.execute("INSERT INTO prospective_cohorts VALUES (?,?)", (row["id"], json.dumps(row)))
        return summary(row, data)


def summary(row, data):
    test = set(row["test_ids"])
    labels = {i: v for i, v in data["ratings"].items() if i in test}
    pairs = [p for p in data["comparisons"] if (p["a"] in test or p["b"] in test)
             and {p["a"], p["b"]} <= set(row["train_ids"] + row["test_ids"])]
    from .storage import feedback_counts
    return {k: row[k] for k in ("id", "status", "created", "protocol", "checkpoint", "revision", "held_groups", "test_ids")} | {
        "feedback_counts":feedback_counts(data,test),
        "choices": len(labels) + len(pairs), "rated": len(labels), "pairs": len(pairs),
        "can_evaluate": len(labels) + len(pairs) >= 3, "evaluation_id": row.get("evaluation_id")}


def latest(store):
    rows = cohorts(store)
    return summary(rows[0], store.get()) if rows else None
