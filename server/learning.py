"""Durable choice journal and reproducible positive-reward memory (R4).

Votes and outbox events commit together. Each revision rebuilds from the
immutable base using current choices, so editing a vote undoes its old dose.
"""
from __future__ import annotations

import json
import time
import numpy as np

from .engine.base import digest
from .engine import stimuli
from .gallery import job_params
from .jobs import now
from .vision import MODEL_ID, REVISION, Vision

PROTOCOL = "positive-gallery-ltd-v1"
GALLERY_DOSE = 0.10
JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, feedback_key TEXT NOT NULL,
 kind TEXT NOT NULL, value TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS feedback_key ON feedback_events(feedback_key,id);
"""
ENGINE_SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_runs (
 revision INTEGER PRIMARY KEY, status TEXT NOT NULL, result TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learning_evaluations (
 id TEXT PRIMARY KEY, status TEXT NOT NULL, snapshot TEXT NOT NULL, result TEXT,
 error TEXT, created TEXT NOT NULL, finished TEXT);
"""


def record(db, key, kind, value, payload):
    encoded = json.dumps(value)
    last = db.execute("SELECT id,value,payload FROM feedback_events WHERE feedback_key=? ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    def galleries(context):
        return sorted((l["id"], l["photo_sha256"]) for l in context["listings"])
    if last and last[1] == encoded and galleries(json.loads(last[2])) == galleries(payload) and json.loads(last[2]).get("teacher_review") == payload.get("teacher_review"):
        return last[0]
    return db.execute("INSERT INTO feedback_events(feedback_key,kind,value,payload,created) VALUES (?,?,?,?,?)",
                      (key, kind, encoded, json.dumps(payload), now())).lastrowid


def events(store, active=False):
    with store.connect() as db:
        query = "SELECT * FROM feedback_events"
        if active:
            query += " WHERE id IN (SELECT MAX(id) FROM feedback_events GROUP BY feedback_key)"
        rows = db.execute(query + " ORDER BY id").fetchall()
    return [{"id": r[0], "key": r[1], "kind": r[2], "value": json.loads(r[3]),
             "payload": json.loads(r[4]), "created": r[5]} for r in rows]


def snapshot(listings, settings, winners, hashes, queue):
    copies = []
    for listing in listings:
        row = {k: listing.get(k) for k in ("id", "title", "photos", "vision", "price", "coords", "size",
                                          "balcony", "balcony_size", "balcony_covered", "bedrooms",
                                          "parking", "furnished", "updated_at")}
        for key in ("url","size_kind","field_sources","coord_kind"):
            row[key]=listing.get(key)
        row["photo_sha256"] = [hashes(p) if hashes.path(p).exists() else None for p in row["photos"]]
        copies.append(row)
    center = queue.get_center(MODEL_ID, REVISION) if settings["mode"] == "cyborg" else None
    return {"protocol": PROTOCOL, "dose": GALLERY_DOSE, "params": job_params(settings),
            "settings": dict(settings),
            "listings": copies, "winners": winners,
            "center": {"vector": center[0].tolist(), "count": center[1]} if center else None}


def initialise(queue):
    with queue.connect() as db:
        db.executescript(ENGINE_SCHEMA)


def public_run(row):
    result = json.loads(row["result"])
    result.pop("recordings", None)
    result.pop("edges", None)
    return {"revision": row["revision"], "status": row["status"], "created": row["created"], **result}


def status(store, queue):
    with store.connect() as db:
        target = db.execute("SELECT COALESCE(MAX(id),0) FROM feedback_events").fetchone()[0]
    applied = int(queue.state("memory_revision") or 0)
    with queue.connect() as db:
        runs = [public_run(r) for r in db.execute("SELECT * FROM learning_runs ORDER BY revision DESC LIMIT 20")]
    from .storage import feedback_counts
    return {"protocol": PROTOCOL, "revision": applied, "target": target,
            "feedback_counts":feedback_counts(store.get()),
            "checkpoint": queue.state("current_checkpoint"),
            "progress": json.loads(queue.state("memory_progress") or "null"),
            "worker": queue.worker_status(), "runs": runs,
            "pending": target > applied,
            "negative_protocol": "Dislikes train the readout; no aversive dopamine circuit is simulated."}


class Memory:
    def __init__(self, worker, store):
        self.worker, self.store = worker, store
        self.queue, self.engine, self.checkpoints = worker.queue, worker.engine, worker.checkpoints
        self.vision = None
        initialise(self.queue)

    def ensure_embeddings(self, photos, hashes):
        missing = [(p, sha) for p, sha in zip(photos, hashes)
                   if sha and self.queue.get_embedding(sha, MODEL_ID, REVISION) is None]
        if missing:
            if self.vision is None: self.vision = Vision()
            for start in range(0, len(missing), 8):
                self.worker.heartbeat(job=None)
                batch = missing[start:start+8]
                vectors = self.vision.embed([p for p, _ in batch])
                for (_, sha), vector in zip(batch, vectors):
                    self.queue.put_embedding(sha, MODEL_ID, REVISION, vector)

    def stimuli(self, payload, listing):
        mode, brief = payload["params"]["mode"], payload["params"]["brief"]
        for photo, expected in zip(listing["photos"], listing["photo_sha256"]):
            if stimuli.file_sha256(self.worker.root / photo.lstrip("/")) != expected:
                raise ValueError("A feedback photo changed; import the current gallery before recording a new choice.")
        if mode == "cyborg":
            self.ensure_embeddings(listing["photos"], listing["photo_sha256"])
        frozen = payload.get("center")
        if mode == "cyborg" and not frozen:
            saved = self.queue.state("memory_center")
            if saved:
                frozen = json.loads(saved)
            else:
                vector, count = self.queue.freeze_center(MODEL_ID, REVISION)
                frozen = {"vector": vector.tolist(), "count": count}
                self.queue.set_state("memory_center", json.dumps(frozen))
        center = stimuli.Center.of(np.array(frozen["vector"], dtype=np.float32), frozen["count"]) if frozen else None
        result, seen = [], set()
        for i, photo in enumerate(listing["photos"]):
            sha = stimuli.file_sha256(self.worker.root / photo.lstrip("/"))
            if sha != listing["photo_sha256"][i]:
                raise ValueError("A feedback photo changed; reimport and save the choice again.")
            if sha in seen:
                continue
            seen.add(sha)
            embedding = self.queue.get_embedding(sha, MODEL_ID, REVISION) if mode == "cyborg" else None
            stimulus, _ = stimuli.encode(mode, listing["vision"]["per_photo"][i], listing, brief,
                                          self.engine.channels(), embedding, center)
            result.append((i, stimulus, int(digest([sha, stimulus.key(), PROTOCOL])[:8], 16)))
        if not result:
            raise ValueError("No photos available for reinforcement.")
        return result

    def train(self, rows, progress=True):
        total = sum(len(set(l["photo_sha256"])) for row in rows for l in row["payload"]["listings"]
                    if l["id"] in row["payload"]["winners"])
        done, episodes, changed = 0, 0, 0
        for row in rows:
            payload = row["payload"]
            for listing in payload["listings"]:
                if listing["id"] not in payload["winners"]:
                    continue
                photos = self.stimuli(payload, listing)
                # At most one 10% dose per connection per gallery, independent
                # of the photograph count. Identical photo files are deduplicated.
                eta = 1 - (1 - payload["dose"]) ** (1 / len(photos))
                for _, stimulus, seed in photos:
                    if self.worker.stopping:
                        raise InterruptedError("Worker stopping; revision resumes after restart.")
                    self.worker.heartbeat(job=None)
                    if progress:
                        self.queue.set_state("memory_progress", json.dumps({"done": done, "total": total,
                            "listing_id": listing["id"], "phase": "reinforcement"}))
                    response = self.engine.run_episode(stimulus, reward=True, learning_rate=eta, seed=seed)
                    episodes += 1
                    changed += response.changed_synapses
                    done += 1
        return {"episodes": episodes, "synaptic_updates": changed}

    def probe(self, payload, listing):
        summaries, recording = [], None
        for position, stimulus, seed in self.stimuli(payload, listing):
            self.worker.heartbeat(job=None)
            response = self.engine.run_episode(stimulus, seed=seed, record=recording is None)
            summaries.append(sum(response.mbon_spikes))
            if recording is None:
                recording = {"position": position, "trace": response.replay}
        return {"photos": len(summaries), "mbon_spikes": float(np.mean(summaries))}, recording

    def changes(self, before):
        old = before.arrays["plastic_weight_mv"]
        new = self.engine.net.graph.data[self.engine.plastic]
        indices = np.flatnonzero(new != old)
        top = indices[np.argsort(np.abs(new[indices] - old[indices]))[-256:][::-1]]
        edges = [{"pre_id": str(self.engine.root_ids[self.engine.plastic_pre[i]]),
                  "post_id": str(self.engine.root_ids[self.engine.net.graph.indices[self.engine.plastic[i]]]),
                  "before_mv": float(old[i]), "after_mv": float(new[i])} for i in top]
        return {"changed_connections": len(indices), "shown_connections": len(top), "edges": edges}

    def run_once(self):
        all_rows = events(self.store)
        if not all_rows:
            return False
        revision = all_rows[-1]["id"]
        if revision <= int(self.queue.state("memory_last_attempt") or 0):
            return False
        active = {}
        for row in all_rows:
            active[row["key"]] = row
        rows = list(active.values())
        before, parent = self.engine.checkpoint(), self.worker.checkpoint
        base = self.queue.state("memory_base_checkpoint")
        if not base:
            base = parent
            self.queue.set_state("memory_base_checkpoint", base)
        latest, started = all_rows[-1], time.perf_counter()
        payload = latest["payload"]
        chosen = next((l for l in payload["listings"] if l["id"] in payload["winners"]),
                      payload["listings"][0] if payload["listings"] else None)
        try:
            try:
                can_probe = bool(chosen and chosen["photos"] and chosen.get("vision")
                    and len(chosen["vision"].get("per_photo", [])) == len(chosen["photos"]) and all(
                    stimuli.file_sha256(self.worker.root / p.lstrip("/")) == sha
                    for p, sha in zip(chosen["photos"], chosen["photo_sha256"])))
            except OSError:
                can_probe = False
            self.queue.set_state("memory_progress", json.dumps({"phase": "before", "done": 0, "total": 0}))
            pre, pre_record = self.probe(payload, chosen) if can_probe else ({}, None)
            self.engine.restore(self.checkpoints.load(base))
            trained = self.train(rows)
            learned = self.engine.checkpoint()
            changes = self.changes(before)
            post, post_record = self.probe(payload, chosen) if can_probe else ({}, None)
            self.engine.restore(learned)
            checkpoint = self.checkpoints.save(learned, f"choice-{revision}", parent=parent, make_current=False)
            result = {**trained, **changes, "protocol": PROTOCOL, "base_checkpoint": base,
                      "before_checkpoint": parent, "checkpoint": checkpoint,
                      "listing_id": chosen["id"] if chosen else None, "title": chosen.get("title") if chosen else None,
                      "feedback_kind": latest["kind"], "feedback_value": latest["value"],
                      "active_choices": len(rows), "rewarded_choices": sum(bool(r["payload"]["winners"]) for r in rows),
                      "probe": {"before": pre, "after": post, "matched_seeds": True} if can_probe else None,
                      "recordings": {"before": pre_record, "after": post_record},
                      "seconds": round(time.perf_counter() - started, 2)}
            # Pointer and revision commit together. Retry always starts at base;
            # a crash before publishing cannot apply a dose twice.
            with self.queue.transaction() as db:
                db.execute("INSERT OR REPLACE INTO learning_runs VALUES (?,?,?,?)", (revision, "done", json.dumps(result), now()))
                db.executemany("INSERT OR REPLACE INTO engine_state VALUES (?,?)", [
                    ("current_checkpoint", checkpoint), ("current_fingerprint", self.engine.fingerprint()),
                    ("memory_revision", str(revision)), ("memory_last_attempt", str(revision)), ("memory_progress", "null")])
            self.worker.checkpoint = checkpoint
        except InterruptedError:
            self.engine.restore(before)
            self.queue.set_state("memory_progress", "null")
            raise
        except Exception as error:
            self.engine.restore(before)
            result = {"error": str(error), "listing_id": chosen["id"] if chosen else None, "edges": []}
            with self.queue.transaction() as db:
                db.execute("INSERT OR REPLACE INTO learning_runs VALUES (?,?,?,?)", (revision, "error", json.dumps(result), now()))
                db.executemany("INSERT OR REPLACE INTO engine_state VALUES (?,?)",
                               [("memory_last_attempt", str(revision)), ("memory_progress", "null")])
            return True
        # Cache refresh is downstream of the published checkpoint. A refresh
        # failure must never roll the in-memory engine back after publication.
        current = self.store.get()
        ids = {l["id"] for r in rows for l in r["payload"]["listings"]}
        for listing in current["listings"]:
            if listing["id"] in ids and listing.get("photos"):
                try:
                    self.queue.enqueue(listing["id"], listing["photos"], job_params(current["settings"]))
                except Exception as error:
                    import logging
                    logging.getLogger(__name__).warning("Memory published; analysis refresh failed: %s", error)
        return True
