"""Engine-neutral contract between the app and a neural simulator."""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

import numpy as np


def digest(value) -> str:
    """Stable SHA-256 of JSON-compatible data."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Stimulus:
    """Input rates for named channels, produced by a versioned codec."""

    codec: str
    rates_hz: tuple[tuple[str, float], ...]

    def key(self) -> str:
        return digest({"codec": self.codec, "rates_hz": [[k, round(v, 6)] for k, v in self.rates_hz]})


@dataclass
class EpisodeResult:
    group_spikes: dict[str, int]
    mbon_spikes: list[int]
    kc_active: int
    kc_active_fraction: float
    pam_hz: float
    total_spikes: int
    wall_seconds: float
    plasticity_applied: bool = False
    changed_synapses: int = 0
    checkpoint: str = ""
    kc_active_ids: list[int] = field(default_factory=list, repr=False)

    def to_json(self, ids: bool = False) -> dict:
        row = asdict(self)
        if not ids:
            row.pop("kc_active_ids")
        return row


@dataclass
class Checkpoint:
    """Everything needed to continue an engine exactly: arrays plus JSON metadata."""

    arrays: dict[str, np.ndarray]
    meta: dict


class SimulationEngine(ABC):
    name: str
    version: str

    @abstractmethod
    def channels(self) -> list[str]:
        """Input channel names a stimulus may drive."""

    @abstractmethod
    def run_episode(self, stimulus: Stimulus, *, reward: bool = False, seed: int | None = None) -> EpisodeResult:
        """Simulate one episode; with `reward`, apply the engine's reinforcement rule."""

    @abstractmethod
    def fingerprint(self) -> str:
        """Hash of everything that changes outputs: weights, parameters and version."""

    @abstractmethod
    def checkpoint(self) -> Checkpoint: ...

    @abstractmethod
    def restore(self, checkpoint: Checkpoint) -> None: ...

    def describe(self) -> dict:
        return {"name": self.name, "version": self.version, "fingerprint": self.fingerprint()}
