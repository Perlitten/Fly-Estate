"""Frozen apartment-group holdout: no held-out photo or choice reinforces memory.

The live checkpoint is restored even on failure. Reports measure preference
agreement; changing synapses alone is never presented as improved taste.
"""
import json
import math
import time
import uuid
import resource
import sys

import numpy as np

from . import learning, readout, prospective, protocol
from .brain import Brain, distance_km
from .jobs import now


def split(listings, ratings, comparisons, hashes):
    ids = {l["id"] for l in listings}
    labels = {i: v for i, v in ratings.items() if i in ids}
    pairs = [p for p in comparisons if p["a"] in ids and p["b"] in ids]
    reviewed = set(labels) | {p[k] for p in pairs for k in ("a", "b")}
    group_of = readout.groups(listings, hashes)
    groups = sorted({group_of[i] for i in reviewed})
    if len(groups) < 5:
        raise ValueError("At least five distinct reviewed apartment groups are needed.")
    for seed in range(783, 803):
        held = set(np.random.default_rng(seed).permutation(groups)[:max(1, math.ceil(len(groups) * .2))].tolist())
        test = {i for i in ids if group_of[i] in held}
        train = ids - test
        train_pairs = [p for p in pairs if p["a"] in train and p["b"] in train]
        test_pairs = [p for p in pairs if p["a"] in test or p["b"] in test]
        train_ratings = {i: v for i, v in labels.items() if i in train}
        test_ratings = {i: v for i, v in labels.items() if i in test}
        # Feasibility depends only on group/feedback counts, never model scores.
        if len(train_pairs) + len(train_ratings) >= 5 and len(test_pairs) + len(test_ratings) >= 2:
            return {"train_ids": sorted(train), "test_ids": sorted(test), "seed": seed,
                    "groups": len(groups), "held_groups": len(held), "group_of": group_of,
                    "train_ratings": train_ratings, "test_ratings": test_ratings,
                    "train_pairs": train_pairs, "test_pairs": test_pairs}
    raise ValueError("More independent choices are needed for a group holdout with five training and two test choices.")


def clusters(pairs, group_of):
    """Connected comparison components; shared apartments cannot be independent."""
    parent = {}
    def root(x):
        parent.setdefault(x, x)
        if parent[x] != x: parent[x] = root(parent[x])
        return parent[x]
    for p in pairs:
        a, b = root(group_of[p["a"]]), root(group_of[p["b"]])
        parent[a] = b
    return [root(group_of[p["a"]]) for p in pairs]


def cluster_interval(values, groups):
    unique = sorted(set(groups))
    if len(unique) < 3:
        return None
    totals = np.array([sum(v for v, g in zip(values, groups) if g == key) for key in unique])
    sizes = np.array([groups.count(key) for key in unique])
    draw = np.random.default_rng(783).integers(0, len(unique), (2000, len(unique)))
    samples = totals[draw].sum(axis=1) / sizes[draw].sum(axis=1)
    return [round(float(x), 4) for x in np.quantile(samples, [.025, .975])]


def metrics(scores, ratings, pairs, group_of=None):
    correct, ties = [], []
    for p in pairs:
        diff = scores[p["a"]] - scores[p["b"]]
        if p["choice"] == 0:
            ties.append(abs(diff) <= .05)
        else:
            correct.append(diff * p["choice"] > 0)
    n, hits = len(correct), sum(correct)
    interval = None
    if n:
        p, z = hits / n, 1.96
        center = (p + z*z/(2*n)) / (1 + z*z/n)
        radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
        interval = [round(center-radius, 4), round(center+radius, 4)]
    binary = {i: int(v > 0) for i, v in ratings.items() if v != 0}
    decisive = [p for p in pairs if p["choice"] != 0]
    component = clusters(decisive, group_of) if group_of else []
    # One outcome per group. Conflicting duplicate labels cannot define a class.
    buckets = {}
    for i,value in binary.items(): buckets.setdefault(group_of[i] if group_of else i, []).append((scores[i],value))
    grouped = {g:(float(np.mean([s for s,_ in rows])),rows[0][1]) for g,rows in buckets.items()
               if len({v for _,v in rows}) == 1}
    ranked = sorted(grouped, key=lambda g: (-grouped[g][0],str(g)))
    k = min(5, len(ranked))
    return {"pairwise_accuracy": hits/n if n else None, "pairs": n, "correct": hits,
            "wilson_95": interval, "ties": len(ties), "tie_agreement": float(np.mean(ties)) if ties else None,
            "auc": readout.auc([s for s,_ in grouped.values()], [v for _,v in grouped.values()]) if grouped else None,
            "rated_apartments": len(binary), "independent_components": len(set(component)),
            "cluster_95": cluster_interval(correct, component) if component else None,
            "precision_at_k": sum(grouped[g][1] for g in ranked[:k])/k if k else None,
            "ranking_k": k, "ranking_groups": len(grouped), "conflicting_rated_groups": len(buckets)-len(grouped)}


def enqueue(queue, store, hashes):
    data = store.get()
    labels, pairs, protected = prospective.training(data, store, hashes)
    from .storage import filter_reasons
    all_eligible = [l for l in data["listings"] if l.get("vision") and l.get("photos")
                    and not filter_reasons(l, data["settings"])]
    reviewed = set(labels) | {p[k] for p in pairs for k in ("a", "b")}
    listings = [l for l in all_eligible if l["id"] in reviewed]
    partition = split(listings, labels, pairs, hashes)
    context = learning.snapshot(listings, data["settings"], [], hashes, queue)
    rows = learning.events(store, active=True)
    held_sha = {hashes(photo) for l in listings if l["id"] in partition["test_ids"] for photo in l["photos"]}
    train_events = [r for r in rows if all(l["id"] not in set(partition["test_ids"]) | protected
                    and not (set(l["photo_sha256"]) & held_sha) for l in r["payload"]["listings"])]
    snapshot = {"context": context, "settings": data["settings"], "partition": partition,
                "feedback_provenance":data.get("feedback_provenance",{}),
                "events": train_events, "revision": max((r["id"] for r in learning.events(store)), default=0)}
    with queue.transaction() as db:
        active = db.execute("SELECT id FROM learning_evaluations WHERE status IN ('queued','running') ORDER BY created LIMIT 1").fetchone()
        if active: return active["id"]
        key = uuid.uuid4().hex
        db.execute("INSERT INTO learning_evaluations(id,status,snapshot,created) VALUES (?,?,?,?)",
                   (key, "queued", json.dumps(snapshot), now()))
    return key


def enqueue_prospective(queue, store):
    with store.lock:
        rows = prospective.cohorts(store)
        if not rows: raise ValueError("Reserve unseen apartments before collecting feedback.")
        row, data = rows[0], store.get()
        if row.get("evaluation_id"):
            with queue.transaction() as db:
                existing = db.execute("SELECT status FROM learning_evaluations WHERE id=?", (row["evaluation_id"],)).fetchone()
                if existing and existing["status"] == "error":
                    protocol.require_design(row.get("design"))
                    if db.execute("SELECT id FROM learning_evaluations WHERE status IN ('queued','running')").fetchone():
                        raise ValueError("Wait for the current evaluation to finish.")
                    db.execute("UPDATE learning_evaluations SET status='queued',error=NULL,finished=NULL WHERE id=?", (row["evaluation_id"],))
            return row["evaluation_id"]
        protocol.require_design(row.get("design"))
        summary = prospective.summary(row, data)
        if not summary["can_evaluate"]: raise ValueError("Save at least three choices involving the reserved apartments.")
        test, ids = set(row["test_ids"]), set(row["train_ids"] + row["test_ids"])
        partition = {"train_ids": row["train_ids"], "test_ids": row["test_ids"], "seed": 783,
                     "group_of": row["group_of"], "held_groups": row["held_groups"],
                     "train_ratings": row["train_ratings"], "train_pairs": row["train_pairs"],
                     "test_ratings": {i: v for i, v in data["ratings"].items() if i in test},
                     "test_pairs": [p for p in data["comparisons"] if {p["a"], p["b"]} <= ids
                                    and (p["a"] in test or p["b"] in test)]}
        key = uuid.uuid4().hex
        snapshot = {"context": row["context"], "settings": row["settings"], "partition": partition,
                    "feedback_provenance":{**row.get("feedback_provenance",{}),**{k:v for k,v in data.get("feedback_provenance",{}).items() if k.removeprefix("rating:") in test}},
                    "events": row["events"], "revision": row["revision"], "cohort": row["id"],
                    "frozen_checkpoint": row["checkpoint"], "base_checkpoint": row["base_checkpoint"]}
        snapshot["design"] = row["design"]
        with queue.transaction() as db:
            if db.execute("SELECT id FROM learning_evaluations WHERE status IN ('queued','running')").fetchone():
                raise ValueError("Wait for the current evaluation to finish.")
            db.execute("INSERT INTO learning_evaluations(id,status,snapshot,created) VALUES (?,?,?,?)",
                       (key, "queued", json.dumps(snapshot), now()))
        row.update(status="frozen", evaluation_id=key)
        with store.connect() as db:
            db.execute("UPDATE prospective_cohorts SET data=? WHERE id=?", (json.dumps(row), row["id"]))
        return key


def rewired(engine):
    """Degree-preserving double-edge swaps confined to KC→MBON connections."""
    from .engine.olfactory import OlfactoryMBEngine
    from .engine import subgraph
    data = subgraph.load()
    data = {k: v.copy() if isinstance(v, np.ndarray) else v for k, v in data.items()}
    group = data["group"]
    mask = (group[data["pre"]] == subgraph.GROUPS.index("kc")) & (group[data["post"]] == subgraph.GROUPS.index("mbon"))
    rng = np.random.default_rng(783)
    positions = np.flatnonzero(mask)
    existing = {(int(data["pre"][i]), int(data["post"][i])) for i in positions}
    swaps = 0
    for _ in range(10 * len(positions)):
        a, b = rng.choice(positions, 2, replace=False)
        pa, pb, qa, qb = int(data["pre"][a]), int(data["pre"][b]), int(data["post"][a]), int(data["post"][b])
        if pa == pb or qa == qb or (pa, qb) in existing or (pb, qa) in existing: continue
        existing.remove((pa, qa)); existing.remove((pb, qb))
        existing.update(((pa, qb), (pb, qa)))
        data["post"][a], data["post"][b] = qb, qa
        swaps += 1
    import hashlib
    fingerprint = hashlib.sha256(data["post"].tobytes()).hexdigest()
    data["sha256"] = "kc-mbon-rewire-v1:" + fingerprint
    if not swaps: raise ValueError("No valid KC→MBON rewiring swaps were possible.")
    control = OlfactoryMBEngine(params=engine.params, data=data)
    control.rewire_info = {"swaps": swaps, "post_sha256": fingerprint, "seed": 783}
    return control


def latest(queue):
    with queue.connect() as db:
        selected = queue.state("selected_evaluation")
        row = db.execute("SELECT id,status,result,error,created,finished,snapshot FROM learning_evaluations WHERE id=?", (selected,)).fetchone() if selected else None
        row = row or db.execute("SELECT id,status,result,error,created,finished,snapshot FROM learning_evaluations ORDER BY created DESC LIMIT 1").fetchone()
    if not row: return None
    out = dict(row)
    snapshot = json.loads(out.pop("snapshot"))
    out["revision"] = snapshot["revision"]
    out["result"] = json.loads(out["result"]) if out["result"] else None
    if out["result"]:
        sources=snapshot.get("feedback_provenance",{})
        counts={}
        for phase in ("train","test"):
            partition=snapshot["partition"]
            labels=partition[f"{phase}_ratings"]
            agent=sum(sources.get(f"rating:{i}",{}).get("actor")=="agent" for i in labels)
            counts[phase]={"human":len(labels)-agent+len(partition[f"{phase}_pairs"]),"agent":agent}
        out["result"]["label_sources"]=counts
        modes = sorted({event["payload"]["params"]["mode"] for event in snapshot["events"] if event["payload"]["winners"]})
        mode = snapshot["context"]["params"]["mode"]
        out["result"]["sensory"] = {"evaluation_mode":mode,"memory_training_modes":modes,
                                    "cross_codec":bool(modes and modes != [mode])}
    return out


def run_once(worker):
    queue, memory = worker.queue, worker.memory
    with queue.transaction() as db:
        row = db.execute("SELECT * FROM learning_evaluations WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if not row: return False
        db.execute("UPDATE learning_evaluations SET status='running' WHERE id=?", (row["id"],))
    frozen = json.loads(row["snapshot"])
    context, partition = frozen["context"], frozen["partition"]
    listings = context["listings"]
    saved = worker.engine.checkpoint()
    started = time.perf_counter()
    try:
        if frozen.get("cohort"): protocol.require_design(frozen.get("design"))
        base = frozen.get("base_checkpoint") or queue.state("memory_base_checkpoint") or worker.checkpoint
        def score(x):
            p, _ = Brain.fit(np.asarray(x), listings, partition["train_ratings"], partition["train_pairs"],
                             normalization_ids=partition["train_ids"])
            return {l["id"]: float(v) for l, v in zip(listings, p)}
        scores = {}
        latency = {}
        control_info = {}
        brain = Brain()
        try:
            x, _ = brain.features(listings, frozen["settings"])
            scores["rate_readout"] = score(x)
        finally:
            if brain.pool: brain.pool.shutdown(wait=True)
            del brain
        # The direct CLIP arm uses the full frozen model embedding, not the
        # 16-channel projection, with the same training-only logistic fit.
        clip = []
        for listing in listings:
            memory.ensure_embeddings(listing["photos"], listing["photo_sha256"])
            from .vision import MODEL_ID, REVISION
            vectors = {sha: queue.get_embedding(sha, MODEL_ID, REVISION) for sha in listing["photo_sha256"]}
            clip.append(np.mean(list(vectors.values()), axis=0))
        scores["clip_readout"] = score(clip)
        total = 3 * sum(len(set(l["photo_sha256"])) for l in listings)
        done = 0
        for name in ("spiking_fixed", "spiking_memory", "spiking_rewired"):
            active_engine = rewired(worker.engine) if name == "spiking_rewired" else worker.engine
            if name == "spiking_rewired": control_info = active_engine.rewire_info
            if name != "spiking_rewired": worker.engine.restore(worker.checkpoints.load(base))
            if name == "spiking_memory":
                queue.set_state("evaluation_progress", json.dumps({"phase": "training_holdout_memory", "done": done, "total": total}))
                if frozen.get("frozen_checkpoint"):
                    worker.engine.restore(worker.checkpoints.load(frozen["frozen_checkpoint"]))
                else:
                    memory.train(frozen["events"], progress=False)
            x = []
            wall = []
            for listing in listings:
                vectors = []
                for _, stimulus, seed in memory.stimuli(context, listing):
                    if worker.stopping: raise InterruptedError()
                    worker.heartbeat(job=None)
                    queue.set_state("evaluation_progress", json.dumps({"phase": name, "done": done, "total": total}))
                    result = active_engine.run_episode(stimulus, seed=seed)
                    vectors.append(readout.photo_vector(result.to_json()))
                    wall.append(result.wall_seconds)
                    done += 1
                x.append(np.mean(vectors, axis=0))
            scores[name] = score(x)
            latency[name] = {"photos": len(wall), "mean_photo_seconds": round(float(np.mean(wall)), 4),
                             "p95_photo_seconds": round(float(np.quantile(wall, .95)), 4)}
        scores["price_distance"] = {l["id"]: -l["price"] / frozen["settings"]["ceiling"]
            - (distance_km(frozen["settings"]["ideal"], l["coords"]) / 12 if l.get("coords") else 0) for l in listings}
        measured = {name: metrics(p, partition["test_ratings"], partition["test_pairs"], partition["group_of"]) for name, p in scores.items()}
        fixed = measured["spiking_fixed"]["pairwise_accuracy"]
        learned = measured["spiking_memory"]["pairwise_accuracy"]
        decisive = [p for p in partition["test_pairs"] if p["choice"]]
        differences = [int((scores["spiking_memory"][p["a"]]-scores["spiking_memory"][p["b"]])*p["choice"] > 0)
                       - int((scores["spiking_fixed"][p["a"]]-scores["spiking_fixed"][p["b"]])*p["choice"] > 0) for p in decisive]
        components = clusters(decisive, partition["group_of"])
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == "darwin" else 1024)
        result = {"protocol": "prospective-groups-v1" if frozen.get("cohort") else "group-holdout-v2",
                  "cohort": frozen.get("cohort"), "frozen_checkpoint": frozen.get("frozen_checkpoint"),
                  "design": frozen.get("design", protocol.design()),
                  "seed": partition["seed"], "revision": frozen["revision"],
                  "train_apartments": len(partition["train_ids"]), "test_apartments": len(partition["test_ids"]),
                  "train_choices": len(partition["train_ratings"]) + len(partition["train_pairs"]),
                  "test_choices": len(partition["test_ratings"]) + len(partition["test_pairs"]),
                  "held_groups": partition["held_groups"], "reinforced_events": len(frozen["events"]),
                  "photo_coverage": 1.0, "models": measured, "seconds": round(time.perf_counter()-started, 2),
                  "plasticity_delta": learned-fixed if fixed is not None and learned is not None else None,
                  "plasticity_cluster_95": cluster_interval(differences, components) if components else None,
                  "independent_components": len(set(components)), "latency": latency,
                  "worker_peak_rss_mb": round(peak, 1), "rss_scope": "worker lifetime high-water mark, not evaluation-only",
                  "control": {"protocol": "kc-mbon-rewire-v1", **control_info,
                              "preserves": "KC out-degree, MBON in-degree and per-KC weight multiset; other connections unchanged"},
                  "conclusion": "Prospective frozen-model measurement. Inspect sample counts and component uncertainty before inferring an improvement."
                    if frozen.get("cohort") else "Retrospective held-out pilot. Repeated runs do not add independent evidence; improvement is not established.",
                  "test_predictions": [{"id": l["id"], "title": l.get("title"),
                    "score": scores["spiking_memory"][l["id"]]} for l in listings if l["id"] in partition["test_ids"]]}
        with queue.connect() as db:
            db.execute("UPDATE learning_evaluations SET status='done',result=?,finished=? WHERE id=?",
                       (json.dumps(result), now(), row["id"]))
    except InterruptedError:
        with queue.connect() as db:
            db.execute("UPDATE learning_evaluations SET status='queued' WHERE id=?", (row["id"],))
        raise
    except Exception as error:
        with queue.connect() as db:
            db.execute("UPDATE learning_evaluations SET status='error',error=?,finished=? WHERE id=?",
                       (str(error), now(), row["id"]))
    finally:
        worker.engine.restore(saved)
        queue.set_state("evaluation_progress", "null")
    return True
