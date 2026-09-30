"""Durable queue, single-worker lease, cancellation, crash recovery and the result cache."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from server.checkpoints import CheckpointStore
from server.engine.base import Stimulus
from server.engine.olfactory import OlfactoryMBEngine, Params
from server.engine import stimuli
from server.gallery import PhotoHashes, gallery, job_params, current_results
from server.jobs import Queue
from server.vision import MODEL_ID, REVISION
from server.worker import Worker
from tests.synthetic import make_data

BRIEF = {"mode": "pure", "budget": 1800, "ceiling": 2800, "ideal": [34.71, 33.05], "radius": 3}
PURE = job_params(BRIEF)
CYBORG = job_params({**BRIEF, "mode": "cyborg"})


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fly-estate-test-"))
        self.queue = Queue(self.dir / "engine.sqlite")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class QueueBehaviour(Temp):
    def test_enqueue_is_idempotent_while_active(self):
        job, created = self.queue.enqueue("L1", ["/a.jpg", "/b.jpg"], PURE)
        again, created_again = self.queue.enqueue("L1", ["/a.jpg", "/b.jpg"], PURE)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(job["id"], again["id"])
        self.assertEqual(job["params"], PURE)
        self.assertEqual([i["status"] for i in job["items"]], ["pending", "pending"])
        other, created_other = self.queue.enqueue("L1", ["/a.jpg", "/b.jpg"], CYBORG)
        self.assertTrue(created_other)
        self.assertNotEqual(other["id"], job["id"])

    def test_r2_database_gains_params_column(self):
        import sqlite3
        path = self.dir / "old.sqlite"
        db = sqlite3.connect(path)
        db.executescript(stimuli_free_r2_schema())
        db.execute("INSERT INTO jobs (id, listing_id, status, total, created) VALUES ('j', 'L', 'done', 1, 'x')")
        db.commit(); db.close()
        self.assertEqual(Queue(path).get("j", items=False)["params"], {})

    def test_cancel_queued_and_running(self):
        queued, _ = self.queue.enqueue("L1", ["/a.jpg"])
        self.assertEqual(self.queue.cancel(queued["id"])["status"], "cancelled")
        running, _ = self.queue.enqueue("L2", ["/a.jpg"])
        self.queue.claim("w1")
        job = self.queue.cancel(running["id"])
        self.assertEqual((job["status"], job["cancel_requested"]), ("running", 1))
        self.assertIsNone(self.queue.cancel("missing"))

    def test_requeue_after_crash_keeps_finished_photos(self):
        job, _ = self.queue.enqueue("L1", ["/a.jpg", "/b.jpg", "/c.jpg"])
        self.queue.claim("w1")
        self.queue.finish_item(job["id"], 0, "done", "k0")
        # The process dies here. A new queue object stands for a restarted process.
        restarted = Queue(self.dir / "engine.sqlite")
        self.assertEqual(restarted.requeue_orphans(), 1)
        again = restarted.claim("w2")
        self.assertEqual((again["id"], again["attempts"], again["done"]), (job["id"], 2, 1))
        self.assertEqual([i["position"] for i in restarted.pending_items(job["id"])], [1, 2])

    def test_single_worker_lease(self):
        self.assertTrue(self.queue.acquire_lease("w1"))
        self.assertFalse(self.queue.acquire_lease("w2"))  # same live process holds it
        self.queue.release_lease("w1")
        self.assertTrue(self.queue.acquire_lease("w2"))
        lease = json.loads(self.queue.state("worker"))
        lease["pid"] = 999_999_999  # a dead process on this host
        self.queue.set_state("worker", json.dumps(lease))
        self.assertTrue(self.queue.acquire_lease("w3"))
        self.assertTrue(self.queue.worker_status()["alive"])


class WorkerEndToEnd(Temp):
    def setUp(self):
        super().setUp()
        self.photos = []
        for k in range(3):
            path = self.dir / "photos" / f"p{k}.jpg"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(f"photo-{k}".encode())
            self.photos.append(f"/photos/p{k}.jpg")
        per_photo = [{"retina": [(k + 1) / 4] * 192} for k in range(3)]
        self.listings = {"L1": {"id": "L1", "photos": self.photos, "vision": {"per_photo": per_photo},
                                "price": 1400, "size": 60, "coords": [34.70, 33.04], "coord_kind": "area",
                                "balcony": True, "balcony_size": None, "balcony_covered": True}}
        self.checkpoints = CheckpointStore(self.queue, self.dir / "checkpoints")
        self.hashes = PhotoHashes(self.dir)

    def worker(self, name):
        engine = OlfactoryMBEngine(Params(epi_ms=50, washout_ms=10), data=make_data(classes=stimuli.CHANNELS))
        w = Worker(self.queue, self.checkpoints, engine, self.listings.get, root=self.dir, worker_id=name)
        w.start()
        return w

    def test_shared_photo_cache_keeps_every_position_and_listing(self):
        listing = self.listings["L1"]
        listing["photos"] = [self.photos[0], self.photos[0]]
        first = listing["vision"]["per_photo"][0]
        listing["vision"] = {"per_photo": [first, first]}
        self.listings["L2"] = {**listing, "id": "L2", "photos": [self.photos[0]], "vision": {"per_photo": [first]}}
        w = self.worker("duplicates")
        for id in ("L1", "L2"):
            self.queue.enqueue(id, self.listings[id]["photos"], PURE)
            w.run_once()
        results = current_results(self.queue, list(self.listings.values()), BRIEF, self.hashes)
        self.assertEqual(set(results["L1"]), {0, 1})
        self.assertEqual(set(results["L2"]), {0})
        self.assertEqual(results["L1"][0], results["L1"][1])
        self.assertEqual(results["L1"][0], results["L2"][0])
        w.close()

    def test_job_runs_every_photo_then_hits_cache(self):
        w = self.worker("w1")
        job, _ = self.queue.enqueue("L1", self.photos, PURE)
        self.assertTrue(w.run_once())
        done = self.queue.get(job["id"])
        self.assertEqual((done["status"], done["done"], done["cached"]), ("done", 3, 0))
        activity = self.queue.listing_activity("L1")
        self.assertEqual(len(activity), 3)
        self.assertFalse(any(a["stale"] for a in activity))
        self.assertEqual(activity[0]["codec"], "photo-pure-v1")
        provenance = activity[0]["result"]["provenance"]
        self.assertEqual(provenance["context"]["balcony_size"]["value"], None)
        self.assertEqual(provenance["photo_signals"], [0.25] * 16)
        again, _ = self.queue.enqueue("L1", self.photos, PURE)
        w.run_once()
        self.assertEqual(self.queue.get(again["id"])["cached"], 3)
        w.close()

    def test_restart_resumes_job_and_restores_checkpoint(self):
        w = self.worker("w1")
        base = self.checkpoints.current()
        job, _ = self.queue.enqueue("L1", self.photos, PURE)
        claimed = self.queue.claim("w1")
        w._photo(claimed, self.queue.pending_items(job["id"])[0], self.listings["L1"],
                 self.listings["L1"]["vision"]["per_photo"], w.engine.channels())
        # Simulated crash: the lease holder disappears without cleanup.
        self.queue.set_state("worker", json.dumps({**json.loads(self.queue.state("worker")), "heartbeat": 0}))
        w2 = self.worker("w2")
        self.assertEqual(w2.checkpoint, base["hash"])
        self.assertEqual(self.queue.get(job["id"])["status"], "queued")
        w2.run_once()
        finished = self.queue.get(job["id"])
        self.assertEqual((finished["status"], finished["done"], finished["attempts"]), ("done", 3, 2))
        w2.close()

    def test_cancel_while_running_stops_before_next_photo(self):
        w = self.worker("w1")
        job, _ = self.queue.enqueue("L1", self.photos, PURE)
        original = w._photo

        def cancel_after_first(job_row, item, *args):
            original(job_row, item, *args)
            self.queue.cancel(job["id"])
        w._photo = cancel_after_first
        w.run_once()
        stopped = self.queue.get(job["id"])
        self.assertEqual(stopped["status"], "cancelled")
        self.assertEqual([i["status"] for i in stopped["items"]], ["done", "cancelled", "cancelled"])
        w.close()

    def test_new_weights_mark_old_activity_stale(self):
        w = self.worker("w1")
        self.queue.enqueue("L1", self.photos, PURE)
        w.run_once()
        w.engine.run_episode(Stimulus("test", (("ORN_T0", 500.0),)), reward=True, seed=0)
        self.queue.set_state("current_fingerprint", w.engine.fingerprint())
        self.assertTrue(all(a["stale"] for a in self.queue.listing_activity("L1")))
        w.close()

    def test_missing_photo_file_fails_item_not_job(self):
        w = self.worker("w1")
        (self.dir / "photos" / "p1.jpg").unlink()
        job, _ = self.queue.enqueue("L1", self.photos, PURE)
        w.run_once()
        finished = self.queue.get(job["id"])
        self.assertEqual((finished["status"], finished["failed"]), ("done", 1))
        self.assertEqual(finished["items"][1]["status"], "error")
        w.close()


    def test_cyborg_uses_stored_embeddings_and_reports_missing_ones(self):
        w = self.worker("w1")
        for k in (0, 2):
            vector = [1.0 if i == k else 0.0 for i in range(stimuli.EMBEDDING_DIM)]
            self.queue.put_embedding(self.hashes(self.photos[k]), MODEL_ID, REVISION, vector)
        job, _ = self.queue.enqueue("L1", self.photos, CYBORG)
        w.run_once()
        items = self.queue.get(job["id"])["items"]
        self.assertTrue(all("centre" in items[k]["error"] for k in (0, 2)))
        self.queue.freeze_center(MODEL_ID, REVISION, min_count=2)
        job, _ = self.queue.enqueue("L1", self.photos, CYBORG)
        w.run_once()
        finished = self.queue.get(job["id"])
        self.assertEqual([i["status"] for i in finished["items"]], ["done", "error", "done"])
        self.assertIn("CLIP embedding", finished["items"][1]["error"])
        self.assertEqual({a["codec"] for a in self.queue.listing_activity("L1")}, {"photo-cyborg-v2"})
        w.close()

    def test_clip_centre_is_frozen_until_refreshed(self):
        def put(k):
            self.queue.put_embedding(f"sha{k}", MODEL_ID, REVISION,
                                     [1.0 if i == k else 0.0 for i in range(stimuli.EMBEDDING_DIM)])
        put(0)
        with self.assertRaises(LookupError):
            self.queue.freeze_center(MODEL_ID, REVISION, min_count=2)
        put(1)
        vector, photos = self.queue.freeze_center(MODEL_ID, REVISION, min_count=2)
        self.assertEqual((photos, vector[0], vector[1]), (2, 0.5, 0.5))
        put(2)
        self.assertEqual(self.queue.freeze_center(MODEL_ID, REVISION, min_count=2)[1], 2)
        vector, photos = self.queue.freeze_center(MODEL_ID, REVISION, refresh=True, min_count=2)
        self.assertEqual(photos, 3)
        self.assertAlmostEqual(float(vector[2]), 1 / 3, places=6)

    def test_job_without_params_fails_clearly(self):
        w = self.worker("w1")
        job, _ = self.queue.enqueue("L1", self.photos)
        w.run_once()
        finished = self.queue.get(job["id"])
        self.assertEqual(finished["status"], "error")
        self.assertIn("before R3", finished["error"])
        w.close()

    def test_gallery_tracks_queue_weights_and_brief(self):
        w = self.worker("w1")
        listing = self.listings["L1"]
        view = gallery(self.queue, listing, BRIEF, self.hashes)
        self.assertEqual(view["counts"], {"missing": 3})
        self.assertEqual(len(view["photos"][0]["signals"]), 16)
        self.queue.enqueue("L1", self.photos, PURE)
        self.queue.claim("w1")
        self.assertEqual([p["status"] for p in gallery(self.queue, listing, BRIEF, self.hashes)["photos"]],
                         ["running", "queued", "queued"])
        self.queue.requeue_orphans()
        w.run_once()
        view = gallery(self.queue, listing, BRIEF, self.hashes)
        self.assertEqual(view["counts"], {"ready": 3})
        self.assertGreaterEqual(view["photos"][0]["result"]["total_spikes"], 0)
        # Another brief changes the listing channels: old results remain visible but stale.
        moved = gallery(self.queue, listing, {**BRIEF, "ideal": [34.80, 33.20]}, self.hashes)
        self.assertEqual(moved["counts"], {"stale": 3})
        # New weights also make every result stale.
        w.engine.run_episode(stimuli.encode("pure", listing["vision"]["per_photo"][0], listing, PURE["brief"],
                                            w.engine.channels())[0], reward=True, seed=0)
        self.queue.set_state("current_fingerprint", w.engine.fingerprint())
        self.assertEqual(gallery(self.queue, listing, BRIEF, self.hashes)["counts"], {"stale": 3})
        # Cyborg without embeddings or a centre: computed when the model is run.
        self.assertEqual(gallery(self.queue, listing, {**BRIEF, "mode": "cyborg"}, self.hashes)["counts"],
                         {"missing": 3})
        w.close()


def stimuli_free_r2_schema() -> str:
    """The R2 `jobs` table, before `params` existed."""
    return """CREATE TABLE jobs (
    id TEXT PRIMARY KEY, listing_id TEXT NOT NULL, status TEXT NOT NULL,
    total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0, worker TEXT, checkpoint TEXT, error TEXT,
    created TEXT NOT NULL, started TEXT, heartbeat TEXT, finished TEXT);"""


class CheckpointFiles(Temp):
    def test_atomic_content_addressed_roundtrip(self):
        store = CheckpointStore(self.queue, self.dir / "checkpoints")
        engine = OlfactoryMBEngine(Params(epi_ms=50, washout_ms=10), data=make_data())
        digest = store.save(engine.checkpoint(), label="base")
        self.assertEqual(store.save(engine.checkpoint(), label="base"), digest)
        self.assertEqual(store.current()["hash"], digest)
        self.assertEqual(list((self.dir / "checkpoints").glob("*.tmp")), [])
        path = self.dir / "checkpoints" / f"{digest}.npz"
        path.write_bytes(path.read_bytes()[:-1] + b"x")
        with self.assertRaises(ValueError):
            store.load(digest)


if __name__ == "__main__":
    unittest.main()
