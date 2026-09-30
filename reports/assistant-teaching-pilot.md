# Assistant teaching and held-out pilot

Measured September 30, 2026. [Machine-readable measurements](results/assistant-teaching-pilot.json). [Teaching criteria](../docs/TEACHER_BRIEF.md).

## What was actually done

The assistant inspected 32 newly imported Bazaraki adverts and all 385 available photographs. Twenty-two reviews were saved for training: two positives, eleven negatives and nine requiring confirmation. Every ordered photo has a recorded observation and content hash. The two positives passed the existing covered-parking/budget brief and the individual source-pin highway rule. Only their 19 unique photographs supplied new positive reinforcement. Negative and neutral reviews do not stimulate an aversive circuit.

Fifteen existing human comparisons remain fifteen human choices. Assistant labels are separately identified, cannot overwrite human ratings and do not fulfil the 50-human-choice target. Full-session ZIP preserves their provenance; lightweight JSON restores human choices only.

Memory revision 37 used 229 reinforcement episodes including replayed earlier choices, changed 12,636 directed KC→MBON weights relative to revision 15, and took 259.82 seconds. Its saved checkpoint is `71674abda9e8f62e4973e4780a612df8425b84713b573db85323a35eeb376278`. The six-photo matched probe was a neutral, excluded apartment: mean MBON response changed from 3209.2 to 2897.0 spikes/photo. This measures generalization after other galleries were rewarded, not reward for this probe apartment.

## Held-out assistant labels

After memory finished, checkpoint, model design, brief, galleries and training feedback were formally reserved. Four other apartment groups supplied one positive, two negative and one neutral assistant rating. All four writes were evaluation-only: they appended no reinforcement events and never fitted the live readout. One possible duplicate advert was omitted. The resulting six-arm calculation restored live memory and did not publish experimental weights.

The visual reviews had already been drafted before formal reservation. The test pool was identified separately from the first training batch; its labels were never passed to training or used to tune the model. This is a held-out assistant pilot exercising the frozen-model mechanism, **not a prospectively blinded human preference study**.

Training: 29 eligible apartments, 15 human comparisons and 13 assistant ratings. Test: four groups, four assistant ratings, zero human choices. Nine of the original training reviews fail existing hard filters and are excluded from readout fitting. Their nonpositive journal entries provide no dopamine reward.

## Recommendation measurements

| Model | Rating AUC | Precision over decisive rated groups |
| --- | --- | --- |
| rate_readout | 0.50 | 0.33 (k=3) |
| clip_readout | 0.00 | 0.33 (k=3) |
| spiking_fixed | 0.50 | 0.33 (k=3) |
| spiking_memory | 0.00 | 0.33 (k=3) |
| spiking_rewired | 1.00 | 0.33 (k=3) |
| price_distance | 0.50 | 0.33 (k=3) |

Learned-minus-fixed rating AUC: **-0.50**. AUC compares one positive with two negative apartment groups; the neutral review is excluded. Pair agreement and its intervals are unavailable because there are no test pairs. No AUC confidence interval was estimated. The sample is too small and selectively curated to establish improved recommendation quality or agreement with the user's personal taste.

The sensory mode was Pure. Saved reinforcement combined the older Cyborg human events with the new Pure assistant events: cyborg, pure. This is not a Pure-only memory experiment. The unchanged Pure adapter pools luminance and cannot directly preserve red hue or detailed appliance semantics. Assistant inspection supplies supervision; detailed CLIP remains an explicit comparison arm.

## Resources

Total evaluation wall time: 2069.64 seconds. Complete photo coverage. Three spiking arms each process the same photographs: 1,269 inference episodes in total.

| Spiking arm | Unique photos | Mean seconds/photo | p95 seconds/photo |
| --- | --- | --- | --- |
| spiking_fixed | 423 | 1.856 | 3.903 |
| spiking_memory | 423 | 1.505 | 3.764 |
| spiking_rewired | 423 | 1.430 | 2.708 |

Worker peak RSS: 151.3 MB, a worker-lifetime high-water mark. It excludes API, CLIP and browser processes. Browser activity and warm caches prevent treating this as an isolated machine benchmark.

## Remaining evidence

Collect genuine human feedback for personal agreement; use a fresh final cohort before collecting its labels; validate stimulus specificity and an aversive circuit separately. Confirm actual addresses, availability, appliance condition/age and internal-only area before arranging a viewing. The curated shortlist is assistant judgement; a neural score can disagree with it.
