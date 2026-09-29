"""Replay the R1 conditioning protocol on the application engine and compare with R1.

The R1 run used Brian2; this engine reimplements the same LIF equations in
NumPy. Poisson draws differ, so the comparison is statistical: odor selection
must match exactly, activity and learning effects within stated tolerances.

    .venv/Scripts/python -m research.engine_parity   (Windows)
    .venv/bin/python -m research.engine_parity       (macOS/Linux)
"""
from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from server.engine.base import Stimulus
from server.engine.olfactory import OlfactoryMBEngine, Params

ROOT = Path(__file__).resolve().parents[1]
R1 = ROOT / "reports/results/learning_g20_s0.json"
OUTPUT = ROOT / "reports/results/engine_parity.json"


def odors(types: list[str], seed: int, nc: int):
    """Odor sets exactly as learning_driver_mb.py draws them."""
    rng = np.random.default_rng(seed)
    order = list(rng.permutation(min(len(types), 3 * nc)))
    a = [types[order[k]] for k in range(0, 2 * nc, 2)]
    b = [types[order[k]] for k in range(1, 2 * nc, 2)]
    fresh = [types[order[k]] for k in range(2 * nc, min(len(order), 3 * nc))]
    ks = sorted({round(nc * f) for f in (0.75, 0.5, 0.25, 0.0)}, reverse=True)
    return a, b, fresh, ks


def main() -> int:
    r1 = json.loads(R1.read_text())
    args = r1["meta"]["args"]
    params = Params(kcmbon_gain=args["kcmbon_gain"], epi_ms=args["epi_sec"] * 1000, dan_hz=args["dan_hz"],
                    kc_thresh=args["kc_thresh"], pam_gate_hz=args["pam_gate_hz"], eta=args["eta"])
    started = time.perf_counter()
    engine = OlfactoryMBEngine(params, seed=args["seed"])
    startup = time.perf_counter() - started
    a, b, fresh, ks = odors(engine.orn_types, args["seed"], args["n_classes"])
    stim = {"A": a, "B": b, **{f"probe{k}": a[:k] + fresh[:args["n_classes"] - k] for k in ks}}
    stimuli = {k: Stimulus("r1-parity", tuple((t, args["orn_hz"]) for t in v)) for k, v in stim.items()}

    plan = [(f"pre_{s}{r}", s, False) for r in (0, 1) for s in "AB"]
    plan += [row for c in range(args["n_pair"]) for row in ((f"train{c}_A+US", "A", True), (f"train{c}_B", "B", False))]
    plan += [(f"post_{s}{r}", s, False) for r in (0, 1) for s in "AB"]
    plan += [(f"probe_{k}", f"probe{k}", False) for k in ks]
    episodes = []
    for name, key, us in plan:
        result = engine.run_episode(stimuli[key], reward=us, carry_state=True)
        episodes.append({"episode": name, "kc_active": result.kc_active, "pam_hz": round(result.pam_hz, 2),
                         "mbon_spk": sum(result.mbon_spikes), "total_spikes": result.total_spikes,
                         "plast": result.plasticity_applied, "wall_s": round(result.wall_seconds, 3)})
        print(f"{name:14s} KC={result.kc_active:4d} PAM={result.pam_hz:6.2f} "
              f"MBON={episodes[-1]['mbon_spk']:5d} {result.wall_seconds:.2f}s", flush=True)

    def mbon(rows, prefix):
        return float(np.mean([e["mbon_spk"] for e in rows if e["episode"].startswith(prefix)]))

    def effects(rows):
        pre_a, post_a = mbon(rows, "pre_A"), mbon(rows, "post_A")
        pre_b, post_b = mbon(rows, "pre_B"), mbon(rows, "post_B")
        return {"pre_A_mbon": pre_a, "post_A_mbon": post_a, "pre_B_mbon": pre_b, "post_B_mbon": post_b,
                "A_suppression": 1 - post_a / pre_a, "B_change": post_b / pre_b - 1,
                "pre_A0_kc_active": next(e["kc_active"] for e in rows if e["episode"] == "pre_A0")}

    ours, theirs = effects(episodes), effects(r1["episodes"])
    weights = engine.weight_summary()
    total_weights = engine.net.graph.data
    first_total = episodes[0]["total_spikes"]
    r1_first = r1["profile"]["runs"][0]["spikes"]
    checks = {
        "odor_sets_identical": [a, b, fresh, ks] == [r1["meta"][k] for k in ("A_types", "B_types", "fresh_types", "probe_ks")],
        "plastic_synapses_identical": weights["plastic_synapses"] == r1["meta"]["n_plastic"],
        "first_episode_spikes_within_5pct": abs(first_total / r1_first - 1) < 0.05,
        "pre_A_kc_active_within_10pct": abs(ours["pre_A0_kc_active"] / theirs["pre_A0_kc_active"] - 1) < 0.10,
        "pre_A_mbon_within_10pct": abs(ours["pre_A_mbon"] / theirs["pre_A_mbon"] - 1) < 0.10,
        "A_suppression_at_least_90pct": ours["A_suppression"] >= 0.90,
        "B_change_within_15pct": abs(ours["B_change"]) < 0.15,
        "changed_synapses_within_15pct": abs(weights["changed_synapses"] / r1["weights_summary"]["learning_modified_pairs"] - 1) < 0.15,
        "changes_only_kc_mbon": bool(np.count_nonzero(np.delete(total_weights, engine.plastic)
                                                      != np.delete(OlfactoryMBEngine(params).net.graph.data, engine.plastic)) == 0),
    }
    walls = [e["wall_s"] for e in episodes]
    report = {
        "reference": R1.relative_to(ROOT).as_posix(), "engine": engine.describe(), "params": asdict(params),
        "odors": {"A": a, "B": b, "fresh": fresh, "probe_ks": ks},
        "effects": {"engine": ours, "r1_brian2": theirs},
        "first_episode_spikes": {"engine": first_total, "r1_brian2": r1_first},
        "weights": {**weights, "r1_changed_synapses": r1["weights_summary"]["learning_modified_pairs"]},
        "runtime": {"startup_s": round(startup, 2), "episode_mean_s": round(float(np.mean(walls)), 3),
                    "episode_max_s": round(float(np.max(walls)), 3), "episodes": len(walls),
                    "note": "episode wall time includes the 150 ms washout"},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "os": platform.platform(),
                        "processor": platform.processor()},
        "checks": checks, "passed": all(checks.values()), "episodes": episodes,
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"effects": report["effects"], "weights": report["weights"], "runtime": report["runtime"],
                      "checks": checks}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
