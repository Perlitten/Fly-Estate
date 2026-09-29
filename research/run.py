"""Run pinned upstream protocols in one isolated, profiled worker at a time.

Examples:
  .cache/research/venv/bin/python -m research.run taste --trials 3
  .cache/research/venv/bin/python -m research.run learning --seed 0 --gain 20
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import runpy
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from research.bootstrap import ROOT, CACHE, MANIFEST, sha256


def arguments() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("protocol", choices=["taste", "learning", "stability"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--gain", type=float, default=20)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--scope", choices=["subgraph", "full"], default="subgraph")
    ap.add_argument("--stabilized", action="store_true")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.trials < 1 or not 0 < args.gain <= 100:
        ap.error("trials >= 1 and 0 < gain <= 100 required")
    if args.stabilized and args.scope == "full":
        ap.error("The upstream stabilization protocol is only defined for the olfactory subgraph")
    return args


def run_name(args: argparse.Namespace) -> str:
    if args.protocol == "taste":
        return f"taste_s{args.seed}_n{args.trials}"
    if args.protocol == "learning":
        return f"learning_g{args.gain:g}_s{args.seed}"
    return f"stability_{args.scope}_{'edited' if args.stabilized else 'raw'}_s{args.seed}"


def environment() -> dict:
    import psutil
    processor = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        try:
            processor = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    packages = ("brian2", "numpy", "pandas", "scipy", "pyarrow", "cython", "joblib", "psutil", "sympy", "matplotlib")
    return {
        "python": platform.python_version(), "os": platform.platform(),
        "machine": platform.machine(), "logical_cpus": os.cpu_count(),
        "processor": processor, "memory_bytes": psutil.virtual_memory().total,
        "packages": {p: importlib.metadata.version(p) for p in packages},
        "codegen": "cython", "workers": 1,
    }


def normalize_taste(rows: list[dict], out: Path, trials: int) -> list[dict]:
    """Include zero-spike trials; upstream pivot tables emit NaN for silent MN9s."""
    import numpy as np
    import pandas as pd
    tables = {}
    for row in rows:
        if row['flyid'] is None:
            continue
        condition = row['condition']
        if condition not in tables:
            tables[condition] = pd.read_parquet(out / 'spikes' / (condition + '.parquet'),
                                               columns=['flywire_id', 'trial'])
        table = tables[condition]
        counts = table.loc[table.flywire_id == row['flyid']].groupby('trial').size()
        rates = np.zeros(trials)
        for index, count in counts.items():
            rates[int(index)] = count  # Each original taste trial lasts one second.
        row['rate_hz'] = round(float(rates.mean()), 2)
        row['std_hz'] = round(float(rates.std()), 2)
    return rows


def worker(args: argparse.Namespace, out: Path) -> None:
    import numpy as np
    import brian2 as b

    cache_dir = ROOT / ".cache/research/cython"
    cache_dir.mkdir(parents=True, exist_ok=True)
    b.prefs.codegen.target = "cython"
    b.prefs.codegen.runtime.cython.cache_dir = str(cache_dir)
    b.defaultclock.dt = 0.1 * b.ms
    b.seed(args.seed)
    sys.path.insert(0, str(CACHE / "shiu"))
    import model

    profile = []
    builds = []
    context = {}
    original_create = model.create_model

    def create(*a, **kw):
        t0 = time.perf_counter()
        result = original_create(*a, **kw)
        builds.append({"seconds": time.perf_counter() - t0,
                       "neurons": len(result[0]), "directed_pairs": len(result[1])})
        return result

    model.create_model = create
    original_run = b.Network.run

    def measured_run(net, duration, *a, **kw):
        t0 = time.perf_counter()
        monitors = [obj for obj in net.objects if isinstance(obj, b.SpikeMonitor)]
        before = [int(m.num_spikes) for m in monitors]
        before_counts = np.array(context['spk'].count[:], dtype=np.int64) if 'kc_indices' in context else None
        if context and "initial_weights" not in context:
            context["initial_weights"] = np.array(context["syn"].w[:] / b.volt)
        result = original_run(net, duration, *a, **kw)
        after = [int(m.num_spikes) for m in monitors]
        row = {"index": len(profile), "simulated_seconds": float(duration / b.second),
               "wall_seconds": time.perf_counter() - t0,
               "spikes": sum(y - x for x, y in zip(before, after))}
        if before_counts is not None:
            delta = np.array(context['spk'].count[:], dtype=np.int64) - before_counts
            counts = delta[context['kc_indices']]
            row.update(kc_count=len(counts), kc_active_ge1=int((counts >= 1).sum()),
                       kc_active_ge2=int((counts >= 2).sum()))
        profile.append(row)
        print("[profile] " + json.dumps(row), flush=True)
        return result

    b.Network.run = measured_run
    out.mkdir(parents=True, exist_ok=True)
    os.chdir(out)
    if args.protocol == "taste":
        source = CACHE / "fly-api/demo/track_a_lif.py"
        namespace = runpy.run_path(str(source))
        sys.argv = [str(source), "--model-dir", str(CACHE / "shiu"), "--out", str(out / "spikes"),
                    "--n-run", str(args.trials), "--n-proc", "1"]
        namespace["main"]()
    elif args.protocol == "learning":
        source = CACHE / "fly-api/experiments/learning/learning_driver_mb.py"
        sys.path.insert(0, str(source.parent))
        import model_ext
        orig_build = model_ext.build_subnet

        def capture_build(*a, **kw):
            t0 = time.perf_counter()
            result = orig_build(*a, **kw)
            context.update({"neu": result[1], "syn": result[2], "spk": result[3], "old2new": result[4],
                            "original_weights": np.array(result[2].w[:] / b.volt)})
            builds.append({"seconds": time.perf_counter() - t0,
                           "neurons": len(result[1]), "directed_pairs": len(result[2])})
            import pandas as pd
            comp_ids = pd.read_csv(CACHE / 'shiu/Completeness_783.csv', index_col=0).index
            ann = pd.read_csv(ROOT / 'data/raw/annotations_v3.1.0.tsv', sep='\t',
                              usecols=['root_id', 'cell_class'])
            kc_ids = ann.loc[ann.cell_class.fillna('').str.contains('Kenyon', case=False), 'root_id']
            indices = comp_ids.get_indexer(kc_ids)
            context['kc_indices'] = np.array([result[4][int(i)] for i in indices if i in result[4]])
            return result

        model_ext.build_subnet = capture_build
        namespace = runpy.run_path(str(source))
        # The upstream driver has a machine-specific ANN path. Change only that
        # runtime global; the pinned file on disk remains byte-for-byte intact.
        namespace["main"].__globals__["ANN"] = str(ROOT / "data/raw/annotations_v3.1.0.tsv")
        sys.argv = [str(source), "--model-dir", str(CACHE / "shiu"), "--out", str(out),
                    "--seed", str(args.seed), "--orn-hz", "500", "--n-classes", "6",
                    "--eta", "0.5", "--n-pair", "5", "--kc-thresh", "1",
                    "--kcmbon-gain", str(args.gain)]
        namespace["main"]()
        final_w = np.array(context["syn"].w[:] / b.volt)
        initial_w = context["initial_weights"]
        original_w = context["original_weights"]
        changed = final_w != initial_w
        from research.audit import groups
        import pandas as pd
        comp = pd.read_csv(CACHE / "shiu/Completeness_783.csv", index_col=0)
        ann = pd.read_csv(ROOT / "data/raw/annotations_v3.1.0.tsv", sep="\t", low_memory=False)
        original_groups = groups(ann, comp)
        kc = np.array([context['old2new'][int(i)] for i in original_groups['kc']])
        mbon = np.array([context['old2new'][int(i)] for i in original_groups['mbon']])
        pre, post = np.array(context['syn'].i[:]), np.array(context['syn'].j[:])
        plastic_mask = np.isin(pre, kc) & np.isin(post, mbon)
        ordered_indices = sorted(context['old2new'], key=context['old2new'].get)
        np.savez_compressed(out / "research-weights.npz", before=initial_w, after=final_w,
                            pre=pre, post=post, root_ids=comp.index.to_numpy(dtype=np.int64)[ordered_indices])
        (out / "weights-summary.json").write_text(json.dumps({
            "unit": "volt", "gain": args.gain,
            "structurally_modified_pairs": int((original_w != initial_w).sum()),
            "learning_modified_pairs": int(changed.sum()),
            "learning_changes_outside_kc_mbon": int((changed & ~plastic_mask).sum()),
            "unchanged_pairs": int((~changed).sum()),
            "maximum_absolute_change_volt": float(np.max(np.abs(final_w - initial_w))),
            "before_sha256": __import__("hashlib").sha256(initial_w.tobytes()).hexdigest(),
            "after_sha256": __import__("hashlib").sha256(final_w.tobytes()).hexdigest(),
            "checkpoint_sha256": sha256(out / "research-weights.npz"),
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
    else:
        import pandas as pd
        from research.audit import groups
        source = CACHE / "shiu/model.py"
        comp = pd.read_csv(CACHE / "shiu/Completeness_783.csv", index_col=0)
        ann = pd.read_csv(ROOT / "data/raw/annotations_v3.1.0.tsv", sep="\t", low_memory=False)
        original_groups = groups(ann, comp)
        if args.scope == "full":
            neu, syn, monitor = create(CACHE / "shiu/Completeness_783.csv",
                                       CACHE / "shiu/Connectivity_783.parquet", model.default_params)
            mapping = {i: i for i in range(len(comp))}
        else:
            sys.path.insert(0, str(CACHE / "fly-api/experiments/learning"))
            from model_ext import build_subnet
            keep = np.unique(np.concatenate(list(original_groups.values())))
            t0 = time.perf_counter()
            _, neu, syn, monitor, mapping = build_subnet(str(CACHE / "shiu"), model.default_params, keep)
            builds.append({"seconds": time.perf_counter() - t0,
                           "neurons": len(neu), "directed_pairs": len(syn)})
        g = {k: np.array([mapping[int(i)] for i in v], dtype=int) for k, v in original_groups.items()}
        edits = {}
        if args.stabilized:
            pre, post = np.array(syn.i[:]), np.array(syn.j[:])
            w = np.array(syn.w[:] / b.volt)
            masks = {
                "dan_out": np.isin(pre, np.concatenate([g['pam'], g['ppl1']])),
                "kc_kc": np.isin(pre, g['kc']) & np.isin(post, g['kc']),
                "orn_in": np.isin(post, g['orn']),
                "excitatory_alln_out": np.isin(pre, g['alln']) & (w > 0),
            }
            for name, mask in masks.items():
                edits[name] = {"selected_pairs": int(mask.sum()), "nonzero_pairs_zeroed": int((w[mask] != 0).sum())}
                w[mask] = 0
            syn.w[:] = w * b.volt
        orn = ann[ann.super_class.fillna('').str.contains('sensory') & ann.cell_class.fillna('').str.contains('olfactory')]
        odor_type = orn.cell_type.value_counts().index[0]
        upstream_indices = comp.index.get_indexer(orn.loc[orn.cell_type == odor_type, 'root_id'].astype(np.int64))
        targets = np.array([mapping[int(i)] for i in upstream_indices if i in mapping])
        pg = b.PoissonGroup(len(targets), rates=0 * b.Hz)
        drv = b.Synapses(pg, neu, on_pre='v_post += w_drv',
                         namespace={'w_drv': model.default_params['w_syn'] * model.default_params['f_poi']})
        drv.connect(i=np.arange(len(targets)), j=targets)
        neu.rfc[targets] = 0 * b.ms
        net = b.Network(neu, syn, monitor, pg, drv)
        stages = []
        previous = np.zeros(len(neu), dtype=np.int64)
        for label, hz, seconds in [('idle', 0, .5), ('weak_odor', 10, .5),
                                   ('washout_1', 0, .25), ('washout_2', 0, .25),
                                   ('washout_3', 0, .25), ('washout_4', 0, .25)]:
            pg.rates = hz * b.Hz
            net.run(seconds * b.second)
            counts = np.array(monitor.count[:], dtype=np.int64)
            delta = counts - previous
            previous = counts
            row = {'stage': label, 'input_hz': hz, 'seconds': seconds,
                   'total_spikes': int(delta.sum()), 'active_neurons': int((delta > 0).sum()),
                   'kc_active_ge1': int((delta[g['kc']] >= 1).sum()),
                   'kc_active_ge2': int((delta[g['kc']] >= 2).sum()),
                   'groups_spikes': {k: int(delta[v].sum()) for k, v in g.items()}}
            stages.append(row)
            print('[stability] ' + json.dumps(row), flush=True)
        (out / 'stability.json').write_text(json.dumps({'scope': args.scope, 'stabilized': args.stabilized,
            'odor_type': str(odor_type), 'input_neurons': len(targets), 'structural_edits': edits,
            'groups': {k: len(v) for k, v in g.items()}, 'stages': stages}, indent=2) + '\n', encoding="utf-8", newline="\n")
    (out / "profile.json").write_text(json.dumps({"network_builds": builds, "runs": profile,
        "dt_ms": 0.1, "source_sha256": sha256(source), "seed": args.seed}, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    args = arguments()
    name = run_name(args)
    out = ROOT / ".cache/research/runs" / name
    if args.worker:
        worker(args, out)
        return
    import psutil
    # Verify pins before executing cached upstream Python.
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for s in manifest["sources"]:
        for f in s["files"]:
            if sha256(ROOT / f["cache_path"]) != f["sha256"]:
                raise RuntimeError(f"Changed upstream file: {f['path']}")
    if out.exists():
        raise RuntimeError(f"Run already exists: {out}. Choose a new seed or archive this run first.")
    out.mkdir(parents=True)
    env = os.environ.copy()
    env.update({"MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1", "PYTHONHASHSEED": str(args.seed),
                "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1"})
    command = [sys.executable, "-m", "research.run", args.protocol, "--worker", "--seed", str(args.seed),
               "--trials", str(args.trials), "--gain", str(args.gain), "--scope", args.scope]
    if args.stabilized:
        command.append('--stabilized')
    t0 = time.perf_counter()
    peak_worker = peak_tree = 0
    peak_phase = None
    with (out / "run.log").open("w", encoding="utf-8") as log:
        p = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        process = psutil.Process(p.pid)
        while p.poll() is None:
            try:
                rss = process.memory_info().rss
                children = process.children(recursive=True)
                tree_rss = rss + sum(c.memory_info().rss for c in children if c.is_running())
                peak_worker = max(peak_worker, rss)
                if tree_rss > peak_tree:
                    compiler = any(c.name() in ('clang', 'clang++', 'cc', 'gcc', 'g++', 'cc1', 'ld') for c in children)
                    peak_tree, peak_phase = tree_rss, "compilation" if compiler else "worker"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            time.sleep(0.05)
    summary = {"recorded_at": datetime.now(timezone.utc).isoformat(),
               "run": name, "protocol": args.protocol, "seed": args.seed, "gain": args.gain,
               "trials": args.trials, "exit_code": p.returncode,
               "wall_seconds": time.perf_counter() - t0,
               "peak_worker_rss_bytes": peak_worker, "peak_process_tree_rss_bytes": peak_tree,
               "peak_tree_phase": peak_phase, "rss_sampling_seconds": 0.05,
               "environment": environment(), "log_path": str((out / "run.log").relative_to(ROOT)),
               "upstream_manifest_sha256": sha256(MANIFEST)}
    for filename in ("profile.json", "weights-summary.json", "meta.json", "stability.json"):
        if (out / filename).exists():
            summary[filename[:-5].replace("-", "_")] = json.loads((out / filename).read_text(encoding="utf-8"))
    if 'meta' in summary:
        summary['meta']['args']['model_dir'] = str((CACHE / 'shiu').relative_to(ROOT))
        summary['meta']['args']['out'] = str(out.relative_to(ROOT))
    for filename in ("results.jsonl", "episodes.jsonl"):
        if (out / filename).exists():
            summary[filename[:-6]] = [json.loads(line) for line in (out / filename).read_text(encoding="utf-8").splitlines()]
    if args.protocol == 'taste' and 'results' in summary:
        summary['results'] = normalize_taste(summary['results'], out, args.trials)
        summary['postprocessing'] = 'Rates recomputed from spike parquet, including silent trials; upstream NaN pivot cells become measured zero.'
    result_path = ROOT / "reports/results" / (name + ".json")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: summary[k] for k in ('run', 'exit_code', 'wall_seconds', 'peak_worker_rss_bytes', 'peak_process_tree_rss_bytes')}, indent=2))
    print(result_path.relative_to(ROOT), flush=True)
    if p.returncode:
        print((out / "run.log").read_text(encoding="utf-8")[-5000:])
        raise SystemExit(p.returncode)


if __name__ == "__main__":
    main()
