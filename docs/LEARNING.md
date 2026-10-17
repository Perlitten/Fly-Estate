# Saved memory and preference evaluation

Implemented September 30, 2026. This protocol connects human choices and explicitly identified assistant reviews to the experimental LIF engine. It does not establish biological apartment preferences.

Measured first run: [personal-memory pilot](../reports/learning-pilot.md). Connections changed, but the small holdout did not establish a recommendation-quality improvement.

## Choice → reinforcement

`Would visit` and the winner of a pair receive positive PAM dopamine reinforcement using the reproduced KC→MBON LTD rule. Every unique photo is simulated independently. A gallery receives one bounded 10% dose: for N unique photos, each photo uses `eta = 1 - 0.9 ** (1/N)`. An active connection therefore cannot lose more than 10% of its weight per gallery event. Multiple distinct human choices can reinforce the same apartment. Identical photo files within its gallery are counted once.

`Maybe`, `Not for me` and pairwise ties update the artificial preference readout. They do not apply a positive pulse. Aversive reinforcement requires a checked circuit and polarity and is not implemented.

Each choice and its outbox event are saved in the same SQLite transaction. The event snapshots its gallery SHA hashes, encoder signals, brief, codec and frozen CLIP centre. Legacy photo embeddings are computed locally when needed. Identical repeated requests do not append another event.

## Persistence and undo

The worker rebuilds each revision from an immutable base checkpoint using the latest event for each rating or pair. Changing or clearing a choice removes its earlier reinforcement. The learned checkpoint, current pointer and applied revision publish together; retries never accumulate an additional dose. Incomplete work resumes from the base after restart. A failed downstream analysis refresh cannot roll back a published checkpoint.

Weight fingerprints invalidate stale photo results. Reviewed apartments are queued for new inference; a fully simulated apartment uses the current spiking readout once enough current choices are available. The rate readout supplies an explicitly labelled fallback. Scores are similarities, not calibrated viewing probabilities.

For choices made before this feature, **Learning → Learn from saved choices** copies the actual saved ratings and comparisons into the journal. Reserved evaluation groups are excluded. It does not invent feedback. Personal databases, checkpoints, photos and reports remain excluded from Git. Full-session ZIP transfers exact memory, images and protocol state with offline restoration; lightweight JSON transfers choices and refetches source photos. See the [transfer procedure](RELEASE.md#transfer-a-complete-session).

## Assistant supervision

At the user's request, the assistant inspected 32 new adverts and all 385 available photos using the [versioned teaching brief](TEACHER_BRIEF.md). It saved 22 training reviews: two supported positives, eleven negatives and nine needing confirmation. Only the two positive galleries supplied new reinforcement: 19 unique photo episodes. The previous 15 human comparisons remain separately identified.

Memory revision 37 completed on September 30: 229 episodes including replayed earlier human reinforcement, 12,636 KC→MBON connections changed relative to revision 15, and 259.82 seconds. Its checkpoint is `71674abda9e8f62e4973e4780a612df8425b84713b573db85323a35eeb376278`. The six-photo matched probe belonged to a neutral, excluded apartment, so its response change is a generalization probe, not a claim that this apartment was rewarded.

Each assistant review freezes the ordered gallery hashes, observations for every photo, source listing fields and road-position evidence. Positive recommendations must pass the existing brief and the documented highway rule. Missing appliance or parking evidence yields confirmation, not invented facts. A human rating may replace an assistant rating; assistant writes cannot overwrite a human rating. Stale reviews leave the active shortlist after their fields, photos or road evidence change.

**Learning → Assistant / your brief** presents the curated shortlist and inspection reasons. These are assistant judgements, separate from a neural model score. Four additional apartment groups have evaluation-only assistant labels and never update memory or fit the readout. Their visual reviews were drafted before the formal checkpoint reservation; this is a held-out assistant pilot exercising the frozen-model mechanism, not a prospectively blinded human preference study. One possible duplicate advert was omitted from this cohort.

Assistant labels count separately from the target of 50 genuine human choices. Positive reviews use the existing bounded LTD rule; negatives and neutral reviews update only the readout. Pure Fly retains its luminance-based sensory adapter and cannot directly preserve red hue or appliance semantics. No semantic vision model is silently inserted into Pure. Full-session ZIP preserves assistant provenance, notes, photos and exact memory; lightweight JSON restores only human choices.

The completed [assistant held-out pilot](../reports/assistant-teaching-pilot.md) took 2,069.64 seconds for 1,269 LIF inference episodes. On one positive and two negative test groups, learned LIF rating AUC was 0.00 versus 0.50 for fixed LIF; the rewired control scored 1.00. No recommendation-quality gain was established. This tiny, curated assistant sample does not measure agreement with the user's personal taste.

## Inspect actual changes

The worker compares plastic weights with the preceding published revision. The brain sidebar's **Learned memory** shows the number of changed directed KC→MBON connections and displays up to 256 strongest changes mapped by FlyWire root ID. Amber means decreased magnitude; blue means restored magnitude after an edit. The displayed subset is not the total number of changed connections.

**Before learning** and **After learning** replay the same first photo with the same random seed. A summary compares MBON spikes averaged over every unique photo in that gallery. Recordings carry checkpoint hashes and use the existing fixed spike brightness scale. The event that publishes a revision can rebuild multiple choices, so its total changes are not attributed solely to the displayed apartment. A lower MBON response demonstrates a memory effect; quality is measured separately.

## Held-out pilot

**Learning → Evaluate on unseen apartments** freezes the current choice history, galleries and brief. About 20% of reviewed apartment groups are held out. Listings sharing any identical photo form one group. All comparisons touching a held-out apartment are excluded from readout training and reinforcement. Snapshot events sharing a held-out photo are also excluded. The cohort must allow at least five training and two test choices; split feasibility uses counts, never model scores.

The original measured pilot had four arms. The current evaluator implements six arms on the same frozen choices:

1. A fixed price + distance rule.
2. Full 512-d CLIP photo embeddings, averaged per gallery, with a regularized preference readout.
3. The rate model with the same preference readout.
4. The spiking engine restored to the immutable base, with a preference readout.
5. That same engine trained only on eligible training choices, with a preference readout.
6. A directed KC→MBON connectivity control, with the same LIF parameters and preference readout. Double-edge swaps preserve KC out-degree, MBON in-degree and per-KC weight multiset, without modifying unrelated edges. Seed, swap count and graph fingerprint are reported.

The spiking arms use the same frozen stimuli and random seeds and average all unique photo responses. Readout normalization is fitted only on training apartments. The sensory projection and frozen CLIP centre are existing fixed model inputs, not tuned against the holdout. Evaluation runs without reward and restores the user's live checkpoint on success, failure or interruption. It never publishes experimental weights.

The report includes decisive pair agreement, correct/total pairs, descriptive Wilson intervals and separate tie handling. Connected comparison components (including both endpoints) define the bootstrap resampling units. With fewer than three components, no bootstrap interval is produced; a large connected comparison graph can therefore have many pairs and little independent evidence. A paired component bootstrap also measures learned-minus-fixed agreement.

Rating AUC and precision@min(5, rated groups) use distinct explicitly rated apartment groups; groups with conflicting duplicate labels are excluded and counted. AUC stays missing unless both classes exist. Precision measures the observed rated subset, not an unobserved population. Report photo coverage, per-photo mean/p95 latency and worker peak RSS; RSS is a worker-lifetime high-water mark, not an isolated per-job peak.

A repeated deterministic split does not add independent evidence. The [six-arm retrospective report](../reports/learning-six-arm-pilot.md) reuses the original 15 real choices and three held-out comparisons. All arms agreed with 1 of 3 choices under Pure inference; saved reinforcement events used Cyborg. This is memory transfer between sensory codecs, not a Pure-only conditioning experiment. The three comparisons form one connected component, so component bootstrap is unavailable. No quality improvement was established. The earlier four-arm Cyborg report remains a separate historical measurement. The new assistant cohort does not add human preference evidence.

## Prospective frozen cohort

**Learning → Reserve unseen apartments** chooses up to ten unreviewed apartment groups across areas before their feedback. At least three unseen groups and five training choices are required. A group touched by any earlier reinforcement photo is ineligible. The reservation freezes the current checkpoint and immutable base, training labels, brief, galleries, encoder/CLIP centre and model source hashes.

Feedback involving reserved apartments or their connected duplicate-photo groups is saved as evaluation-only. It cannot reinforce memory, fit the score readout or select gallery aggregation, including through legacy sync. Groups remain protected after a report is completed. If source fields/gallery change, a new label cannot silently describe the original experiment.

After at least three choices involving that cohort, **Evaluate frozen model** snapshots those labels and queues the six-arm comparison. The learned arm restores the reserved checkpoint, the fixed arm the reserved base. No test label tunes model design. Source-hash changes reject an evaluation. Feedback is rejected if the brief, mode, frozen photos/listing context or comparison opponents have changed. Retrying a failed job uses its original frozen snapshot; reopening a report does not create a new experiment. Download the selected report as JSON. Reports disclose inference mode and the original codecs of saved reinforcement events, including transfer between codecs.

Reserve another cohort only after the preceding one is frozen. If model parameters are tuned after reading a result, reserve fresh final groups; the earlier cohort is no longer an untouched final benchmark. The UI currently exposes model responses during review, so collected labels are user feedback under that interface, not a blinded preference study.

## Isolated positive-plasticity controls

The [photo-conditioning runner](../research/README.md#isolated-photo-conditioning-controls) implements identical A/B presentations with no reward, reward paired with A and PAM-only reward in a separate quiet episode, over specified seeds. It records active KCs, PAM and MBON responses, actual changed connections and checkpoint encode/decode probes on an isolated engine. It does not publish weights or create personal feedback.

The [measured Pure controls](../reports/photo-memory-controls.md) ran seeds 0, 1 and 2 with three conditioning presentations per arm. Only paired reward changed weights: 11,140–11,248 KC→MBON connections. Mean A/B MBON suppression was 10.5%/10.3%, indicating broad generalization rather than selective preference. No changes occurred outside plastic connections; checkpoint encode/decode restored every probe spike count exactly. Separate PAM-only reward has no sensory-driven active KCs, so its zero update follows the implemented same-episode gate, not a validated biological temporal window. Physical restart/transfer, broader specificity and aversive PPL1/MBON polarity remain open.

## Next evidence to collect

Collect at least 50 diverse real choices and rate reserved groups. The current record contains 15 actual comparisons. Run the implemented six-arm prospective evaluator with a fixed brief and mode, then publish sample counts, grouping, uncertainty and resources. Complete an exact-session transfer demonstration and broaden photo-specificity controls. Validate negative reinforcement separately. The current retrospective and positive-plasticity measurements do not establish improved taste.

## Local checks

```sh
.venv/bin/python -m unittest discover -s tests -t . -q
pnpm build
```

Tests cover transaction idempotence, gallery dose, undo, recovery, restricted plastic synapses, publication failure, photo integrity and holdout boundaries.
