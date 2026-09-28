"""Generate the R1 report and figure from measured results, without rerunning simulations."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from research.bootstrap import ROOT

RESULTS = ROOT / 'reports/results'


def load(name):
    return json.loads((RESULTS / (name + '.json')).read_text())


def average(rows, prefix, field='mbon_spk'):
    return float(np.mean([r[field] for r in rows if r['episode'].startswith(prefix)]))


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else None


def main():
    audit = load('connectome-audit')
    taste = load('taste_s0_n3')
    learning = [load(f'learning_g20_s{s}') for s in range(3)]
    gain1 = load('learning_g1_s0')
    stability = [load(name) for name in ('stability_full_raw_s0', 'stability_subgraph_raw_s0', 'stability_subgraph_edited_s0')]
    runs = [taste, *learning, gain1, *stability]
    if any(r['exit_code'] != 0 for r in runs):
        raise RuntimeError('Only completed experiments can produce a baseline report')
    metrics = {'learning': [], 'resources': [], 'stability': [], 'taste': taste['results']}
    for run in [*learning, gain1]:
        rows = run['episodes']
        pre_a, post_a = average(rows, 'pre_A'), average(rows, 'post_A')
        pre_b, post_b = average(rows, 'pre_B'), average(rows, 'post_B')
        by_name = {r['episode']: r for r in rows}
        profile = run['profile']['runs']
        ge2 = [p['kc_active_ge2'] / p['kc_count'] for p in profile[:8:2] if 'kc_active_ge2' in p]
        metrics['learning'].append({
            'run': run['run'], 'gain': run['gain'], 'seed': run['seed'],
            'pre_A_spikes': pre_a, 'post_A_spikes': post_a,
            'A_suppression_percent': 100 * (1 - post_a / pre_a),
            'pre_B_spikes': pre_b, 'post_B_spikes': post_b,
            'B_change_percent': 100 * (post_b / pre_b - 1),
            'plastic_weight_mass_change_percent': 100 * (1 - rows[-1]['w_frac']),
            'changed_pairs': run['weights_summary']['learning_modified_pairs'],
            'changes_outside_KC_MBON': run['weights_summary']['learning_changes_outside_kc_mbon'],
            'pre_KC_active_ge1_percent': 100 * np.mean([r['kc_active'] / 5177 for r in rows[:4]]),
            'pre_KC_active_ge2_percent': 100 * np.mean(ge2) if ge2 else None,
            'pre_A_repeat_jaccard_ge1': jaccard(by_name['pre_A0']['kc_ids'], by_name['pre_A1']['kc_ids']),
            'pre_B_repeat_jaccard_ge1': jaccard(by_name['pre_B0']['kc_ids'], by_name['pre_B1']['kc_ids']),
            'A_B_jaccard_ge1': jaccard(by_name['pre_A0']['kc_ids'], by_name['pre_B0']['kc_ids']),
        })
    for run in runs:
        profile = run['profile']['runs']
        build = run['profile']['network_builds'][0]['seconds']
        if run['protocol'] == 'learning':
            episodes = [profile[i]['wall_seconds'] + profile[i + 1]['wall_seconds'] for i in range(2, len(profile), 2)]
            repeat = float(np.median(episodes))
            repeat_unit = '0.5 s stimulus + 0.15 s washout'
        else:
            repeat = float(np.median([p['wall_seconds'] for p in profile[1:]]))
            repeat_unit = '1 s trial, rebuilt network' if run['protocol'] == 'taste' else '0.25–0.5 s stages, reused network'
        metrics['resources'].append({'run': run['run'], 'total_wall_seconds': run['wall_seconds'],
            'first_build_seconds': build, 'first_run_seconds': profile[0]['wall_seconds'],
            'repeat_median_seconds': repeat, 'repeat_unit': repeat_unit,
            'peak_worker_GiB': run['peak_worker_rss_bytes'] / 2**30,
            'peak_process_tree_GiB': run['peak_process_tree_rss_bytes'] / 2**30})
    for run in stability:
        s = run['stability']
        stages = s['stages']
        last = stages[-1]
        metrics['stability'].append({'run': run['run'], 'initial_idle_spikes': stages[0]['total_spikes'],
            'weak_odor_spikes': stages[1]['total_spikes'], 'final_washout_spikes': last['total_spikes'],
            'final_washout_spikes_per_second': last['total_spikes'] / last['seconds'],
            'final_washout_active_neurons': last['active_neurons'],
            'final_washout_KC_ge2_percent': 100 * last['kc_active_ge2'] / s['groups']['kc']})
    (RESULTS / 'metrics.json').write_text(json.dumps(metrics, indent=2, allow_nan=False) + '\n')

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    fig.suptitle('Fly Estate · measured LIF baseline', fontsize=17, fontweight='bold')
    ax = axes[0]
    sugar = [r for r in taste['results'] if r['neuron'] == 'MN9_L' and r['condition'].startswith('sugar_')]
    ax.errorbar([25, 50, 100, 150, 200], [r['rate_hz'] for r in sugar],
                yerr=[r['std_hz'] for r in sugar], marker='o', capsize=4, color='#176d69', label='Sugar · mean ± SD')
    mixed = next(r for r in taste['results'] if r['condition'] == 'sugar150_bitter150' and r['neuron'] == 'MN9_L')
    ax.scatter([150], [mixed['rate_hz']], marker='X', s=90, color='#ab4864', label='Sugar + bitter')
    ax.set(title='Taste → motor output · v630', xlabel='Input rate (Hz)', ylabel='MN9_L firing rate (Hz)', ylim=(0, 110))
    ax.legend(frameon=False, fontsize=9, loc='upper left')
    ax.text(.02, -.24, '3 trials per condition · 1 simulated second each', transform=ax.transAxes, fontsize=9)
    ax = axes[1]
    curves_a, curves_b = [], []
    for run in learning:
        rows = run['episodes']; named = {r['episode']: r for r in rows}
        pre_a, pre_b = average(rows, 'pre_A'), average(rows, 'pre_B')
        curves_a.append([100, *[100 * named[f'train{i}_A+US']['mbon_spk'] / pre_a for i in range(1, 5)], 100 * average(rows, 'post_A') / pre_a])
        curves_b.append([100, *[100 * named[f'train{i}_B']['mbon_spk'] / pre_b for i in range(5)]])
    for values, color, label in [(curves_a, '#176d69', 'Rewarded odor A'), (curves_b, '#ab4864', 'Unpaired odor B')]:
        values = np.array(values)
        for row in values:
            ax.plot(range(6), row, alpha=.25, color=color, linewidth=1)
        ax.plot(range(6), values.mean(axis=0), marker='o', color=color, label=label)
    ax.set(title='Conditioning · 8,991 neurons', xlabel='Completed reward pairings', ylabel='MBON response (% of pre)', ylim=(0, 115), xticks=range(6))
    ax.legend(frameon=False, fontsize=9)
    ax.text(.02, -.24, '3 seeds · artificial KC→MBON gain ×20', transform=ax.transAxes, fontsize=9)
    ax = axes[2]
    for run, color, label in [(stability[0], '#ab4864', 'Unedited full v783'), (stability[2], '#176d69', 'Edited olfactory subgraph')]:
        stages = run['stability']['stages']
        ax.plot(range(len(stages)), [s['total_spikes'] / s['seconds'] / 1000 for s in stages], color=color, marker='o', label=label)
    ax.set(title='Activity after input stops', ylabel='Population spikes / second (thousands)', xticks=range(6),
           xticklabels=['Idle', 'Odor', '+.25', '+.50', '+.75', '+1.0'], xlabel='Input-off time (seconds)')
    ax.legend(frameon=False, fontsize=9)
    ax.text(.02, -.24, '10 Hz ORN input · observed washout: 1 second', transform=ax.transAxes, fontsize=9)
    figures = ROOT / 'reports/figures'; figures.mkdir(exist_ok=True)
    fig.savefig(figures / 'lif-baseline.png', dpi=180)
    fig.savefig(figures / 'lif-baseline.svg')
    svg = figures / 'lif-baseline.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)

    table_learning = '\n'.join(f"| {r['seed']} | {r['gain']:g} | {r['pre_A_spikes']:.0f} → {r['post_A_spikes']:.0f} | {r['A_suppression_percent']:.2f}% | {r['B_change_percent']:+.2f}% | {r['changed_pairs']:,} |" for r in metrics['learning'])
    table_resources = '\n'.join(f"| {r['run']} | {r['total_wall_seconds']:.2f} | {r['first_build_seconds']:.2f} | {r['first_run_seconds']:.2f} | {r['repeat_median_seconds']:.3f} | {r['peak_worker_GiB']:.2f} |" for r in metrics['resources'])
    table_stability = '\n'.join(f"| {r['run']} | {r['initial_idle_spikes']:,} | {r['final_washout_spikes_per_second']:,.0f} | {r['final_washout_active_neurons']:,} | {r['final_washout_KC_ge2_percent']:.1f}% |" for r in metrics['stability'])
    table_kc = '\n'.join(f"| {r['seed']} | {r['gain']:g} | {r['pre_KC_active_ge1_percent']:.2f}% | {r['pre_KC_active_ge2_percent']:.2f}% | {r['pre_A_repeat_jaccard_ge1']:.3f} | {r['A_B_jaccard_ge1']:.3f} |" if r['pre_KC_active_ge2_percent'] is not None else f"| {r['seed']} | {r['gain']:g} | {r['pre_KC_active_ge1_percent']:.2f}% | not recorded | {r['pre_A_repeat_jaccard_ge1']:.3f} | {r['A_B_jaccard_ge1']:.3f} |" for r in metrics['learning'])
    suppression = 100 * (1 - mixed['rate_hz'] / next(r['rate_hz'] for r in sugar if r['condition'] == 'sugar_150Hz'))
    env = taste['environment']
    measured = taste.get('recorded_at', '2026-09-28').split('T')[0]
    memory = f"{env['memory_bytes'] / 2**30:g} GiB RAM" if 'memory_bytes' in env else 'RAM not recorded'
    dose_rates = '/'.join(f"{r['rate_hz']:.2f}".rstrip('0').rstrip('.') for r in sugar)
    bitter = next(r['rate_hz'] for r in taste['results'] if r['condition'] == 'bitter_150Hz' and r['neuron'] == 'MN9_L')
    water = next(r['rate_hz'] for r in taste['results'] if r['condition'] == 'water_150Hz' and r['neuron'] == 'MN9_L')
    report = f'''# R1: reproduced LIF baseline and resource measurements

Measured {measured}, on {env.get('processor', env['machine'])} ({env['logical_cpus']} logical CPUs, {memory}), {env['os']}, Python {env['python']}. One research worker at a time; Cython code generation; no GPU. Other desktop processes may affect these timings; the original September 28 measurement also ran alongside the apartment application.

**R1 is complete as an exploratory reproduction.** This establishes a spiking research baseline. Apartment photos and personal ratings still use the application’s existing rate engine; research plasticity is not connected to the application yet.

![Measured taste, conditioning and sustained activity](figures/lif-baseline.png)

## Sources and exact protocol

- [Shiu model](https://github.com/philshiu/Drosophila_brain_model/tree/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960), [published paper](https://www.nature.com/articles/s41586-024-07763-9).
- [fly-api](https://github.com/dtch1997/fly-api/tree/a6ad07a810b1a43cd0356149c07b32105eb46d2a), [taste protocol](https://github.com/dtch1997/fly-api/blob/a6ad07a810b1a43cd0356149c07b32105eb46d2a/demo/track_a_lif.py), [learning protocol](https://github.com/dtch1997/fly-api/blob/a6ad07a810b1a43cd0356149c07b32105eb46d2a/experiments/learning/learning_driver_mb.py).
- Source and dataset SHA256 values: [upstream manifest](../research/upstream-manifest.json). Large upstream files remain in the ignored cache; their original code is unchanged.
- Runtime adaptations: replace the learning driver’s hardcoded annotation path with our pinned v3.1.0 TSV; seed Brian2 explicitly; use one worker; set dt to 0.1 ms; measure build/run durations and RSS. Recompute taste rates from spike files to include silent trials where the upstream pivot table emits NaN. Preserve the raw upstream output in the cache.
- Brian2 2.9.0 failed on NumPy 2.5.3 (`ndarray.ptp` removed). Use the separate NumPy 1.26.4 research environment; the application’s NumPy environment is preserved. [Failure record](results/failed_numpy2.json), [dependency lock](../research/requirements-lock.txt).

The LIF equations and constants follow the upstream model: rest/reset −52 mV, threshold −45 mV, membrane time constant 20 ms, synaptic decay 5 ms, refractory period 2.2 ms, transmission delay 1.8 ms and weight 0.275 mV per signed anatomical synapse. External Poisson stimulation uses the upstream factor 250 and zero refractory period for stimulated targets. Weight signs are inherited predictions in the supplied connectivity data, not validated receptor-specific signs.

## Connectome audit

| Data | Neurons | Directed pairs | Anatomical synapses | Sign/threshold |
| --- | ---: | ---: | ---: | --- |
| Shiu v630 taste experiment | 127,400 | 14,687,178 | 52,793,639 | inherited ± signs; count ≥1 |
| Shiu v783 full model | 138,639 | 15,091,983 | 54,492,922 | inherited ± signs; count ≥1 |
| v783 olfactory→MB experiment | 8,991 | 791,613 | subset of the full data | four explicit structural edits |
| Current apartment application | 139,248 | 2,700,429 | 34,152,544 | positive normalized weights; count ≥5 |

All upstream connection indices match their root IDs. Both upstream datasets contain zero self-connections and zero duplicate pairs. v783 has 9,059,302 positive and 6,032,681 negative directed pairs. Of our 139,248 annotation IDs, **138,625 match v783, 623 are absent from its completeness table**, and 14 upstream IDs lack a current annotation. Do not silently equate the displayed anatomy with simulated neurons. v630 taste IDs remain a distinct version; no v630→v783 conversion is claimed.

The learning subgraph matches 8,991 neurons: 2,279 ORNs, 429 ALLNs, 685 ALPNs, 5,177 KCs, 2 APLs, 96 MBONs, 307 PAMs and 16 PPL1s. [Full audit and missing-ID lists](results/connectome-audit.json).

## Taste response

Original v630 taste protocol, **three one-second trials per condition** rather than the paper’s 30. MN9_L responds to sugar input at 25/50/100/150/200 Hz with {dose_rates} Hz. At 150 Hz, bitter produces {bitter:g} Hz, water {water:g} Hz, and sugar+bitter {mixed['rate_hz']:g} Hz: **{suppression:.1f}% suppression** relative to sugar alone. Variability across the three trials is recorded as population SD, not a confidence interval. [Measured rates](results/taste_s0_n3.json).

This reproduces the qualitative dose response and bitter suppression. It is not a full statistical replication of the original paper.

## Conditioning and gain sensitivity

Six disjoint ORN classes per odor, 500 Hz input, 0.5 s episodes plus 0.15 s washout; PAM reward drive 60 Hz; five rewarded A episodes interleaved with unpaired B; two pre/post presentations; η=0.5; active KC threshold ≥1 spike; PAM gate ≥1 Hz. Brian2 and odor selection use seeds 0/1/2. G=20 is the explicit artificial KC→MBON gain; G=1 is a sensitivity arm at seed 0.

| Seed | Gain | A pre → post spikes | A suppression | B change | Changed pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
{table_learning}

There are 62,261 candidate KC→MBON pairs. Every run changes **zero connections outside that declared set**. Reduced response to A is a readout of this artificial reward protocol; lower total MBON output does not independently prove appetitive polarity. Checkpoints store before/after weights in volts, pre/post indices and root IDs. Their hashes are recorded; they are research weight snapshots, not complete restartable application checkpoints.

Structural edits are explicit: DAN fast outputs zeroed, KC→KC zeroed, ORN afferents zeroed, positive ALLN outputs zeroed. The source selects 50,155 / 293,762 / 65,429 / 37,892 pairs respectively; these masks overlap. G=20 also modifies KC→MBON efficacy. Uniform episodic LTD is not compartment-specific dopamine biology. Human apartment feedback has not been used in these experiments.

### KC sparsity and repeatability

Pre-episode active fraction, with stated thresholds:

| Seed | Gain | KC ≥1 spike | KC ≥2 spikes | A repeat Jaccard (≥1) | A/B Jaccard (≥1) |
| --- | ---: | ---: | ---: | ---: | ---: |
{table_kc}

The ≥2-spike instrumentation was added after the first G=20 run, so that value is missing for seed 0. Report threshold/gain dependence explicitly; do not copy claims of perfect repeatability or a single sparsity percentage from another environment. Generalization probes run only after training in the upstream driver: their raw response and weight-depression trace are recorded, but there is no matched naive-probe baseline here for estimating a generalization suppression percentage.

## Spontaneous and sustained activity

Initial idle lasts 0.5 s; one ORN_DA1 class (126 input neurons) receives 10 Hz for 0.5 s, followed by four 0.25 s input-free windows. Stability uses a vectorized PoissonGroup adapter with the same input amplitude; taste reproduction uses the original per-neuron PoissonInput. Only the subgraph receives the four edits in the edited arm; its gain is 1.

| Run | Initial idle spikes | Final washout spikes/s | Active neurons in final window | KC ≥2 active |
| --- | ---: | ---: | ---: | ---: |
{table_stability}

The unedited model is silent before input but develops sustained activity that remains present throughout the measured one-second washout. The edited olfactory subgraph returns to silence. The experiment does not establish infinite persistence or whole-brain stability after the subgraph edits.

## Compute cost

Seconds and **GiB** (2³⁰ bytes); RSS sampled every 50 ms. Worker peak excludes the HTTP server, application CLIP model and the profiling parent. Process-tree peaks including compiler children are also in the JSON records. Compilation cache is shared between serial runs; first calls in later runs may already have warm kernels.

| Run | Total wall s | First build s | First run s | Repeat median s | Worker peak GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
{table_resources}

The taste script rebuilds each network and repeatedly generates input kernels. Its trial timings include preparation/compilation inside `Network.run` and are **not steady-state episode latency**. Learning reuses a compiled network: its repeat median covers a full 0.5 s stimulus plus 0.15 s washout. Stability repeat timings mix 0.25/0.5 s windows; inspect individual durations in the JSON. The first taste run began with an empty dedicated Cython cache; later protocols reused it. These are local measurements, not a hardware-independent promise.

## R2 integration decision

1. Start with one persistent research worker using the **explicit 8,991-neuron edited olfactory→MB subgraph**. Keep the full graph as a separate offline research mode until a stable stimulus regime is established. Full v783 fits local RAM, but the sustained activity makes raw photo stimulation unsuitable without further work.
2. Prepare the signed subgraph once, reuse the compiled network, and avoid loading the full 15-million-pair table for every episode. Preserve original anatomical weights separately from structural edits, readout gain and learned memory.
3. Keep the existing apartment rate engine as the application baseline. Add a versioned `SimulationEngine`, durable queue and traceable checkpoint before sending apartment stimuli into LIF. Explicitly distinguish simulated neurons from display-only anatomy.
4. Treat G=20 and uniform LTD as research settings. Select apartment valence, compartments and sensory projections in R3/R4; this odor reproduction does not establish apartment taste or flight behavior.

## Reproduce

See [research setup and run instructions](../research/README.md). Run `research.bootstrap`, `research.audit`, `research.suite`, then `research.analyse` in the separate locked environment. Completed successful runs are preserved; cached numerical outputs allow regenerating this report and figure without rerunning simulations. [Machine-readable metrics](results/metrics.json).
'''
    (ROOT / 'reports/lif-baseline.md').write_text(report)
    print(json.dumps(metrics['learning'], indent=2))
    print('Generated reports/lif-baseline.md and reports/figures/lif-baseline.png')


if __name__ == '__main__':
    main()
