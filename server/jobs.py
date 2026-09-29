"""Durable simulation queue shared by the HTTP server and the engine worker.

SQLite in WAL mode (`data/engine/engine.sqlite`). The HTTP server only
enqueues, reads and cancels; the single worker claims jobs, records per-photo
progress and results. A job interrupted by a crash or restart keeps its
finished photos and is requeued when the next worker starts.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/engine/engine.sqlite"
LEASE_SECONDS = 30.0
ACTIVE = ("queued", "running")
MIN_CENTER_PHOTOS = 32
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, listing_id TEXT NOT NULL, status TEXT NOT NULL,
    total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0, worker TEXT, checkpoint TEXT, error TEXT,
    created TEXT NOT NULL, started TEXT, heartbeat TEXT, finished TEXT);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created);
CREATE INDEX IF NOT EXISTS jobs_listing ON jobs(listing_id, created);
CREATE TABLE IF NOT EXISTS job_items (
    job_id TEXT NOT NULL REFERENCES jobs(id), position INTEGER NOT NULL, photo TEXT NOT NULL,
    status TEXT NOT NULL, cache_key TEXT, error TEXT, updated TEXT,
    PRIMARY KEY (job_id, position));
CREATE TABLE IF NOT EXISTS activity (
    cache_key TEXT PRIMARY KEY, listing_id TEXT NOT NULL, position INTEGER NOT NULL, photo TEXT NOT NULL,
    photo_sha256 TEXT NOT NULL, codec TEXT NOT NULL, engine_version TEXT NOT NULL,
    fingerprint TEXT NOT NULL, checkpoint TEXT, result TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS activity_listing ON activity(listing_id, position, created);
CREATE TABLE IF NOT EXISTS checkpoints (
    hash TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, version TEXT NOT NULL, label TEXT NOT NULL,
    parent TEXT, created TEXT NOT NULL, meta TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS engine_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS photo_embeddings (
    photo_sha256 TEXT NOT NULL, model TEXT NOT NULL, revision TEXT NOT NULL, dim INTEGER NOT NULL,
    vector BLOB NOT NULL, created TEXT NOT NULL, PRIMARY KEY (photo_sha256, model, revision));
CREATE TABLE IF NOT EXISTS embedding_centers (
    model TEXT NOT NULL, revision TEXT NOT NULL, dim INTEGER NOT NULL, count INTEGER NOT NULL,
    vector BLOB NOT NULL, created TEXT NOT NULL, PRIMARY KEY (model, revision));
"""
# Columns added after R2; applied to existing databases in `Queue.__init__`.
MIGRATIONS = {"jobs": {"params": "TEXT NOT NULL DEFAULT '{}'"}}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Queue:
    def __init__(self, path: Path = DATABASE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            for table, columns in MIGRATIONS.items():
                present = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns.items():
                    if name not in present:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    # -- jobs (HTTP server side) -------------------------------------------
    def enqueue(self, listing_id: str, photos: list[str], params: dict | None = None) -> tuple[dict, bool]:
        """Queue every photo of a listing; returns (job, created).

        `params` (codec mode and the brief snapshot) are part of the job's
        identity: enqueueing is idempotent while a job with the same listing
        and params is active.
        """
        if not photos:
            raise ValueError("A simulation needs at least one photo.")
        encoded = json.dumps(params or {}, sort_keys=True)
        with self.transaction() as db:
            active = db.execute(f"SELECT id FROM jobs WHERE listing_id=? AND params=? AND status IN {ACTIVE} "
                                "ORDER BY created LIMIT 1", (listing_id, encoded)).fetchone()
            if active:
                job_id, created = active["id"], False
            else:
                job_id, created, stamp = uuid.uuid4().hex, True, now()
                db.execute("INSERT INTO jobs (id, listing_id, status, total, created, params) VALUES (?,?,?,?,?,?)",
                           (job_id, listing_id, "queued", len(photos), stamp, encoded))
                db.executemany("INSERT INTO job_items (job_id, position, photo, status, updated) VALUES (?,?,?,?,?)",
                               [(job_id, k, photo, "pending", stamp) for k, photo in enumerate(photos)])
        return self.get(job_id), created

    def get(self, job_id: str, items: bool = True) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            job = self._job(row)
            if items:
                job["items"] = [dict(r) for r in db.execute(
                    "SELECT position, photo, status, cache_key, error, updated FROM job_items "
                    "WHERE job_id=? ORDER BY position", (job_id,))]
        return job

    def list(self, listing_id: str | None = None, limit: int = 20) -> list[dict]:
        with self.connect() as db:
            if listing_id:
                rows = db.execute("SELECT * FROM jobs WHERE listing_id=? ORDER BY created DESC LIMIT ?",
                                  (listing_id, limit))
            else:
                rows = db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,))
            return [self._job(r) for r in rows]

    @staticmethod
    def _job(row) -> dict:
        job = dict(row)
        job["params"] = json.loads(job.get("params") or "{}")
        return job

    def cancel(self, job_id: str) -> dict | None:
        with self.transaction() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            if row["status"] == "queued":
                stamp = now()
                db.execute("UPDATE jobs SET status='cancelled', cancel_requested=1, finished=? WHERE id=?",
                           (stamp, job_id))
                db.execute("UPDATE job_items SET status='cancelled', updated=? WHERE job_id=? AND status='pending'",
                           (stamp, job_id))
            elif row["status"] == "running":
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))
        return self.get(job_id)

    def counts(self) -> dict[str, int]:
        with self.connect() as db:
            return {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}

    # -- jobs (worker side) -------------------------------------------------
    def claim(self, worker: str) -> dict | None:
        with self.transaction() as db:
            row = db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            stamp = now()
            db.execute("UPDATE jobs SET status='running', worker=?, started=COALESCE(started, ?), heartbeat=?, "
                       "attempts=attempts+1 WHERE id=?", (worker, stamp, stamp, row["id"]))
        return self.get(row["id"])

    def requeue_orphans(self) -> int:
        """Return running jobs to the queue (called by the lease holder at start)."""
        with self.transaction() as db:
            stamp = now()
            cancelled = db.execute("SELECT id FROM jobs WHERE status='running' AND cancel_requested=1").fetchall()
            for row in cancelled:
                self._finish(db, row["id"], "cancelled", None, stamp)
            return db.execute("UPDATE jobs SET status='queued', worker=NULL WHERE status='running'").rowcount

    def set_checkpoint(self, job_id: str, checkpoint: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET checkpoint=?, heartbeat=? WHERE id=?", (checkpoint, now(), job_id))

    def pending_items(self, job_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT position, photo FROM job_items WHERE job_id=? "
                                                "AND status='pending' ORDER BY position", (job_id,))]

    def cancel_requested(self, job_id: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def finish_item(self, job_id: str, position: int, status: str, cache_key: str | None = None,
                    error: str | None = None) -> None:
        with self.transaction() as db:
            stamp = now()
            db.execute("UPDATE job_items SET status=?, cache_key=?, error=?, updated=? WHERE job_id=? AND position=?",
                       (status, cache_key, error, stamp, job_id, position))
            db.execute("""UPDATE jobs SET heartbeat=?,
                done=(SELECT COUNT(*) FROM job_items WHERE job_id=? AND status IN ('done','cached','error')),
                cached=(SELECT COUNT(*) FROM job_items WHERE job_id=? AND status='cached'),
                failed=(SELECT COUNT(*) FROM job_items WHERE job_id=? AND status='error') WHERE id=?""",
                       (stamp, job_id, job_id, job_id, job_id))

    def complete(self, job_id: str, status: str, error: str | None = None) -> None:
        with self.transaction() as db:
            self._finish(db, job_id, status, error, now())

    @staticmethod
    def _finish(db, job_id, status, error, stamp):
        db.execute("UPDATE jobs SET status=?, error=?, finished=? WHERE id=?", (status, error, stamp, job_id))
        if status != "done":
            db.execute("UPDATE job_items SET status='cancelled', updated=? WHERE job_id=? AND status='pending'",
                       (stamp, job_id))

    # -- activity cache -------------------------------------------------------
    def get_activity(self, cache_key: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM activity WHERE cache_key=?", (cache_key,)).fetchone()
        return self._activity(row) if row else None

    def put_activity(self, cache_key: str, **fields) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO activity VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (cache_key, fields["listing_id"], fields["position"], fields["photo"],
                        fields["photo_sha256"], fields["codec"], fields["engine_version"], fields["fingerprint"],
                        fields.get("checkpoint"), json.dumps(fields["result"]), now()))

    def get_activities(self, cache_keys) -> dict[str, dict]:
        """Results for many cache keys in one connection: {cache_key: result}."""
        keys, out = list(cache_keys), {}
        with self.connect() as db:
            for start in range(0, len(keys), 500):
                chunk = keys[start:start + 500]
                rows = db.execute(f"SELECT cache_key, result FROM activity WHERE cache_key IN "
                                  f"({','.join('?' * len(chunk))})", chunk)
                out.update({r["cache_key"]: json.loads(r["result"]) for r in rows})
        return out

    def activity_stamp(self) -> tuple[int, str | None]:
        with self.connect() as db:
            row = db.execute("SELECT COUNT(*) AS n, MAX(created) AS last FROM activity").fetchone()
        return int(row["n"]), row["last"]

    def listing_activity(self, listing_id: str, codec: str | None = None) -> list[dict]:
        """Latest result per photo (optionally of one codec), labelled stale when produced by other weights."""
        current = self.state("current_fingerprint")
        codec_filter = "AND b.codec=a.codec" if codec else ""
        with self.connect() as db:
            rows = db.execute(f"""SELECT a.* FROM activity a WHERE a.listing_id=? {"AND a.codec=?" if codec else ""}
                AND a.created = (SELECT MAX(b.created) FROM activity b WHERE b.listing_id=a.listing_id
                AND b.position=a.position {codec_filter}) ORDER BY a.position""",
                              (listing_id, codec) if codec else (listing_id,)).fetchall()
        out = []
        for row in rows:
            item = self._activity(row)
            item["stale"] = current is not None and item["fingerprint"] != current
            out.append(item)
        return out

    @staticmethod
    def _activity(row) -> dict:
        item = dict(row)
        item["result"] = json.loads(item["result"])
        return item

    # -- CLIP image embeddings, addressed by photo content ------------------------
    def put_embedding(self, photo_sha: str, model: str, revision: str, vector) -> None:
        import numpy as np
        data = np.asarray(vector, dtype="<f4")
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO photo_embeddings VALUES (?,?,?,?,?,?)",
                       (photo_sha, model, revision, int(data.size), data.tobytes(), now()))

    def get_embedding(self, photo_sha: str, model: str, revision: str):
        import numpy as np
        with self.connect() as db:
            row = db.execute("SELECT vector FROM photo_embeddings WHERE photo_sha256=? AND model=? AND revision=?",
                             (photo_sha, model, revision)).fetchone()
        return np.frombuffer(row["vector"], dtype="<f4") if row else None

    def get_embeddings(self, model: str, revision: str) -> dict:
        """Every stored embedding of one model revision: {photo_sha256: vector}."""
        import numpy as np
        with self.connect() as db:
            rows = db.execute("SELECT photo_sha256, vector FROM photo_embeddings WHERE model=? AND revision=?",
                              (model, revision)).fetchall()
        return {r["photo_sha256"]: np.frombuffer(r["vector"], dtype="<f4") for r in rows}

    def embedded(self, model: str, revision: str) -> set[str]:
        with self.connect() as db:
            return {r[0] for r in db.execute("SELECT photo_sha256 FROM photo_embeddings WHERE model=? AND revision=?",
                                             (model, revision))}

    def get_center(self, model: str, revision: str):
        """Frozen mean embedding as (vector, photo count), or None."""
        import numpy as np
        with self.connect() as db:
            row = db.execute("SELECT vector, count FROM embedding_centers WHERE model=? AND revision=?",
                             (model, revision)).fetchone()
        return (np.frombuffer(row["vector"], dtype="<f4"), row["count"]) if row else None

    def freeze_center(self, model: str, revision: str, refresh: bool = False,
                      min_count: int = MIN_CENTER_PHOTOS):
        """Mean of every stored unit embedding, frozen once so results stay comparable.

        An existing centre is kept unless `refresh`; replacing it changes every
        cyborg stimulus, so earlier results stop matching.
        """
        import numpy as np
        if not refresh and (found := self.get_center(model, revision)) is not None:
            return found
        with self.connect() as db:
            rows = db.execute("SELECT vector FROM photo_embeddings WHERE model=? AND revision=?",
                              (model, revision)).fetchall()
        if len(rows) < min_count:
            raise LookupError(f"A CLIP centre needs at least {min_count} embedded photos; {len(rows)} stored.")
        vectors = np.stack([np.frombuffer(r["vector"], dtype="<f4").astype(np.float64) for r in rows])
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        mean = vectors.mean(axis=0).astype("<f4")
        with self.connect() as db:
            # Without `refresh`, a centre frozen concurrently by another process wins.
            db.execute(f"INSERT OR {'REPLACE' if refresh else 'IGNORE'} INTO embedding_centers VALUES (?,?,?,?,?,?)",
                       (model, revision, int(mean.size), len(rows), mean.tobytes(), now()))
        return self.get_center(model, revision)

    # -- engine state and the single-worker lease -------------------------------
    def state(self, key: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM engine_state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO engine_state VALUES (?,?)", (key, value))

    @staticmethod
    def _lease_expired(lease: dict) -> bool:
        if time.time() - lease["heartbeat"] > LEASE_SECONDS:
            return True
        return lease.get("host") == socket.gethostname() and not pid_alive(int(lease.get("pid", 0)))

    def acquire_lease(self, worker: str, info: dict | None = None) -> bool:
        with self.transaction() as db:
            row = db.execute("SELECT value FROM engine_state WHERE key='worker'").fetchone()
            if row:
                lease = json.loads(row["value"])
                if lease["id"] != worker and not self._lease_expired(lease):
                    return False
            lease = {"id": worker, "pid": os.getpid(), "host": socket.gethostname(),
                     "heartbeat": time.time(), "started": now(), **(info or {})}
            db.execute("INSERT OR REPLACE INTO engine_state VALUES ('worker', ?)", (json.dumps(lease),))
        return True

    def renew_lease(self, worker: str, **info) -> bool:
        with self.transaction() as db:
            row = db.execute("SELECT value FROM engine_state WHERE key='worker'").fetchone()
            lease = json.loads(row["value"]) if row else None
            if not lease or lease["id"] != worker:
                return False
            lease.update(info, heartbeat=time.time())
            db.execute("UPDATE engine_state SET value=? WHERE key='worker'", (json.dumps(lease),))
        return True

    def release_lease(self, worker: str) -> None:
        with self.transaction() as db:
            row = db.execute("SELECT value FROM engine_state WHERE key='worker'").fetchone()
            if row and json.loads(row["value"])["id"] == worker:
                db.execute("DELETE FROM engine_state WHERE key='worker'")

    def worker_status(self) -> dict:
        raw = self.state("worker")
        if not raw:
            return {"alive": False}
        lease = json.loads(raw)
        age = time.time() - lease["heartbeat"]
        return {**lease, "alive": not self._lease_expired(lease), "heartbeat_age_s": round(age, 1)}
