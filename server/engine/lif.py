"""Vectorised leaky integrate-and-fire network with Shiu et al. parameters.

The per-step schedule follows Brian2's default order as used by the upstream
model: state update → threshold → delayed synaptic delivery → external
Poisson drive → reset. Voltages are in mV, dt = 0.1 ms, exact linear
integration of dv/dt = (v0 − v + g)/τm and dg/dt = −g/τs. Refractory
neurons neither integrate nor receive synaptic input ("unless refractory");
externally driven targets have zero refractory period, as upstream.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse

DT_MS = 0.1
V_REST = -52.0
V_RESET = -52.0
V_THRESHOLD = -45.0
TAU_MEMBRANE_MS = 20.0
TAU_SYNAPSE_MS = 5.0
REFRACTORY_STEPS = 22  # 2.2 ms
DELAY_STEPS = 18  # 1.8 ms
POISSON_WEIGHT_MV = 0.275 * 250  # w_syn × f_poi

A = np.exp(-DT_MS / TAU_MEMBRANE_MS)
B = np.exp(-DT_MS / TAU_SYNAPSE_MS)
COUPLING = TAU_SYNAPSE_MS / (TAU_SYNAPSE_MS - TAU_MEMBRANE_MS) * (B - A)


class LifNetwork:
    """Mutable network state. Weights live in `self.graph.data` (pre × post CSR)."""

    def __init__(self, n: int, pre: np.ndarray, post: np.ndarray, weight_mv: np.ndarray):
        graph = sparse.csr_matrix((np.asarray(weight_mv, dtype=np.float64), (pre, post)), shape=(n, n))
        graph.sum_duplicates()
        graph.sort_indices()
        self.graph = graph
        self.n = n
        self.no_refractory = np.zeros(n, dtype=bool)
        self.reset_state()

    def reset_state(self) -> None:
        self.v = np.full(self.n, V_REST)
        self.g = np.zeros(self.n)
        self.last = np.full(self.n, -10**9, dtype=np.int64)
        self.queue: list[np.ndarray] = [np.empty(0, dtype=np.int64) for _ in range(DELAY_STEPS + 1)]
        self.step = 0

    def state(self) -> dict[str, np.ndarray]:
        """Dynamic state, with spike times relative to the current step."""
        pending = np.full((DELAY_STEPS + 1, self.n), False)
        for slot, spikes in enumerate(self.queue):
            pending[slot, spikes] = True
        return {"v": self.v.copy(), "g": self.g.copy(),
                "since_spike": np.minimum(self.step - self.last, 10**9), "pending": pending,
                "slot": np.int64(self.step % (DELAY_STEPS + 1))}

    def load_state(self, state: dict[str, np.ndarray]) -> None:
        self.v, self.g = state["v"].astype(np.float64), state["g"].astype(np.float64)
        # Re-anchor spike times so ring-buffer slots line up with the saved phase.
        self.step = int(state["slot"])
        self.last = self.step - state["since_spike"].astype(np.int64)
        self.queue = [np.flatnonzero(row) for row in state["pending"]]

    def run(self, steps: int, targets: np.ndarray, rates_hz: np.ndarray,
            rng: np.random.Generator, *, spike_bins: np.ndarray | None = None,
            bin_steps: int = 250, on_bin=None) -> np.ndarray:
        """Advance `steps` × 0.1 ms; returns spike counts per neuron."""
        counts = np.zeros(self.n, dtype=np.int32)
        targets = np.asarray(targets, dtype=np.int64)
        probability = np.asarray(rates_hz, dtype=np.float64) * DT_MS * 1e-3
        driven = probability > 0
        targets, probability = targets[driven], probability[driven]
        indptr, indices, data = self.graph.indptr, self.graph.indices, self.graph.data
        v, g, last, queue, n = self.v, self.g, self.last, self.queue, self.n
        slots = DELAY_STEPS + 1
        for tick in range(steps):
            step = self.step
            integrating = self.no_refractory | (step - last >= REFRACTORY_STEPS)
            np.copyto(v, V_REST + (v - V_REST) * A + g * COUPLING, where=integrating)
            np.multiply(g, B, out=g, where=integrating)
            spikes = np.flatnonzero(integrating & (v > V_THRESHOLD))
            queue[step % slots] = spikes
            arriving = queue[(step - DELAY_STEPS) % slots]  # empty until the first delay elapses
            if len(arriving):
                starts, ends = indptr[arriving], indptr[arriving + 1]
                sizes = ends - starts
                total = int(sizes.sum())
                if total:
                    edge = np.repeat(ends - sizes.cumsum(), sizes) + np.arange(total)
                    received = np.bincount(indices[edge], weights=data[edge], minlength=n)
                    g += received * integrating
            if len(targets):
                fired = targets[rng.random(len(targets)) < probability]
                v[fired] += POISSON_WEIGHT_MV
            v[spikes] = V_RESET
            g[spikes] = 0.0
            last[spikes] = step
            counts[spikes] += 1
            if spike_bins is not None:
                spike_bins[tick // bin_steps, spikes] += 1
                if on_bin and ((tick + 1) % bin_steps == 0 or tick + 1 == steps):
                    on_bin(tick // bin_steps + 1)
            self.step += 1
        return counts
