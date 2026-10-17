# Positive photo-conditioning controls

Measured September 30, 2026. [Machine-readable summaries](results/photo-memory-controls.json). Isolated application LIF engine, immutable base checkpoint, Pure codec, two distinct real apartment photographs with their stated listing context. Three seeds (0, 1, 2), three presentations per arm, 10% reinforcement dose per paired photo presentation. No personal rating or published checkpoint was changed.

The same A/B presentation sequence was run without reward, with reward paired with A, and with PAM-only reward in a separate quiet episode. The engine resets dynamic state between episodes. Probes use identical seeds before conditioning, after conditioning and after checkpoint encode/decode restoration.

| Arm                      | Changed KC→MBON connections, by seed | Mean A MBON spikes, before → after | Mean B MBON spikes, before → after |
| ------------------------ | ------------------------------------ | ---------------------------------- | ---------------------------------- |
| No reward                | 0 / 0 / 0                            | 5,907.3 → 5,907.3                  | 5,619.7 → 5,619.7                  |
| Reward paired with A     | 11,244 / 11,248 / 11,140             | 5,907.3 → 5,286.7                  | 5,619.7 → 5,038.3                  |
| Unpaired PAM-only reward | 0 / 0 / 0                            | 5,907.3 → 5,907.3                  | 5,619.7 → 5,619.7                  |

Every seed had zero changes outside the declared plastic connections. Checkpoint encode/decode restoration reproduced every post-conditioning A/B MBON spike count exactly. Total wall time: **66.60 seconds**.

Paired reward reduced A responses by **10.5%** and B by **10.3%**. This demonstrates positive plasticity and substantial generalization between these two photo-plus-context stimuli. It does not demonstrate selective visual preference: the two stimuli share the same low-dimensional channel layout and their own listing metadata. An unpaired reward episode has no active sensory-driven KCs; its zero update follows the model's same-episode KC/PAM gate, rather than validating a biological temporal learning window.

This is an artificial-adapter control, distinct from the original R1 odor reproduction and the real multi-gallery personal-memory probe. It does not establish aversive polarity, biological aesthetics or better apartment recommendations. A physical restart and transfer of the full application session still need a separate demonstration. Raw episode recordings and photo provenance remain private under `.cache/research/`.
