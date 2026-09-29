"""Engine contract: reinforcement scope, determinism and checkpoint restore."""
import unittest

import numpy as np

from server.engine import subgraph
from server.engine.base import Stimulus
from server.engine.olfactory import OlfactoryMBEngine, Params
from tests.synthetic import make_data

ODOR = Stimulus("test", (("ORN_T0", 500.0), ("ORN_T3", 500.0), ("ORN_T7", 500.0)))
OTHER = Stimulus("test", (("ORN_T1", 500.0), ("ORN_T5", 500.0)))


def engine(**params):
    return OlfactoryMBEngine(Params(epi_ms=100, washout_ms=20, **params), data=make_data())


class SyntheticEngine(unittest.TestCase):
    def test_activity_reaches_mbons(self):
        result = engine().run_episode(ODOR, seed=1)
        self.assertGreater(result.kc_active, 0)
        self.assertGreater(sum(result.mbon_spikes), 0)
        self.assertEqual(result.pam_hz, 0.0)

    def test_seeded_inference_is_order_independent(self):
        e = engine()
        first = e.run_episode(ODOR, seed=5)
        e.run_episode(OTHER, seed=9)
        again = e.run_episode(ODOR, seed=5)
        self.assertEqual(first.mbon_spikes, again.mbon_spikes)
        self.assertEqual(first.total_spikes, again.total_spikes)

    def test_reward_changes_only_active_kc_to_mbon(self):
        e = engine()
        before = e.net.graph.data.copy()
        fingerprint = e.fingerprint()
        result = e.run_episode(ODOR, reward=True, seed=2)
        self.assertTrue(result.plasticity_applied)
        self.assertGreater(result.pam_hz, 1.0)
        changed = np.flatnonzero(e.net.graph.data != before)
        self.assertEqual(len(changed), result.changed_synapses)
        self.assertTrue(set(changed) <= set(e.plastic))
        rows = np.repeat(np.arange(e.net.n), np.diff(e.net.graph.indptr))
        self.assertTrue(set(rows[changed]) <= set(result.kc_active_ids))
        np.testing.assert_allclose(e.net.graph.data[changed], before[changed] * 0.5)
        self.assertNotEqual(e.fingerprint(), fingerprint)
        self.assertEqual(len(e.history), 1)

    def test_unknown_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            engine().run_episode(Stimulus("test", (("ORN_missing", 1.0),)))

    def test_checkpoint_restore_reproduces_outputs(self):
        e = engine()
        for _ in range(3):
            e.run_episode(ODOR, reward=True, carry_state=True)
            e.run_episode(OTHER, carry_state=True)
        saved = e.checkpoint()
        restored = engine()
        restored.restore(saved)
        self.assertEqual(restored.fingerprint(), e.fingerprint())
        self.assertEqual(restored.history, e.history)
        # Identical stimuli after restore: seeded trials and exact continuation.
        self.assertEqual(e.run_episode(ODOR, seed=11).mbon_spikes, restored.run_episode(ODOR, seed=11).mbon_spikes)
        e.restore(saved)
        a = e.run_episode(OTHER, carry_state=True)
        b = restored.run_episode(OTHER, carry_state=True)
        self.assertEqual((a.mbon_spikes, a.total_spikes), (b.mbon_spikes, b.total_spikes))

    def test_incompatible_checkpoint_is_refused(self):
        saved = engine().checkpoint()
        other = OlfactoryMBEngine(Params(epi_ms=100, washout_ms=20, eta=0.3), data=make_data())
        with self.assertRaises(ValueError):
            other.restore(saved)
        saved.arrays["plastic_weight_mv"] = saved.arrays["plastic_weight_mv"] * 0.9
        with self.assertRaises(ValueError):
            engine().restore(saved)


@unittest.skipUnless(subgraph.OUTPUT.exists(), "prepare with `python -m server.engine.subgraph`")
class RealSubgraph(unittest.TestCase):
    def test_restore_after_learning_matches_on_identical_stimuli(self):
        e = OlfactoryMBEngine()
        self.assertEqual((e.net.n, len(e.plastic)), (8991, 62261))
        odor = Stimulus("test", tuple((t, 500.0) for t in ("ORN_VA1v", "ORN_DL3", "ORN_DA1", "ORN_DL1", "ORN_DL4", "ORN_DM2")))
        e.run_episode(odor, reward=True, seed=0)
        saved = e.checkpoint()
        restored = OlfactoryMBEngine()
        restored.restore(saved)
        a, b = e.run_episode(odor, seed=3), restored.run_episode(odor, seed=3)
        self.assertEqual(a.mbon_spikes, b.mbon_spikes)
        self.assertEqual(a.group_spikes, b.group_spikes)


if __name__ == "__main__":
    unittest.main()
