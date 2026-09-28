# Reproducing the LIF research baseline

This optional environment reproduces the pinned Shiu/fly-api experiments separately from the apartment application. Read the [measured report](../reports/lif-baseline.md) before integrating the model. The application currently uses its existing rate engine.

## Environment

Use **Python 3.12** and a C/C++ compiler for Brian2’s Cython backend. On macOS, install the Xcode command line tools if the compiler is missing; on Linux, install your distribution’s compiler toolchain. The commands below are for macOS/Linux, run from the repository root.

Prepare the application data once, without importing apartments:

```sh
pnpm install --frozen-lockfile
pnpm setup --no-seed
python3.12 -m venv .cache/research/venv
.cache/research/venv/bin/python -m pip install -r research/requirements-lock.txt
.cache/research/venv/bin/python -m research.bootstrap
```

The research environment pins NumPy 1.26.4 and Brian2 2.9.0. Keep it separate from `.venv`: Brian2 failed with the application’s NumPy 2.5.3. The full dependency lock is the measured environment; [requirements.txt](requirements.txt) lists the direct dependencies.

Bootstrap downloads 18 source/data files from two fixed Git commits, verifies SHA256 values against [upstream-manifest.json](upstream-manifest.json), and keeps the files unmodified in `.cache/research/upstream`. It downloads roughly 200 MB in addition to the application data. Raw data, compiled kernels, logs and weight snapshots are excluded from Git.

## Reading or regenerating published results

The repository includes numerical results and figures from September 28, 2026. Regenerate their summary without running simulations:

```sh
.cache/research/venv/bin/python -m research.analyse
```

`research.suite` preserves existing successful result files when their source manifest and recorded package versions match. On a fresh clone, these files are the published measurements, so running the suite normally skips those experiments. Reading these files does not reproduce the measurements on your computer.

## Measuring the complete protocol again

Archive the published results first. If you have previously run simulations in this checkout, also archive `.cache/research/runs`; each run refuses to overwrite its existing raw output directory. Choose a new archive name if one already exists.

```sh
mkdir -p .cache/research
mv reports/results .cache/research/published-results
# Only if this directory already exists:
# mv .cache/research/runs .cache/research/previous-runs
.cache/research/venv/bin/python -m research.audit
.cache/research/venv/bin/python -m research.suite
.cache/research/venv/bin/python -m research.analyse
```

The suite runs one worker at a time:

| Protocol | Data | Configuration |
| --- | --- | --- |
| Original taste response | Shiu v630 full graph | 3 one-second trials per condition, seed 0 |
| Olfactory→MB conditioning | v783, 8,991 matched neurons | Gain 20, seeds 0/1/2; gain 1, seed 0 |
| Idle/input/washout | v783 full graph and olfactory subgraph | Full unedited, subgraph unedited, subgraph with four structural edits |

The original taste protocol took about 15 minutes on the measured M4 Pro. Later experiments took seconds, with different compilation cache conditions. Peak worker memory was roughly 1.7–2.7 GiB; this excludes the desktop and the apartment application. Actual runtime and memory depend on your computer and compiler cache. Three taste trials are an exploratory reproduction, not a full statistical replication of the paper.

Run individual experiments with explicit parameters:

```sh
.cache/research/venv/bin/python -m research.run taste --trials 3 --seed 0
.cache/research/venv/bin/python -m research.run learning --gain 20 --seed 1
.cache/research/venv/bin/python -m research.run stability --scope subgraph --stabilized --seed 0
```

## Outputs and provenance

- `reports/results/*.json`: rates, episode summaries, IDs, audit results, durations, sampled RSS, environment and source hashes.
- `reports/results/metrics.json`: aggregate measurements used by the report and figure.
- `reports/lif-baseline.md`, `reports/figures/lif-baseline.{png,svg}`: readable report and exportable figure.
- `.cache/research/runs/<name>/`: raw spike files, upstream output, profiling log and before/after weight snapshots. Weight snapshots contain neuron IDs, indices and units; they are not complete restartable application checkpoints.
- `.cache/research/cython/`: shared compilation cache. Later runs may reuse compiled kernels; inspect first-run and repeat-run durations separately.

Runtime instrumentation replaces the learning driver’s machine-specific annotation path, sets deterministic seeds, profiles network calls and includes silent taste trials in reported rates. Upstream equations, constants and cached source files stay unchanged. The learning protocol’s structural edits and artificial gain are recorded explicitly. Learned apartment preferences are not used in these experiments.

The report’s integration decision selects one persistent worker for the edited olfactory subgraph. Queue recovery, application checkpoints, photo stimuli and dopamine-dependent apartment memory remain R2–R4 work in the [roadmap](../docs/ROADMAP.md).

Upstream source attribution and licenses: [NOTICE.md](NOTICE.md). Public FlyWire data and annotation citations: [application provenance](../README.md#sources-and-versions).
