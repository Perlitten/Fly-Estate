"""Recorded spike counts, and their ID-based projection onto the anatomical view.

Counts stay lossless in the activity cache. Only the display uses a fixed
square-root scale: 20 spikes per 25 ms bin = maximum brightness. Neurons
outside the simulated subgraph have no activity assigned to them.
"""
from __future__ import annotations

import base64
import hashlib
import zlib
from functools import lru_cache
from pathlib import Path

import numpy as np

BIN_MS = 25.0
FORMAT = "spike-bins-1"
DISPLAY_MAX = 20.0


def pack(counts: np.ndarray, root_ids_sha256: str, duration_ms: float | None = None) -> dict:
    data = np.asarray(counts, dtype="<u2")
    return {"format": FORMAT, "neurons": data.shape[1], "bins": data.shape[0],
            "bin_ms": BIN_MS, "duration_ms": duration_ms or len(data) * BIN_MS,
            "root_ids_sha256": root_ids_sha256,
            "counts": base64.b64encode(zlib.compress(data.tobytes(), level=1)).decode("ascii")}


@lru_cache(maxsize=2)
def _ids(path: str, modified: int) -> tuple[np.ndarray, str]:
    with np.load(path, allow_pickle=False) as data:
        ids = data["root_ids"]
    return ids, hashlib.sha256(ids.tobytes()).hexdigest()


def project(trace: dict, anatomical_ids: np.ndarray, subgraph_path: Path) -> dict:
    ids, sha = _ids(str(subgraph_path), subgraph_path.stat().st_mtime_ns)
    if trace["format"] != FORMAT or trace["root_ids_sha256"] != sha or trace["neurons"] != len(ids):
        raise ValueError("Replay neuron IDs differ from the prepared engine. Run the model again.")
    counts = np.frombuffer(zlib.decompress(base64.b64decode(trace["counts"])), dtype="<u2")
    counts = counts.reshape(trace["bins"], len(ids))
    # Search by actual root ID, never by an assumed common ordering.
    order = np.argsort(anatomical_ids)
    positions = np.searchsorted(anatomical_ids[order], ids)
    valid = positions < len(order)
    indices = np.full(len(ids), -1, dtype=np.int32)
    indices[valid] = order[positions[valid]]
    valid &= anatomical_ids[np.maximum(indices, 0)] == ids
    indices[~valid] = -1
    display = np.rint(255 * np.sqrt(np.minimum(counts / DISPLAY_MAX, 1))).astype(np.uint8)
    return {"available": True, "format": FORMAT, "indices": indices.tolist(),
            "bins": int(trace["bins"]), "bin_ms": float(trace["bin_ms"]),
            "duration_ms": float(trace["duration_ms"]),
            "values": base64.b64encode(display.tobytes()).decode("ascii"),
            "simulated_neurons": len(ids), "mapped_neurons": int(valid.sum()),
            "display_max_spikes_per_bin": DISPLAY_MAX,
            "total_spikes": int(counts.sum()), "root_ids_sha256": sha}
