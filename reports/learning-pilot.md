# First personal-memory pilot

Measured September 30, 2026, using 15 existing human pairwise choices. No single ratings or invented feedback were added. Private apartment identities, galleries and choice records are excluded from this report.

## Memory effect

The `positive-gallery-ltd-v1` protocol replayed 210 unique-photo episodes across the 15 winning-gallery events. Each event bounded its reinforcement dose to 10% per connection, independent of gallery length. The published revision changed **16,932 distinct directed KC→MBON connections**. The count of repeated synaptic updates was 1,915,303; it is not a count of distinct connections.

An unrewarded matched probe used all 14 unique photos of the final event's apartment, with the same photo stimuli and random seeds before and after rebuilding memory:

| Measurement                                    |  Before |   After |
| ---------------------------------------------- | ------: | ------: |
| Mean summed MBON spikes per photo, over 500 ms | 5,552.7 | 3,318.6 |

This is a 40.2% reduction. It demonstrates an effect of the implemented depression rule. It does not establish biological positive valence or better recommendations. The 3D view exposes the 256 strongest changed connections and a matched first-photo recording for both checkpoints. Restart restored the identical learned checkpoint and revision. Original ratings and pairwise values were compared with the pre-learning SQLite backup and were unchanged.

## Apartment-group holdout

Protocol: `group-holdout-v1`, split seed 784, fixed before computing model scores. The feasibility search starts at 783 and depends only on feedback counts. Sixteen reviewed apartment groups produced 13 training apartments and 3 held-out apartments. Twelve comparisons trained each readout and reinforced the experimental memory arm; three comparisons were held out. All choices touching held-out apartments were excluded from both reinforcement and readout training. Duplicate photo groups cannot cross the boundary.

Both spiking arms averaged every unique available photo using identical stimuli and seeds. Photo coverage was 100%; evaluation took 360.39 seconds. The user's live learned checkpoint was preserved throughout this separate experiment.

| Model                            | Correct test comparisons | Pair agreement | Descriptive Wilson 95% interval |
| -------------------------------- | -----------------------: | -------------: | ------------------------------: |
| Price + distance rule            |                    1 / 3 |          33.3% |                       6.2–79.2% |
| Rate readout                     |                    1 / 3 |          33.3% |                       6.2–79.2% |
| Fixed spiking weights + readout  |                    2 / 3 |          66.7% |                      20.8–93.9% |
| Learned spiking memory + readout |                    2 / 3 |          66.7% |                      20.8–93.9% |

**Measured plasticity advantage: 0 percentage points. Improved recommendation quality is not established.** There were no test ties and no single-apartment binary ratings, so rating AUC is unavailable. Correlated comparisons and only three test choices prevent strong statistical conclusions. The Wilson intervals are descriptive and assume independent outcomes; repeating this split does not create independent evidence.

This is a retrospective pilot with a training-only simulated memory arm. A prospective benchmark must reserve new apartment groups before collecting feedback. The next data target is at least 50 diverse real choices, with the model design frozen before final evaluation. Direct CLIP and rewired-connectivity controls, group-aware uncertainty and ranking metrics were still open at the time of this pilot.

September 30 update: the [six-arm retrospective report](learning-six-arm-pilot.md) adds those controls on the same split under Pure inference with Cyborg-conditioned memory. All arms scored 1 of 3. The report documents the codec change and single connected test component; it does not replace this historical four-arm measurement or add independent human feedback. Prospective reservation and evaluation are implemented; new labels remain to be collected.

Implementation and recovery rules: [learning protocol](../docs/LEARNING.md). Local checks passed: 64 unit tests, TypeScript and production frontend build; browser inspection confirmed connection overlays, before/after playback and the held-out report.
