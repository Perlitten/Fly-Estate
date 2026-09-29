"""Olfactory→mushroom-body subgraph selected in R1.

Reproduces fly-api `learning_driver_mb.py` + `model_ext.build_subnet` at the
pinned revision without Brian2: the same annotation groups, the same pinned
Shiu v783 connectivity and the same four structural edits, applied in the
same order. The result is cached in `data/engine/` with source checksums.

Prepare once: `python -m research.bootstrap`, then `python -m server.engine.subgraph`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / ".cache/research/upstream/shiu"
ANNOTATIONS = ROOT / "data/raw/annotations_v3.1.0.tsv"
OUTPUT = ROOT / "data/engine/olfactory_mb_v783.npz"
GROUPS = ("orn", "alln", "alpn", "kc", "apl", "mbon", "pam", "ppl1")
W_SYN_MV = 0.275  # Shiu default_params['w_syn']
FORMAT = 2
# The driver ranks ORN classes by -count through pandas `value_counts`; the
# order among equal counts depends on the pandas version (pandas 3 differs
# from the 2.x used in R1). This is the R1 order for annotations v3.1.0;
# build() uses it only while it is still a valid ranking by count.
R1_ORN_ORDER = (
    "ORN_DA1", "ORN_VA1d", "ORN_VA1v", "ORN_DL3", "ORN_VL1", "ORN_VM4", "ORN_VL2a", "ORN_DL1",
    "ORN_DM1", "ORN_VM5d", "ORN_VA2", "ORN_V", "ORN_DM3", "ORN_VA6", "ORN_DM2", "ORN_DM6",
    "ORN_DL4", "ORN_DL5", "ORN_DM5", "ORN_DM4", "ORN_DA4m", "ORN_DA4l",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(upstream: Path = UPSTREAM, annotations: Path = ANNOTATIONS) -> dict:
    import pandas as pd

    ann = pd.read_csv(annotations, sep="\t", low_memory=False,
                      usecols=["root_id", "super_class", "cell_class", "cell_type", "hemibrain_type"])
    cc, sc = ann.cell_class.fillna(""), ann.super_class.fillna("")
    ct, ht = ann.cell_type.fillna(""), ann.hemibrain_type.fillna("")
    completeness = pd.read_csv(upstream / "Completeness_783.csv", index_col=0)
    flyid2i = {fid: i for i, fid in enumerate(completeness.index)}

    def ids(mask):
        return [flyid2i[i] for i in ann.loc[mask, "root_id"].astype(int) if i in flyid2i]

    orn_mask = sc.str.contains("sensory") & cc.str.contains("olfactory")
    groups = {
        "orn": ids(orn_mask), "alln": ids(cc == "ALLN"), "alpn": ids(cc == "ALPN"),
        "kc": ids(cc.str.contains("Kenyon", case=False)), "apl": ids(ct == "APL"),
        "mbon": ids(ct.str.startswith("MBON") | ht.str.startswith("MBON")),
        "pam": ids(ct.str.startswith("PAM") | ht.str.startswith("PAM")),
        "ppl1": ids(ct.str.startswith("PPL1") | ht.str.startswith("PPL1")),
    }
    keep = np.asarray(sorted({i for v in groups.values() for i in v}), dtype=np.int64)
    old2new = np.full(len(completeness), -1, dtype=np.int64)
    old2new[keep] = np.arange(len(keep))

    con = pd.read_parquet(upstream / "Connectivity_783.parquet")
    pre_full = con["Presynaptic_Index"].to_numpy()
    post_full = con["Postsynaptic_Index"].to_numpy()
    inside = np.isin(pre_full, keep) & np.isin(post_full, keep)
    pre = old2new[pre_full[inside]].astype(np.int32)
    post = old2new[post_full[inside]].astype(np.int32)
    weight = con["Excitatory x Connectivity"].to_numpy()[inside].astype(np.float64) * W_SYN_MV

    g = {k: np.asarray(sorted(old2new[i] for i in v), dtype=np.int32) for k, v in groups.items()}
    dan = np.concatenate([g["pam"], g["ppl1"]])
    edits = {}
    m = np.isin(pre, dan); weight[m] = 0; edits["dan_outputs"] = int(m.sum())
    m = np.isin(pre, g["kc"]) & np.isin(post, g["kc"]); weight[m] = 0; edits["kc_to_kc"] = int(m.sum())
    m = np.isin(post, g["orn"]); weight[m] = 0; edits["orn_inputs"] = int(m.sum())
    m = np.isin(pre, g["alln"]) & (weight > 0); weight[m] = 0; edits["alln_excitatory_outputs"] = int(m.sum())

    # ORN glomerulus classes, ranked as in the R1 run of the driver.
    orn = ann[orn_mask]
    counts = orn.cell_type.value_counts()
    eligible = {t for t in counts.index if counts[t] >= 40}
    pinned = (set(R1_ORN_ORDER) == eligible
              and all(counts[a] >= counts[b] for a, b in zip(R1_ORN_ORDER, R1_ORN_ORDER[1:])))
    orn_types = list(R1_ORN_ORDER) if pinned else sorted(eligible, key=lambda t: (-counts[t], t))
    root_ids = completeness.index.to_numpy(dtype=np.int64)[keep]
    type_of = dict(zip(orn.root_id.astype(int), orn.cell_type))
    orn_class = np.full(len(keep), -1, dtype=np.int16)
    type_index = {t: k for k, t in enumerate(orn_types)}
    for new, rid in enumerate(root_ids):
        if rid in type_of and type_of[rid] in type_index:
            orn_class[new] = type_index[type_of[rid]]
    group = np.full(len(keep), -1, dtype=np.int8)
    for k, name in enumerate(GROUPS):
        group[g[name]] = k  # later groups win; the upstream groups are disjoint in practice

    return {
        "root_ids": root_ids, "pre": pre, "post": post, "weight_mv": weight,
        "group": group, "orn_class": orn_class, "orn_types": np.asarray(orn_types),
        "meta": {
            "format": FORMAT, "neurons": int(len(keep)), "directed_pairs": int(len(pre)),
            "groups": {k: int(len(v)) for k, v in g.items()}, "structural_edits": edits,
            "weight_unit": "mV", "w_syn_mv": W_SYN_MV,
            "orn_order": "r1-pinned" if pinned else "count-then-name",
            "sources": {
                "Completeness_783.csv": sha256(upstream / "Completeness_783.csv"),
                "Connectivity_783.parquet": sha256(upstream / "Connectivity_783.parquet"),
                annotations.name: sha256(annotations),
            },
            "reproduces": "fly-api a6ad07a8 experiments/learning/learning_driver_mb.py",
        },
    }


def save(data: dict, path: Path = OUTPUT) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    arrays = {k: v for k, v in data.items() if k != "meta"}
    with tmp.open("wb") as f:
        np.savez_compressed(f, meta=np.frombuffer(json.dumps(data["meta"]).encode(), dtype=np.uint8), **arrays)
    tmp.replace(path)
    return sha256(path)


def load(path: Path = OUTPUT) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path.relative_to(ROOT)} is missing. Run `python -m research.bootstrap` "
            "and `python -m server.engine.subgraph`.")
    with np.load(path, allow_pickle=False) as saved:
        data = {k: saved[k] for k in saved.files}
    data["meta"] = json.loads(data["meta"].tobytes())
    data["sha256"] = sha256(path)
    return data


if __name__ == "__main__":
    built = build()
    digest = save(built)
    print(json.dumps({**built["meta"], "sha256": digest}, indent=2))
