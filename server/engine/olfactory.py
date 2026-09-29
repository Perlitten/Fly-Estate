"""Persistent LIF engine for the edited olfactory→mushroom-body subgraph (R1).

Episode protocol and plasticity follow fly-api `learning_driver_mb.py`:
0.5 s of Poisson drive on ORN classes (plus PAM dopamine drive when
rewarded), counts from that window only, then a 150 ms washout. With reward,
if PAMs fire at ≥ the gate rate, KC→MBON synapses from KCs active in the
episode are depressed: w *= 1 − eta. Only those synapses ever change.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass

import numpy as np

from . import subgraph
from .base import Checkpoint, EpisodeResult, SimulationEngine, Stimulus, digest
from .lif import DT_MS, LifNetwork

VERSION = "olfactory-mb-lif-1"


@dataclass(frozen=True)
class Params:
    kcmbon_gain: float = 20.0
    epi_ms: float = 500.0
    washout_ms: float = 150.0
    dan_hz: float = 60.0
    kc_thresh: int = 1
    pam_gate_hz: float = 1.0
    eta: float = 0.5


class OlfactoryMBEngine(SimulationEngine):
    name = "olfactory-mb"
    version = VERSION

    def __init__(self, params: Params = Params(), seed: int = 0, data: dict | None = None):
        data = data if data is not None else subgraph.load()
        self.params, self.seed = params, seed
        self.source_sha = data["sha256"]
        self.root_ids = data["root_ids"]
        self.root_ids_sha = hashlib.sha256(self.root_ids.tobytes()).hexdigest()
        self.orn_types = [str(t) for t in data["orn_types"]]
        group = data["group"]
        self.groups = {name: np.flatnonzero(group == k) for k, name in enumerate(subgraph.GROUPS)}
        self.orn_by_type = {t: np.flatnonzero(data["orn_class"] == k) for k, t in enumerate(self.orn_types)}

        weight = data["weight_mv"].astype(np.float64).copy()
        is_kc = np.zeros(len(group), dtype=bool); is_kc[self.groups["kc"]] = True
        is_mbon = np.zeros(len(group), dtype=bool); is_mbon[self.groups["mbon"]] = True
        weight[is_kc[data["pre"]] & is_mbon[data["post"]]] *= params.kcmbon_gain
        self.net = LifNetwork(len(group), data["pre"], data["post"], weight)
        # Upstream sets rfc = 0 on every Poisson target. ORNs have no inputs
        # after the structural edits, so exempting all of them is equivalent.
        self.net.no_refractory[self.groups["orn"]] = True
        self.net.no_refractory[self.groups["pam"]] = True

        graph = self.net.graph
        rows = np.repeat(np.arange(graph.shape[0]), np.diff(graph.indptr))
        self.plastic = np.flatnonzero(is_kc[rows] & is_mbon[graph.indices])
        self.plastic_pre = rows[self.plastic]
        self.base_plastic = graph.data[self.plastic].copy()
        self.rng = np.random.default_rng(seed)
        self.history: list[dict] = []
        self._fingerprint: str | None = None

    # -- contract ---------------------------------------------------------
    def channels(self) -> list[str]:
        return list(self.orn_types)

    def fingerprint(self) -> str:
        if self._fingerprint is None:
            h = hashlib.sha256()
            h.update(json.dumps({"version": VERSION, "params": asdict(self.params),
                                 "source": self.source_sha}, sort_keys=True).encode())
            h.update(np.ascontiguousarray(self.net.graph.data[self.plastic]).tobytes())
            self._fingerprint = h.hexdigest()
        return self._fingerprint

    def run_episode(self, stimulus: Stimulus, *, reward: bool = False, seed: int | None = None,
                    carry_state: bool = False) -> EpisodeResult:
        """One episode.

        Default (`carry_state=False`) is a fresh trial: all dynamic state is
        reset and, with `seed`, the result depends only on stimulus, seed and
        weights. `carry_state=True` keeps pending spikes and refractory timers
        and resets only v and g, as the upstream driver does between episodes.
        """
        p, net = self.params, self.net
        unknown = [name for name, _ in stimulus.rates_hz if name not in self.orn_by_type]
        if unknown:
            raise ValueError(f"unknown input channels: {unknown}")
        if carry_state:
            net.v[:] = -52.0
            net.g[:] = 0.0
        else:
            net.reset_state()
        rng = np.random.default_rng(seed) if seed is not None else self.rng
        targets, rates = [], []
        for name, hz in stimulus.rates_hz:
            if hz > 0:
                targets.append(self.orn_by_type[name]); rates.append(np.full(len(targets[-1]), float(hz)))
        if reward and p.dan_hz > 0:
            targets.append(self.groups["pam"]); rates.append(np.full(len(self.groups["pam"]), p.dan_hz))
        targets_arr = np.concatenate(targets) if targets else np.empty(0, dtype=np.int64)
        rates_arr = np.concatenate(rates) if rates else np.empty(0)

        started = time.perf_counter()
        counts = net.run(round(p.epi_ms / DT_MS), targets_arr, rates_arr, rng)
        if carry_state and p.washout_ms > 0:
            net.run(round(p.washout_ms / DT_MS), np.empty(0, dtype=np.int64), np.empty(0), rng)
        wall = time.perf_counter() - started

        kc = self.groups["kc"]
        active = kc[counts[kc] >= p.kc_thresh]
        pam_hz = float(counts[self.groups["pam"]].mean() / (p.epi_ms / 1000))
        applied, changed = False, 0
        if reward and pam_hz >= p.pam_gate_hz and len(active):
            hot = self.plastic[np.isin(self.plastic_pre, active)]
            before = net.graph.data[hot].copy()
            net.graph.data[hot] *= 1 - p.eta
            changed = int(np.count_nonzero(net.graph.data[hot] != before))
            applied = True
            self._fingerprint = None
        result = EpisodeResult(
            group_spikes={name: int(counts[idx].sum()) for name, idx in self.groups.items()},
            mbon_spikes=[int(x) for x in counts[self.groups["mbon"]]],
            kc_active=int(len(active)), kc_active_fraction=float(len(active) / len(kc)),
            pam_hz=pam_hz, total_spikes=int(counts.sum()), wall_seconds=wall,
            plasticity_applied=applied, changed_synapses=changed, checkpoint=self.fingerprint(),
            kc_active_ids=[int(x) for x in active])
        if reward:
            self.history.append({"stimulus": stimulus.key(), "codec": stimulus.codec, "reward": True,
                                 "applied": applied, "changed_synapses": changed,
                                 "kc_active": result.kc_active, "pam_hz": round(pam_hz, 3),
                                 "checkpoint": result.checkpoint})
        return result

    def weight_summary(self) -> dict:
        current = self.net.graph.data[self.plastic]
        return {"plastic_synapses": int(len(self.plastic)),
                "changed_synapses": int(np.count_nonzero(current != self.base_plastic)),
                "weight_fraction": float(current.sum() / self.base_plastic.sum())}

    def checkpoint(self) -> Checkpoint:
        arrays = {"plastic_weight_mv": self.net.graph.data[self.plastic].copy(),
                  **{f"state_{k}": v for k, v in self.net.state().items()}}
        meta = {"engine": self.name, "version": VERSION, "params": asdict(self.params), "seed": self.seed,
                "source_sha256": self.source_sha, "root_ids_sha256": self.root_ids_sha,
                "plastic_synapses": int(len(self.plastic)), "rng": self.rng.bit_generator.state,
                "history": list(self.history), "fingerprint": self.fingerprint()}
        return Checkpoint(arrays, meta)

    def restore(self, checkpoint: Checkpoint) -> None:
        meta, arrays = checkpoint.meta, checkpoint.arrays
        expected = {"version": VERSION, "source_sha256": self.source_sha, "root_ids_sha256": self.root_ids_sha,
                    "params": asdict(self.params)}
        mismatched = [k for k, v in expected.items() if meta.get(k) != v]
        if mismatched:
            raise ValueError(f"checkpoint incompatible with this engine: {mismatched}")
        weights = arrays["plastic_weight_mv"]
        if weights.shape != self.plastic.shape:
            raise ValueError("checkpoint plastic synapse count differs")
        self.net.graph.data[self.plastic] = weights
        self.net.load_state({k[len("state_"):]: v for k, v in arrays.items() if k.startswith("state_")})
        self.seed = meta["seed"]
        self.rng = np.random.default_rng()
        self.rng.bit_generator.state = meta["rng"]
        self.history = list(meta["history"])
        self._fingerprint = None
        if self.fingerprint() != meta["fingerprint"]:
            raise ValueError("checkpoint fingerprint does not match restored weights")

    def describe(self) -> dict:
        return {**super().describe(), "neurons": int(self.net.n), "channels": len(self.orn_types),
                "params": asdict(self.params), **self.weight_summary()}


__all__ = ["OlfactoryMBEngine", "Params", "VERSION", "digest"]
