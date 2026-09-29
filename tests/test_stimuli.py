"""R3 photo and listing codecs: layout, determinism, unknown values and cache identity."""
import unittest

import numpy as np

from server.engine import stimuli

CHANNELS = [f"ORN_T{k}" for k in range(stimuli.CHANNELS)]
BRIEF = {"ceiling": 2800, "ideal": [34.71, 33.05], "radius": 3}
LISTING = {"price": 1400, "size": 60, "coords": [34.71, 33.05], "coord_kind": "exact",
           "balcony": True, "balcony_size": 15, "balcony_covered": False}


def retina(block=None):
    """8 × 8 RGB retina, black except one white 2 × 2 block at (row, col)."""
    image = np.zeros((8, 8, 3))
    if block:
        r, c = block
        image[r * 2:r * 2 + 2, c * 2:c * 2 + 2] = 1.0
    return image.ravel().tolist()


class PureCodec(unittest.TestCase):
    def test_luminance_grid_maps_block_to_channel(self):
        stimulus, provenance = stimuli.encode("pure", {"retina": retina((1, 2))}, LISTING, BRIEF, CHANNELS)
        rates = dict(stimulus.rates_hz)
        self.assertEqual(stimulus.codec, "photo-pure-v1")
        self.assertAlmostEqual(rates["ORN_T6"], stimuli.MAX_HZ)  # row 1 · 4 + col 2
        self.assertEqual(sum(rates[c] for c in CHANNELS[:16]), stimuli.MAX_HZ)
        self.assertEqual(provenance["context_channels"]["price"], "ORN_T16")

    def test_listing_channels_and_unknown_values(self):
        stimulus, provenance = stimuli.encode("pure", {"retina": retina()}, LISTING, BRIEF, CHANNELS)
        rates = dict(stimulus.rates_hz)
        self.assertAlmostEqual(rates["ORN_T16"], 1400 / 2800 * stimuli.MAX_HZ)  # price
        self.assertAlmostEqual(rates["ORN_T17"], stimuli.MAX_HZ)  # at the preferred point
        self.assertAlmostEqual(rates["ORN_T18"], 60 / 120 * stimuli.MAX_HZ)  # floor area
        self.assertEqual(rates["ORN_T21"], 0.0)  # no confirmed shelter
        unknown = {**LISTING, "coords": None, "size": None, "balcony": False, "balcony_size": None}
        context = stimuli.context_signals(unknown, BRIEF)
        self.assertEqual([context[k]["value"] for k in ("proximity", "floor_area", "balcony", "balcony_size")],
                         [None] * 4)

    def test_needs_all_channels(self):
        with self.assertRaises(ValueError):
            stimuli.encode("pure", {"retina": retina()}, LISTING, BRIEF, CHANNELS[:11])


ZERO = stimuli.Center.of(np.zeros(stimuli.EMBEDDING_DIM), 0)


class CyborgCodec(unittest.TestCase):
    def test_projection_is_fixed_and_scale_invariant(self):
        vector = np.random.default_rng(1).normal(size=stimuli.EMBEDDING_DIM)
        a = stimuli.cyborg_signals(vector, ZERO)
        np.testing.assert_allclose(a, stimuli.cyborg_signals(vector * 3, ZERO), rtol=1e-12)
        self.assertEqual(len(a), 16)
        self.assertTrue(all(0 < x < 1 for x in a))
        self.assertNotEqual(a, stimuli.cyborg_signals(-vector, ZERO))

    def test_centre_removes_the_shared_component(self):
        rng = np.random.default_rng(2)
        shared = rng.normal(size=stimuli.EMBEDDING_DIM) * 3
        photos = shared + rng.normal(size=(40, stimuli.EMBEDDING_DIM))
        units = photos / np.linalg.norm(photos, axis=1, keepdims=True)
        center = stimuli.Center.of(units.mean(axis=0), len(units))

        def correlation(c):
            signals = np.array([stimuli.cyborg_signals(p, c) for p in photos])
            return np.corrcoef(signals)[np.triu_indices(len(photos), 1)].mean()
        self.assertGreater(correlation(ZERO), 0.8)
        self.assertLess(abs(correlation(center)), 0.2)

    def test_requires_embedding_and_centre(self):
        embedding = np.ones(stimuli.EMBEDDING_DIM)
        with self.assertRaises(LookupError):
            stimuli.encode("cyborg", {"retina": retina()}, LISTING, BRIEF, CHANNELS, center=ZERO)
        with self.assertRaises(LookupError):
            stimuli.encode("cyborg", {"retina": retina()}, LISTING, BRIEF, CHANNELS, embedding)
        with self.assertRaises(ValueError):
            stimuli.cyborg_signals([1.0, 2.0], ZERO)


class CacheIdentity(unittest.TestCase):
    def test_key_depends_on_brief_codec_and_weights(self):
        photo = {"retina": retina((0, 0))}
        base, _ = stimuli.encode("pure", photo, LISTING, BRIEF, CHANNELS)
        key = stimuli.cache_key("sha", base, "pure", "v", "f")
        self.assertEqual(key, stimuli.cache_key("sha", base, "pure", "v", "f"))
        moved, _ = stimuli.encode("pure", photo, LISTING, {**BRIEF, "ceiling": 3000}, CHANNELS)
        self.assertNotEqual(key, stimuli.cache_key("sha", moved, "pure", "v", "f"))
        self.assertNotEqual(key, stimuli.cache_key("sha", base, "pure", "v", "other-weights"))
        self.assertNotEqual(key, stimuli.cache_key("sha", base, "cyborg", "v", "f"))
        other = stimuli.Center.of(np.full(stimuli.EMBEDDING_DIM, 0.01), 5)
        self.assertNotEqual(stimuli.cache_key("sha", base, "cyborg", "v", "f", ZERO),
                            stimuli.cache_key("sha", base, "cyborg", "v", "f", other))


if __name__ == "__main__":
    unittest.main()
