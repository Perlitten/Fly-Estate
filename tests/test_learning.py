"""Feedback transactions, cancellation, restart and evaluation leakage guards."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from server import learning, evaluation
from server.storage import Store
from server.jobs import Queue
from server.checkpoints import CheckpointStore
from server.worker import Worker
from server.gallery import PhotoHashes
from server.engine.olfactory import OlfactoryMBEngine, Params
from tests.synthetic import make_data
from server.brain import Brain


class SmallBrain:
    """Only replace the large rate graph; test the actual evaluator/readout."""
    pool = None
    fit = staticmethod(Brain.fit)

    def features(self, listings, settings):
        return np.array([[l["size"], l["price"]] for l in listings]), []


class MemoryChoices(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data/state.sqlite")
        self.settings = {**self.store.get()["settings"], "mode": "pure"}
        self.store.settings(self.settings)
        photo = "/data/photos/one.jpg"
        path = self.root / photo.lstrip("/")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"synthetic photo content")
        self.listing = {"id": "a", "title": "Test apartment", "photos": [photo],
                        "price": 1800, "size": 120, "coords": [34.71, 33.05],
                        "balcony": True, "balcony_size": 30, "balcony_covered": True,
                        "vision": {"per_photo": [{"retina": [.9] * 192, "attributes": {}}]}}
        self.store.listing(self.listing)
        self.queue = Queue(self.root / "engine.sqlite")
        self.checkpoints = CheckpointStore(self.queue, self.root / "checkpoints")
        self.engine = OlfactoryMBEngine(Params(epi_ms=100, washout_ms=20), data=make_data(classes=22))
        self.worker = Worker(self.queue, self.checkpoints, self.engine,
                             lambda _: self.listing, self.root)
        self.worker.start()
        self.base = self.engine.fingerprint()

    def tearDown(self):
        self.worker.close()
        self.temp.cleanup()

    def vote(self, value):
        context = learning.snapshot([self.listing], self.settings, ["a"] if value == 1 else [],
                                    PhotoHashes(self.root), self.queue)
        return self.store.rating("a", value, context=context)

    def test_duplicate_vote_does_not_repeat_dopamine(self):
        id = self.vote(1)
        self.assertEqual(id, self.vote(1))
        before = self.engine.net.graph.data.copy()
        self.assertTrue(self.worker.memory.run_once())
        learned = self.engine.fingerprint()
        self.assertNotEqual(learned, self.base)
        changed = set(np.flatnonzero(before != self.engine.net.graph.data))
        self.assertTrue(changed <= set(self.engine.plastic))
        self.assertFalse(self.worker.memory.run_once())
        self.assertEqual(learned, self.engine.fingerprint())
        self.assertEqual(len(learning.events(self.store)), 1)

    def test_removing_vote_restores_base_and_restart_keeps_it(self):
        self.vote(1)
        self.worker.memory.run_once()
        self.vote(None)
        self.worker.memory.run_once()
        self.assertEqual(self.engine.fingerprint(), self.base)
        self.assertNotIn("a", self.store.get()["ratings"])
        self.worker.close()
        restored = OlfactoryMBEngine(Params(epi_ms=100, washout_ms=20), data=make_data(classes=22))
        self.worker = Worker(self.queue, self.checkpoints, restored, lambda _: self.listing, self.root)
        self.worker.start()
        self.assertEqual(restored.fingerprint(), self.base)
        self.assertFalse(self.worker.memory.run_once())

    def test_failed_publish_keeps_old_memory_and_retry_is_safe(self):
        self.vote(1)
        old = self.checkpoints.current()["hash"]
        with patch.object(self.checkpoints, "save", side_effect=OSError("disk full")):
            self.worker.memory.run_once()
        self.assertEqual(self.engine.fingerprint(), self.base)
        self.assertEqual(self.checkpoints.current()["hash"], old)
        self.assertEqual(int(self.queue.state("memory_revision") or 0), 0)
        self.queue.set_state("memory_last_attempt", "0")
        self.worker.memory.run_once()
        self.assertNotEqual(self.engine.fingerprint(), self.base)
        self.assertFalse(self.worker.memory.run_once())

    def test_duplicate_photo_does_not_double_gallery_dose(self):
        self.listing["photos"] *= 2
        self.listing["vision"]["per_photo"] *= 2
        self.vote(1)
        self.worker.memory.run_once()
        run = learning.status(self.store, self.queue)["runs"][0]
        self.assertEqual(run["episodes"], 1)
        weights = self.engine.net.graph.data[self.engine.plastic]
        self.assertTrue(np.all(weights >= self.engine.base_plastic * .9 - 1e-9))

    def test_negative_and_neutral_do_not_apply_positive_reward(self):
        for value in (-1, 0):
            self.vote(value)
            self.worker.memory.run_once()
            self.assertEqual(self.engine.fingerprint(), self.base)

    def test_pair_order_is_idempotent(self):
        context = learning.snapshot([self.listing], self.settings, ["a"], PhotoHashes(self.root), self.queue)
        first = self.store.compare("a", "b", 1, context)
        second = self.store.compare("b", "a", -1, context)
        self.assertEqual(first, second)

    def test_refresh_failure_cannot_roll_back_published_memory(self):
        self.vote(1)
        with patch.object(self.queue, "enqueue", side_effect=OSError("cache unavailable")):
            self.worker.memory.run_once()
        self.assertNotEqual(self.engine.fingerprint(), self.base)
        self.assertEqual(self.queue.state("current_fingerprint"), self.engine.fingerprint())
        self.assertEqual(learning.status(self.store, self.queue)["runs"][0]["status"], "done")

    def test_changed_photos_fail_before_embedding_cache_write(self):
        self.vote(1)
        (self.root / self.listing["photos"][0].lstrip("/")).write_bytes(b"changed gallery")
        with patch.object(self.queue, "put_embedding") as cache:
            self.worker.memory.run_once()
        cache.assert_not_called()
        self.assertEqual(self.engine.fingerprint(), self.base)
        self.assertEqual(learning.status(self.store, self.queue)["runs"][0]["status"], "error")

    def test_clearing_choice_does_not_require_its_missing_photo(self):
        self.vote(1)
        self.worker.memory.run_once()
        (self.root / self.listing["photos"][0].lstrip("/")).unlink()
        self.vote(None)
        self.worker.memory.run_once()
        self.assertEqual(self.engine.fingerprint(), self.base)
        self.assertEqual(learning.status(self.store, self.queue)["runs"][0]["status"], "done")

    def test_refreshed_gallery_replaces_old_choice_without_extra_dose(self):
        first = self.vote(1)
        self.worker.memory.run_once()
        (self.root / self.listing["photos"][0].lstrip("/")).write_bytes(b"new photo content")
        refreshed = self.vote(1)
        self.assertNotEqual(first, refreshed)
        self.assertEqual(refreshed, self.vote(1))
        self.worker.memory.run_once()
        weights = self.engine.net.graph.data[self.engine.plastic]
        self.assertTrue(np.all(weights >= self.engine.base_plastic * .9 - 1e-9))

    def test_memory_triggered_inference_backfills_legacy_clip_embeddings(self):
        from server.vision import MODEL_ID, REVISION
        self.vote(1)
        self.worker.memory.run_once()
        self.worker.run_once()  # finish the automatically queued pure job
        baseline = self.engine.fingerprint()
        center = np.zeros(512, dtype=np.float32)
        center[0] = 1
        self.queue.put_embedding("centre-anchor", MODEL_ID, REVISION, center)
        self.queue.freeze_center(MODEL_ID, REVISION, min_count=1)
        vector = np.zeros(512, dtype=np.float32)
        vector[1] = 1
        job, _ = self.queue.enqueue("a", self.listing["photos"], learning.job_params({**self.settings, "mode": "cyborg"}))
        with patch("server.learning.Vision") as encoder:
            encoder.return_value.embed.return_value = [vector]
            self.worker.run_once()
        encoder.return_value.embed.assert_called_once()
        self.assertEqual(self.queue.get(job["id"])["failed"], 0)
        self.assertEqual(self.queue.get(job["id"])["status"], "done")
        self.assertEqual(self.engine.fingerprint(), baseline)

    def test_evaluation_restores_live_memory_on_failure(self):
        self.vote(1)
        self.worker.memory.run_once()
        fingerprint = self.engine.fingerprint()
        checkpoint = self.worker.checkpoint
        # A malformed frozen evaluation must fail without publishing its
        # experimental weights or losing the user's saved memory.
        frozen = {"context": {"listings": []}, "partition": {}, "settings": {}}
        with self.queue.connect() as db:
            db.execute("INSERT INTO learning_evaluations(id,status,snapshot,created) VALUES (?,?,?,?)",
                       ("failure", "queued", json.dumps(frozen), "now"))
        with patch("server.evaluation.Brain", SmallBrain):
            self.assertTrue(evaluation.run_once(self.worker))
        self.assertEqual(fingerprint, self.engine.fingerprint())
        self.assertEqual(checkpoint, self.worker.checkpoint)
        self.assertEqual(checkpoint, self.queue.state("current_checkpoint"))

    def test_actual_holdout_reinforcement_excludes_test_choices_and_preserves_memory(self):
        members = [self.listing]
        for i in range(1, 9):
            listing = {**self.listing, "id": f"b{i}", "size": 70+i*10, "price": 1400+i*100,
                       "photos": [f"/data/photos/{i}.jpg"], "city": "Limassol", "bedrooms": 2, "parking": "covered"}
            (self.root / listing["photos"][0].lstrip("/")).write_bytes(f"unique {i}".encode())
            self.store.listing(listing)
            members.append(listing)
        self.listing.update(city="Limassol", bedrooms=2, parking="covered")
        self.store.listing(self.listing)
        hashes = PhotoHashes(self.root)
        for listing in members[1:]:
            context = learning.snapshot([self.listing, listing], self.settings, [listing["id"]], hashes, self.queue)
            self.store.compare("a", listing["id"], -1, context)
        self.worker.memory.run_once()
        fingerprint, checkpoint = self.engine.fingerprint(), self.worker.checkpoint
        key = evaluation.enqueue(self.queue, self.store, hashes)
        with self.queue.connect() as db:
            frozen = json.loads(db.execute("SELECT snapshot FROM learning_evaluations WHERE id=?", (key,)).fetchone()[0])
        held = set(frozen["partition"]["test_ids"])
        self.assertTrue(held)
        for event in frozen["events"]:
            self.assertFalse(held & {l["id"] for l in event["payload"]["listings"]})
        with patch("server.evaluation.Brain", SmallBrain), patch.object(self.worker.memory, "train", wraps=self.worker.memory.train) as train:
            evaluation.run_once(self.worker)
        self.assertEqual(train.call_args.args[0], frozen["events"])
        self.assertEqual(fingerprint, self.engine.fingerprint())
        self.assertEqual(checkpoint, self.queue.state("current_checkpoint"))
        report = evaluation.latest(self.queue)
        self.assertEqual(report["status"], "done", report["error"])
        self.assertEqual(report["result"]["photo_coverage"], 1.0)


class HeldOutChoices(unittest.TestCase):
    def test_test_feature_scale_does_not_fit_training_normalization(self):
        listings = [{"id": "a"}, {"id": "b"}, {"id": "held"}]
        ratings = {"a": 1, "b": -1}
        first, _ = Brain.fit(np.array([[1.], [2.], [3.]]), listings, ratings, [], ["a", "b"])
        second, _ = Brain.fit(np.array([[1.], [2.], [1e9]]), listings, ratings, [], ["a", "b"])
        np.testing.assert_array_equal(first[:2], second[:2])

    def test_duplicate_photos_and_touching_pairs_never_cross_training_boundary(self):
        listings = [{"id": str(i), "photos": [str(i)]} for i in range(10)]
        listings[9]["photos"] = ["8"]
        pairs = [{"a": "0", "b": str(i), "choice": 1} for i in range(1, 10)]
        split = evaluation.split(listings, {}, pairs, lambda p: p)
        train, test = set(split["train_ids"]), set(split["test_ids"])
        self.assertFalse(train & test)
        self.assertEqual("8" in test, "9" in test)
        for p in split["train_pairs"]:
            self.assertFalse({p["a"], p["b"]} & test)
        self.assertEqual(split, evaluation.split(listings, {}, pairs, lambda p: p))

    def test_small_sample_uncertainty_and_ties_are_explicit(self):
        result = evaluation.metrics({"a": .8, "b": .2}, {},
                                    [{"a": "a", "b": "b", "choice": 1}])
        self.assertEqual(result["pairwise_accuracy"], 1)
        self.assertLess(result["wilson_95"][0], .3)
        self.assertIsNone(result["auc"])
        empty = evaluation.metrics({"a": .5, "b": .5}, {},
                                   [{"a": "a", "b": "b", "choice": 0}])
        self.assertIsNone(empty["pairwise_accuracy"])
        self.assertEqual(empty["tie_agreement"], 1)
