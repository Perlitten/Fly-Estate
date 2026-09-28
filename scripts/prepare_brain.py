"""Build the actual v783 graph. No sampled or synthetic connections."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/brain"
OUT.mkdir(parents=True, exist_ok=True)
ann = pd.read_csv(ROOT / "data/raw/annotations_v3.1.0.tsv", sep="\t", low_memory=False)
ann = ann.drop_duplicates("root_id").sort_values("root_id").reset_index(drop=True)
ids = ann.root_id.to_numpy(dtype=np.int64)
print(f"Annotations: {len(ids):,} neurons", flush=True)
edges = pd.read_feather(ROOT / "data/raw/proofread_connections_783.feather",
                       columns=["pre_pt_root_id", "post_pt_root_id", "syn_count"])
index = pd.Index(ids)
pre = index.get_indexer(edges.pre_pt_root_id)
post = index.get_indexer(edges.post_pt_root_id)
valid = (pre >= 0) & (post >= 0) & (pre != post)
counts = sparse.csr_matrix((edges.syn_count.to_numpy()[valid].astype(np.float32),
                          (post[valid], pre[valid])), shape=(len(ids), len(ids)))
counts.sum_duplicates()
counts.data[counts.data < 5] = 0
counts.eliminate_zeros()
synapses = int(counts.sum())
incoming = np.asarray(counts.sum(axis=1)).ravel()
weights = sparse.diags(1 / np.maximum(incoming, 1)) @ counts
sparse.save_npz(OUT / "weights.npz", weights.astype(np.float32))
classes = ann.cell_class.fillna("").to_numpy(dtype=str)
types = ann.cell_type.fillna("").to_numpy(dtype=str)
flows = ann.flow.fillna("").to_numpy(dtype=str)
superclasses = ann.super_class.fillna("").to_numpy(dtype=str)
visual = np.flatnonzero((classes == "visual") & (superclasses == "sensory"))
if not len(visual):
    raise RuntimeError("No annotated visual sensory neurons found")
cyborg = np.flatnonzero(superclasses == "visual_projection")
if not len(cyborg):
    cyborg = visual.copy()
nav = np.flatnonzero((classes == "CX") & (ann.cell_sub_class.fillna("").to_numpy() == "ring neuron"))
metadata = np.flatnonzero(classes == "ALPN")
mbon = np.flatnonzero(classes == "MBON")
cx = np.flatnonzero(classes == "CX")
cx_types = sorted(set(types[cx]) - {""})
rows, cols = [], []
for row, t in enumerate(cx_types):
    nodes = np.flatnonzero((types == t) & (classes == "CX"))
    rows.extend([row] * len(nodes)); cols.extend(nodes.tolist())
pool = sparse.csr_matrix((np.ones(len(rows), np.float32), (rows, cols)), shape=(len(cx_types), len(ids)))
pool = sparse.diags(1 / np.maximum(np.asarray(pool.sum(axis=1)).ravel(), 1)) @ pool
sparse.save_npz(OUT / "cx_pool.npz", pool.astype(np.float32))
np.savez_compressed(OUT / "neurons.npz", ids=ids, classes=classes, types=types, visual=visual,
                    cyborg=cyborg, nav=nav, metadata=metadata, mbon=mbon,
                    positions=ann[["pos_x", "pos_y", "pos_z"]].fillna(0).to_numpy(np.float32))
summary = {"dataset": "FAFB v783", "annotations": "v3.1.0", "neurons": len(ids),
           "connections": int(weights.nnz), "synapses": synapses, "threshold": 5,
           "visual_inputs": len(visual), "cyborg_inputs": len(cyborg), "navigation_inputs": len(nav),
           "metadata_inputs": len(metadata), "mbon_outputs": len(mbon), "cx_output_types": len(cx_types),
           "groups": {name: int((classes == name).sum()) for name in ["visual", "Kenyon_Cell", "MBON", "CX", "DAN", "ALPN"]},
           "dynamics": "Positive, incoming-normalized synapse counts; 16 leaky tanh rate steps. Not electrophysiology.",
           "plasticity": "Artificial learned MBON/CX decision readout. KC→MBON biological plasticity is not implemented.",
           "sources": ["https://zenodo.org/records/10676866", "https://github.com/flyconnectome/flywire_annotations/tree/v3.1.0"]}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2), flush=True)
