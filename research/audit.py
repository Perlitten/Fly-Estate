"""Audit upstream indices, signed weights and the local v783 annotations."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.bootstrap import ROOT, CACHE, sha256


def groups(ann: pd.DataFrame, comp: pd.DataFrame) -> dict[str, np.ndarray]:
    cc = ann.cell_class.fillna("")
    sc = ann.super_class.fillna("")
    ct = ann.cell_type.fillna("")
    ht = ann.hemibrain_type.fillna("")
    masks = {
        "orn": sc.str.contains("sensory") & cc.str.contains("olfactory"),
        "alln": cc == "ALLN", "alpn": cc == "ALPN",
        "kc": cc.str.contains("Kenyon", case=False), "apl": ct == "APL",
        "mbon": ct.str.startswith("MBON") | ht.str.startswith("MBON"),
        "pam": ct.str.startswith("PAM") | ht.str.startswith("PAM"),
        "ppl1": ct.str.startswith("PPL1") | ht.str.startswith("PPL1"),
    }
    index = pd.Index(comp.index)
    result = {}
    for name, mask in masks.items():
        values = index.get_indexer(ann.loc[mask, "root_id"].astype(np.int64))
        result[name] = np.unique(values[values >= 0])
    return result


def main() -> None:
    ann_path = ROOT / "data/raw/annotations_v3.1.0.tsv"
    if not ann_path.exists():
        raise RuntimeError("Run pnpm setup --no-seed first to prepare pinned annotations")
    ann = pd.read_csv(ann_path, sep="\t", low_memory=False)
    ann_ids = ann.root_id.astype(np.int64).to_numpy()
    report = {"annotations": {"revision": "v3.1.0", "neurons": len(ann_ids),
                               "sha256": sha256(ann_path)}, "versions": {}}
    for version in (630, 783):
        comp_name = "2023_03_23_completeness_630_final.csv" if version == 630 else "Completeness_783.csv"
        con_name = "2023_03_23_connectivity_630_final.parquet" if version == 630 else "Connectivity_783.parquet"
        comp = pd.read_csv(CACHE / "shiu" / comp_name, index_col=0)
        con = pd.read_parquet(CACHE / "shiu" / con_name)
        ids = comp.index.to_numpy(dtype=np.int64)
        pre = con.Presynaptic_Index.to_numpy(dtype=np.int64)
        post = con.Postsynaptic_Index.to_numpy(dtype=np.int64)
        valid = (pre >= 0) & (post >= 0) & (pre < len(ids)) & (post < len(ids))
        if not valid.all():
            raise RuntimeError(f"v{version}: out-of-range indices")
        if not (np.array_equal(ids[pre], con.Presynaptic_ID.to_numpy())
                and np.array_equal(ids[post], con.Postsynaptic_ID.to_numpy())):
            raise RuntimeError(f"v{version}: root IDs and connection indices disagree")
        if comp.index.has_duplicates or con.duplicated(["Presynaptic_Index", "Postsynaptic_Index"]).any():
            raise RuntimeError(f"v{version}: duplicate neurons/connections")
        signed = con["Excitatory x Connectivity"].to_numpy()
        counts = con.Connectivity.to_numpy()
        row = {
            "neurons": len(ids), "directed_pairs": len(con),
            "synapse_count": int(counts.sum()), "minimum_connection_count": int(counts.min()),
            "self_connections": int((pre == post).sum()),
            "positive_pairs": int((signed > 0).sum()), "negative_pairs": int((signed < 0).sum()),
            "zero_pairs": int((signed == 0).sum()),
            "positive_synapse_mass": int(counts[signed > 0].sum()),
            "negative_synapse_mass": int(counts[signed < 0].sum()),
            "annotation_ids_matched": int(np.isin(ann_ids, ids).sum()),
            "annotation_ids_missing_count": int((~np.isin(ann_ids, ids)).sum()),
            "upstream_ids_without_annotation_count": int((~np.isin(ids, ann_ids)).sum()),
            "annotation_ids_missing_from_upstream": [str(x) for x in ann_ids[~np.isin(ann_ids, ids)][:None if version == 783 else 20]],
            "upstream_ids_without_annotation": [str(x) for x in ids[~np.isin(ids, ann_ids)][:None if version == 783 else 20]],
            "missing_id_lists_complete": version == 783,
            "index_root_consistency": True,
        }
        if version == 783:
            g = groups(ann, comp)
            keep = np.unique(np.concatenate(list(g.values())))
            row["learning_groups"] = {k: len(v) for k, v in g.items()}
            row["learning_subgraph_neurons"] = len(keep)
            row["learning_subgraph_pairs"] = int((np.isin(pre, keep) & np.isin(post, keep)).sum())
        report["versions"][str(version)] = row
        print(f"v{version}: {len(ids):,} neurons, {len(con):,} pairs, {counts.sum():,} synapses", flush=True)
    report["application_graph"] = json.loads((ROOT / "data/brain/summary.json").read_text(encoding="utf-8"))
    path = ROOT / "reports/results/connectome-audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
