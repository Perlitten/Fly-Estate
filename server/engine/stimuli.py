"""Photo + listing → ORN stimulus codecs (R3).

Both codecs are artificial adapters: the simulated subgraph has only
olfactory inputs, so pictures and listing facts are mapped onto its 22 ORN
glomerulus classes. Nothing here claims a biological visual pathway.

Channel layout, fixed for every codec (engine channel order = R1 order):

* channels 0–15 — the photo. **Pure** (`photo-pure-v1`): the 8 × 8 RGB
  retina is converted to luminance (Rec. 709) and pooled into a 4 × 4 grid of
  2 × 2 blocks; block (row, col) drives channel row·4 + col at
  luminance × `MAX_HZ`. **Cyborg** (`photo-cyborg-v2`): the complete
  L2-normalised 512-d CLIP image embedding minus a frozen centre (the mean
  embedding of the stored photo corpus, identified by its SHA-256), again
  L2-normalised, is multiplied by a fixed Gaussian projection (seed
  `PROJECTION_SEED`) and squashed: rate = `MAX_HZ` · sigmoid(`GAIN` · z).
  Without centring, the component shared by all CLIP image embeddings
  dominates and every photo drives nearly the same rates (v1).
* channels 16–21 — the listing, identical for every photo of an apartment:
  price relative to the brief's hard limit, closeness to the preferred point,
  stated floor area, balcony/loggia, its stated size and shelter. Unknown
  values drive nothing and are reported as unknown in the provenance.

Rates are nonnegative and carry magnitude only: the spiking stimulus declares
no direction of preference. Human ratings are stored apart (`ratings`,
`comparisons` in `data/state.sqlite`), never enter a stimulus and are read
only by the score readout (`server.gallery.portfolio`) and, in R4, by
reinforcement. `PREFERENCES` records who declared each listing channel and,
for the rate baseline, which ones are positive by construction.

Episode duration and rates come from the engine (R1: 0.5 s, odours at
500 Hz); `MAX_HZ` matches the R1 odour rate.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np

from .base import Stimulus, digest

MAX_HZ = 500.0
PHOTO_CHANNELS = 16
CONTEXT = ("price", "proximity", "floor_area", "balcony", "balcony_size", "balcony_shelter")
CHANNELS = PHOTO_CHANNELS + len(CONTEXT)
CODECS = {"pure": "photo-pure-v1", "cyborg": "photo-cyborg-v2"}
EMBEDDING_DIM = 512
PROJECTION_SEED = 783
GAIN = 2.0
AREA_SCALE_M2 = 120.0
BALCONY_SCALE_M2 = 30.0
LUMA = (0.2126, 0.7152, 0.0722)


# Engineered projection and provenance of each listing channel. `rate_baseline`
# describes `server.brain`, whose projections for area and balcony are made
# positive on purpose; the spiking model only sees the magnitude.
PREFERENCES = {
    "price": {"projection": "listing price ÷ brief hard limit, clipped to [0, 1]",
              "declared_by": "client brief (hard limit)", "rate_baseline": "price above target, signed",
              "direction": "learned from ratings"},
    "proximity": {"projection": "1 / (1 + d / r); d = straight-line km to the preferred point, r = brief radius; "
                                "1 at the point, 0.5 at the radius",
                  "declared_by": "client brief (preferred point, radius)", "rate_baseline": "direction and distance",
                  "direction": "learned from ratings",
                  "accuracy": "d uses source coordinates or, for coord_kind 'area', the area centre"},
    "floor_area": {"projection": f"stated m² ÷ {AREA_SCALE_M2:g}, clipped to [0, 1]",
                   "declared_by": "owner, ROADMAP R3: floor area and room to fly are positive preferences",
                   "rate_baseline": "positive by construction", "direction": "positive (declared)"},
    "balcony": {"projection": "1 when the source states a balcony or loggia, otherwise unknown (0 Hz)",
                "declared_by": "owner, ROADMAP R3: outdoor space is a priority signal",
                "rate_baseline": "positive by construction", "direction": "positive (declared)"},
    "balcony_size": {"projection": f"stated balcony m² ÷ {BALCONY_SCALE_M2:g}, clipped to [0, 1]",
                     "declared_by": "owner, ROADMAP R3", "rate_baseline": "positive by construction",
                     "direction": "positive (declared)"},
    "balcony_shelter": {"projection": "1 when the source states a covered balcony, otherwise unknown (0 Hz)",
                        "declared_by": "owner, ROADMAP R3", "rate_baseline": "positive by construction",
                        "direction": "positive (declared)"},
}


class Center(NamedTuple):
    """Frozen mean CLIP embedding subtracted by the cyborg codec."""
    vector: np.ndarray
    sha256: str
    count: int

    @classmethod
    def of(cls, vector, count: int) -> "Center":
        data = np.asarray(vector, dtype="<f4")
        if data.shape != (EMBEDDING_DIM,):
            raise ValueError(f"expected a {EMBEDDING_DIM}-d centre, got {data.shape}")
        return cls(data.astype(np.float64), hashlib.sha256(data.tobytes()).hexdigest(), int(count))


def settings(mode: str, center: Center | None = None) -> dict:
    """Codec parameters that enter the cache key."""
    common = {"codec": CODECS[mode], "max_hz": MAX_HZ, "photo_channels": PHOTO_CHANNELS, "context": list(CONTEXT),
              "area_scale_m2": AREA_SCALE_M2, "balcony_scale_m2": BALCONY_SCALE_M2}
    if mode == "pure":
        return {**common, "retina": "8x8 RGB → Rec.709 luminance → 4x4 mean of 2x2"}
    return {**common, "embedding_dim": EMBEDDING_DIM, "projection_seed": PROJECTION_SEED, "gain": GAIN,
            "center_sha256": center.sha256 if center else None, "center_photos": center.count if center else None}


_projection: np.ndarray | None = None


def projection() -> np.ndarray:
    global _projection
    if _projection is None:
        _projection = np.random.default_rng(PROJECTION_SEED).normal(0, 1, (PHOTO_CHANNELS, EMBEDDING_DIM))
    return _projection


def pure_signals(retina) -> list[float]:
    rgb = np.asarray(retina, dtype=np.float64).reshape(8, 8, 3)
    luma = np.clip(rgb @ np.asarray(LUMA), 0, 1)
    return [float(x) for x in luma.reshape(4, 2, 4, 2).mean(axis=(1, 3)).ravel()]


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / max(float(np.linalg.norm(vector)), 1e-12)


def cyborg_signals(embedding, center: Center) -> list[float]:
    vector = np.asarray(embedding, dtype=np.float64)
    if vector.shape != (EMBEDDING_DIM,):
        raise ValueError(f"expected a {EMBEDDING_DIM}-d image embedding, got {vector.shape}")
    z = projection() @ _unit(_unit(vector) - center.vector)
    return [float(x) for x in 1 / (1 + np.exp(-GAIN * z))]


def distance_km(a, b) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    s = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(s)))


def context_signals(listing: dict, brief: dict) -> dict[str, dict]:
    """Listing facts in [0, 1] with their source; `value` None means unknown."""
    def unit(x):
        return round(min(max(float(x), 0.0), 1.0), 6)

    coords, size, balcony_size = listing.get("coords"), listing.get("size"), listing.get("balcony_size")
    distance = distance_km(brief["ideal"], coords) if coords else None
    return {
        "price": {"value": unit(listing["price"] / brief["ceiling"]), "source": "listing price ÷ brief hard limit"},
        "proximity": {"value": unit(1 / (1 + distance / brief["radius"])) if distance is not None else None,
                      "source": f"straight line to preferred point ({listing.get('coord_kind') or 'unknown'})",
                      "km": round(distance, 2) if distance is not None else None},
        "floor_area": {"value": unit(size / AREA_SCALE_M2) if size else None, "source": "listing field size"},
        "balcony": {"value": 1.0 if listing.get("balcony") else None, "source": "listing field balcony"},
        "balcony_size": {"value": unit(balcony_size / BALCONY_SCALE_M2) if balcony_size else None,
                         "source": "listing field balcony_size"},
        "balcony_shelter": {"value": 1.0 if listing.get("balcony_covered") is True else None,
                            "source": "listing field balcony_covered"},
    }


def encode(mode: str, photo: dict, listing: dict, brief: dict, channels: list[str],
           embedding=None, center: Center | None = None) -> tuple[Stimulus, dict]:
    """Stimulus for one photo of a listing plus its provenance."""
    if mode not in CODECS:
        raise ValueError(f"unknown mode {mode!r}")
    if len(channels) < CHANNELS:
        raise ValueError(f"{CODECS[mode]} needs {CHANNELS} input channels, engine has {len(channels)}")
    if mode == "pure":
        visual = pure_signals(photo["retina"])
    else:
        if embedding is None:
            raise LookupError("This photo has no CLIP embedding yet.")
        if center is None:
            raise LookupError("No CLIP centre is frozen yet; it is set on the first cyborg run.")
        visual = cyborg_signals(embedding, center)
    context = context_signals(listing, brief)
    values = visual + [context[name]["value"] or 0.0 for name in CONTEXT]
    rates = tuple((channel, round(v * MAX_HZ, 3)) for channel, v in zip(channels, values))
    provenance = {"photo_signals": [round(v, 6) for v in visual], "context": context,
                  "photo_channels": list(channels[:PHOTO_CHANNELS]),
                  "context_channels": dict(zip(CONTEXT, channels[PHOTO_CHANNELS:CHANNELS]))}
    if center is not None and mode == "cyborg":
        provenance["center_sha256"] = center.sha256
    return Stimulus(CODECS[mode], rates), provenance


def cache_key(photo_sha: str, stimulus: Stimulus, mode: str, engine_version: str, fingerprint: str,
              center: Center | None = None) -> str:
    return digest({"photo_sha256": photo_sha, "stimulus": stimulus.key(), "settings": settings(mode, center),
                   "engine_version": engine_version, "fingerprint": fingerprint})


def file_sha256(path: Path) -> str:
    digest_ = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest_.update(block)
    return digest_.hexdigest()
