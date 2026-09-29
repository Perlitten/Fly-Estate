"""Hand-checkable cases for the LIF step schedule."""
import unittest

import numpy as np

from server.engine.lif import A, B, COUPLING, DELAY_STEPS, POISSON_WEIGHT_MV, LifNetwork


class Scripted:
    """Stands in for a Generator: fires the listed targets at the listed steps."""

    def __init__(self, spikes_at):
        self.spikes_at, self.step = spikes_at, 0

    def random(self, n):
        row = np.ones(n)
        for target in self.spikes_at.get(self.step, ()):
            row[target] = 0.0
        self.step += 1
        return row


def pair(weight=10.0):
    return LifNetwork(2, np.array([0]), np.array([1]), np.array([weight]))


class LifSchedule(unittest.TestCase):
    def test_drive_spikes_on_next_step(self):
        net = pair()
        net.no_refractory[0] = True
        counts = net.run(1, np.array([0]), np.array([1.0]), Scripted({0: [0]}))
        self.assertEqual(counts[0], 0)
        self.assertAlmostEqual(net.v[0], -52.0 + POISSON_WEIGHT_MV)
        counts = net.run(1, np.array([0]), np.array([1.0]), Scripted({}))
        self.assertEqual(counts[0], 1)
        self.assertEqual(net.v[0], -52.0)
        self.assertEqual(net.last[0], 1)

    def test_synaptic_delay_is_18_steps(self):
        net = pair(weight=10.0)
        net.no_refractory[0] = True
        net.run(1 + DELAY_STEPS, np.array([0]), np.array([1.0]), Scripted({0: [0]}))  # spike at step 1
        self.assertEqual(net.g[1], 0.0)  # steps 0..18: not yet delivered
        net.run(1, np.array([0]), np.array([1.0]), Scripted({}))  # step 19 = 1 + 18
        self.assertAlmostEqual(net.g[1], 10.0)
        net.run(1, np.array([0]), np.array([1.0]), Scripted({}))
        self.assertAlmostEqual(net.g[1], 10.0 * B)
        self.assertAlmostEqual(net.v[1], -52.0 + 10.0 * COUPLING)

    def test_refractory_blocks_integration_and_input(self):
        drive = {s: [0] for s in range(60)}
        free = LifNetwork(1, np.array([0]), np.array([0]), np.array([0.0]))
        free.no_refractory[0] = True
        refractory = LifNetwork(1, np.array([0]), np.array([0]), np.array([0.0]))
        # Without the exemption: spikes at 1, then only after 22 silent steps.
        self.assertEqual(free.run(50, np.array([0]), np.array([1.0]), Scripted(drive))[0], 25)
        self.assertEqual(refractory.run(50, np.array([0]), np.array([1.0]), Scripted(drive))[0], 3)

    def test_leak_is_exact_exponential(self):
        net = pair()
        net.v[:] = -48.0
        net.run(10, np.empty(0, dtype=np.int64), np.empty(0), np.random.default_rng(0))
        self.assertAlmostEqual(net.v[0], -52.0 + 4.0 * A ** 10)

    def test_state_roundtrip_preserves_pending_spikes(self):
        net = pair(weight=10.0)
        net.no_refractory[0] = True
        net.run(5, np.array([0]), np.array([1.0]), Scripted({0: [0]}))  # spike at 1 is in flight
        state = net.state()
        other = pair(weight=10.0)
        other.no_refractory[0] = True
        other.load_state(state)
        a = net.run(30, np.empty(0, dtype=np.int64), np.empty(0), np.random.default_rng(0))
        b = other.run(30, np.empty(0, dtype=np.int64), np.empty(0), np.random.default_rng(0))
        np.testing.assert_array_equal(a, b)
        np.testing.assert_allclose(net.g, other.g)
        np.testing.assert_allclose(net.v, other.v)


if __name__ == "__main__":
    unittest.main()
