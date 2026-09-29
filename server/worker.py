"""Single persistent engine worker: `python -m server.worker`.

Holds the engine in memory, takes jobs from the durable queue one at a time
and simulates every photo of a listing with the job's codec (Pure/Cyborg)
and brief snapshot. Results are cached by photo content, stimulus, codec
settings, engine version and weight fingerprint, so repeated jobs cost
nothing until the weights, the codec or the brief change.
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

from .checkpoints import CheckpointStore
from .engine import stimuli
from .engine.base import SimulationEngine
from .jobs import ROOT, Queue
from .vision import MODEL_ID, REVISION

log = logging.getLogger("fly-estate.worker")


def listing_loader(path: Path = ROOT / "data/state.sqlite") -> Callable[[str], dict | None]:
    def load(listing_id: str) -> dict | None:
        db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            row = db.execute("SELECT data FROM listings WHERE id=?", (listing_id,)).fetchone()
        finally:
            db.close()
        return json.loads(row[0]) if row else None
    return load


class Worker:
    def __init__(self, queue: Queue, checkpoints: CheckpointStore, engine: SimulationEngine,
                 load_listing: Callable[[str], dict | None], root: Path = ROOT, worker_id: str | None = None):
        self.queue, self.checkpoints, self.engine = queue, checkpoints, engine
        self.load_listing, self.root = load_listing, root
        self.id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.checkpoint: str | None = None
        self.stopping = False

    def start(self) -> None:
        if not self.queue.acquire_lease(self.id, {"engine": self.engine.version}):
            raise RuntimeError("Another engine worker holds the lease; only one worker may run.")
        current = self.checkpoints.current()
        if current and current["version"] == self.engine.version:
            try:
                self.engine.restore(self.checkpoints.load(current["hash"]))
                self.checkpoint = current["hash"]
            except (ValueError, OSError) as error:
                log.warning("Current checkpoint not restored (%s); starting from base weights.", error)
        if self.checkpoint is None:
            self.checkpoint = self.checkpoints.save(self.engine.checkpoint(), label="base")
        self.queue.set_state("current_fingerprint", self.engine.fingerprint())
        self.queue.set_state("engine_version", self.engine.version)
        self.queue.set_state("channels", json.dumps(self.engine.channels()))
        self.queue.set_state("live_replay", "null")
        requeued = self.queue.requeue_orphans()
        if requeued:
            log.info("Requeued %d interrupted job(s).", requeued)

    def close(self) -> None:
        self.queue.release_lease(self.id)

    def heartbeat(self, **info) -> None:
        if not self.queue.renew_lease(self.id, **info):
            raise RuntimeError("Worker lease lost.")

    def run_once(self) -> bool:
        self.heartbeat(job=None)
        job = self.queue.claim(self.id)
        if not job:
            return False
        self.process(job)
        return True

    def serve(self, poll: float = 1.0) -> None:
        while not self.stopping:
            if not self.run_once():
                time.sleep(poll)

    def process(self, job: dict) -> None:
        job_id = job["id"]
        self.queue.set_checkpoint(job_id, self.checkpoint)
        try:
            listing = self.load_listing(job["listing_id"])
            if not listing:
                raise LookupError("Apartment not found.")
            params = job.get("params") or {}
            if params.get("mode") not in stimuli.CODECS or not params.get("brief"):
                raise ValueError("This job has no codec or brief (queued before R3); run the listing again.")
            per_photo = (listing.get("vision") or {}).get("per_photo") or []
            channels = self.engine.channels()
            for item in self.queue.pending_items(job_id):
                if self.stopping:
                    return  # the job stays running and is requeued at the next start
                if self.queue.cancel_requested(job_id):
                    self.queue.complete(job_id, "cancelled")
                    return
                self.heartbeat(job=job_id)
                self._photo(job, item, listing, per_photo, channels)
            final = self.queue.get(job_id, items=False)
            ok = final["done"] - final["failed"]
            self.queue.complete(job_id, "done" if ok else "error",
                                None if ok else "No photo could be simulated.")
        except Exception as error:
            log.exception("Simulation job %s failed", job_id)
            self.queue.complete(job_id, "error", str(error))
        finally:
            self.queue.set_state("live_replay", "null")

    def _photo(self, job: dict, item: dict, listing: dict, per_photo: list, channels: list[str]) -> None:
        position = item["position"]
        mode, brief = job["params"]["mode"], job["params"]["brief"]
        try:
            if position >= len(per_photo):
                raise LookupError("This photo has no encoder signals yet; import the listing again.")
            path = self.root / item["photo"].lstrip("/")
            photo_sha = stimuli.file_sha256(path)
            embedding = center = None
            if mode == "cyborg":
                embedding = self.queue.get_embedding(photo_sha, MODEL_ID, REVISION)
                frozen = self.queue.get_center(MODEL_ID, REVISION)
                center = stimuli.Center.of(*frozen) if frozen else None
            stimulus, provenance = stimuli.encode(mode, per_photo[position], listing, brief, channels,
                                                  embedding, center)
            key = stimuli.cache_key(photo_sha, stimulus, mode, self.engine.version, self.engine.fingerprint(), center)
            cached = self.queue.get_activity(key)
            if cached and cached["result"].get("replay"):
                self.queue.finish_item(job["id"], position, "cached", key)
                return

            def publish(trace):
                self.queue.set_state("live_replay", json.dumps({"job_id": job["id"],
                    "listing_id": listing["id"], "position": position, "params": job["params"],
                    "fingerprint": self.engine.fingerprint(), "trace": trace}))

            result = self.engine.run_visual_episode(stimulus, seed=int(key[:8], 16), on_progress=publish)
            self.queue.put_activity(key, listing_id=job["listing_id"], position=position, photo=item["photo"],
                                    photo_sha256=photo_sha, codec=stimulus.codec, engine_version=self.engine.version,
                                    fingerprint=self.engine.fingerprint(), checkpoint=self.checkpoint,
                                    result={**result.to_json(), "stimulus": [list(r) for r in stimulus.rates_hz],
                                            "provenance": provenance})
            self.queue.finish_item(job["id"], position, "done", key)
        except Exception as error:
            log.warning("Photo %s of job %s failed: %s", position, job["id"], error)
            self.queue.finish_item(job["id"], position, "error", error=str(error))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fly Estate engine worker")
    parser.add_argument("--once", action="store_true", help="process queued jobs, then exit")
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[worker] %(message)s")
    from .engine.olfactory import OlfactoryMBEngine
    try:
        engine = OlfactoryMBEngine()
    except FileNotFoundError as error:
        log.error("%s", error)
        return 2
    queue = Queue()
    worker = Worker(queue, CheckpointStore(queue), engine, listing_loader())
    try:
        worker.start()
    except RuntimeError as error:
        log.error("%s", error)
        return 3

    def stop(*_):
        worker.stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("%s ready: %s, %d neurons, checkpoint %s", worker.id, engine.version, engine.net.n, worker.checkpoint[:12])
    try:
        if args.once:
            while worker.run_once() and not worker.stopping:
                pass
        else:
            worker.serve(args.poll)
    finally:
        worker.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
