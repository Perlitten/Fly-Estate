# Fly Estate: local research release procedure

Updated September 30, 2026. This documents the current local build and the remaining demonstrations. The final prospective benchmark and second-computer transfer have not been completed.

## Reproducible setup

Use Node.js 22+, pnpm 11 and Python 3.11+. Start from the same Git revision as the session being transferred.

```sh
pnpm install --frozen-lockfile
pnpm setup
pnpm dev
```

Setup verifies pinned upstream data, prepares the anatomical/rate graph and the 8,991-neuron edited LIF subgraph, and loads the pinned local CLIP model. It does not download apartment galleries by default. `pnpm setup --seed` explicitly imports the archived public catalogue. There are no fabricated personal choices.

Open `http://127.0.0.1:5176`; API and one persistent worker run locally. [Dependency/source provenance](../README.md#sources-and-versions), [research pins and reproduction](../research/README.md), [scientific boundaries](../README.md#scientific-boundaries).

## Demonstration sequence

1. Open **Area map**. The Bazaraki snapshot contains prices, thumbnails, source URLs and exact or approximate locations. No full gallery is imported merely by searching.
2. Select a marker and **Analyze this apartment**. One advert/gallery is imported, every available photo is encoded and the apartment opens in the brain. Read download warnings and **Source & freshness**. Confirm availability with the original source.
3. Select Pure or Cyborg intentionally. **Analyze in 3D** computes real LIF spikes for every unique stored photo. The remaining anatomical neurons stay dim. **Replay analysis** uses saved recordings; pause, scrub and select photos.
4. Save a real **Would visit**, **Maybe**, **Not for me** or pairwise choice. Positive choices apply the bounded PAM/KC→MBON LTD protocol; neutral and negative feedback train the readout without aversive plasticity.
5. Open **Learning** after the worker publishes memory. Inspect changed connections, checkpointed before/after responses and history. A weight change is evidence of plasticity; recommendation quality requires the next step.
6. **Reserve unseen apartments** before their feedback. Save real choices for reserved groups; those feedback entries remain excluded from training. Collect a broader 50-choice record across areas/interiors. **Evaluate frozen model** compares six fixed arms on frozen choices and downloads a JSON report.

The historical [15-choice pilot](../reports/learning-pilot.md) had only three held-out comparisons. Learned and fixed spikes both agreed on two under Cyborg. The [subsequent six-arm report](../reports/learning-six-arm-pilot.md) reused these choices under Pure inference with Cyborg-conditioned memory: every arm agreed on one of three. These comparisons form one connected component. Neither report establishes improved taste or provides prospective evidence. The [three-seed photo controls](../reports/photo-memory-controls.md) measured positive plasticity and broad A/B generalization; they did not establish selective preference.

## Transfer a complete session

Export **Client brief → Download full session** or **Learning → Save the full session**. The operation refuses to export during an active source import. SQLite snapshots are taken under the application write lock and engine write reservation; media/checkpoints are immutable content-addressed files.

The ZIP includes:

- Local listings, settings, choices, journal and prospective cohorts.
- Engine queue/activity database, embeddings, frozen centres and recordings.
- Prepared subgraph, every registered checkpoint and stored source/uploaded photos.
- Manifest with file sizes, SHA256 checksums, checkpoint pointer, model source hashes and dependency/upstream versions.

The ZIP excludes re-downloadable anatomical/model caches and source-code copies. Transfer it privately; it contains personal preferences and photo provenance. It is not a Git artifact.

After setup with matching model code on the receiving computer, stop API/worker before restoration:

```sh
.venv/bin/python -m server.session restore /absolute/path/fly-estate-session.zip
pnpm dev
```

The CLI rejects a running worker/API, incompatible model source hashes, invalid archive paths, oversized content, checksum/database failures and an incompatible checkpoint. It validates before changing local data. The previous session is preserved under `.cache/session-restores/<id>/`, and installation failure rolls back. `--api-port PORT` checks a nondefault API port. On Windows use `.venv/Scripts/python.exe`.

For terminal export:

```sh
.venv/bin/python -m server.session export /absolute/path/fly-estate-session.zip
```

Use this after source imports finish. The full ZIP also preserves assistant review provenance, per-photo observations and held-out labels. Lightweight JSON refetches source galleries and restores human choices only; it does not transfer exact memory or turn assistant supervision into human feedback.

## Remaining release evidence

- Record second-computer restoration, compare checkpoint hashes and replay the same photo under the same brief/seed.
- Collect real prospective feedback and publish the six-arm measurement with group counts, uncertainty, coverage and resources. Missing AUC/ranking intervals must remain missing when sample structure cannot support them.
- Broaden the measured paired/unpaired/no-reward photo controls to assess specificity; reproduce their effects after a physical restart. Design aversive circuitry and polarity separately.
- Record the frontend build and exact code revision chosen for the research release. A public service and a NeuroMechFly body are separate later decisions.

Current local observation (September 30): frontend TypeScript/Vite build and Python compilation succeeded. API and the single worker restarted with memory revision 37 and checkpoint `71674abda9e8f62e4973e4780a612df8425b84713b573db85323a35eeb376278`; the restored engine fingerprint matches the saved checkpoint. Live status reports 15 human comparisons, 26 assistant reviews and a completed evaluation. The final full-session export produced 1,961 ZIP entries, including its manifest and 1,954 stored photos, with 19 model source hashes (330,006,721 bytes). This confirms export and local restart; offline restoration and second-computer replay remain unmeasured.

The [assistant teaching pilot](../reports/assistant-teaching-pilot.md) took 2,069.64 s for 1,269 LIF inference episodes. Learned rating AUC was 0.00 against fixed weights at 0.50 on three decisive assistant labels; no recommendation gain is established. Earlier six-arm retrospective evaluation took 512.59 s for 606 inference episodes; positive photo controls took 66.60 s. Protocol, label provenance and resource limitations are recorded in their reports. Automated tests were not run during this teaching cycle.

The current implementation uses experimental sensory projections and a positive LTD rule on an edited subgraph. It is neither recorded living-fly activity nor a validated biological apartment selector.
