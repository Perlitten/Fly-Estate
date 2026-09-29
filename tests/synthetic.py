"""Small synthetic olfactory→MB circuit with the real subgraph's data layout."""
import numpy as np

from server.engine import subgraph


def make_data(seed: int = 0, classes: int = 11) -> dict:
    rng = np.random.default_rng(seed)
    sizes = {"orn": classes * 8, "alln": 0, "alpn": classes * 3, "kc": 120, "apl": 0, "mbon": 6, "pam": 8, "ppl1": 0}
    group = np.concatenate([np.full(n, k, dtype=np.int8) for k, n in enumerate(sizes.values())])
    idx = {name: np.flatnonzero(group == k) for k, name in enumerate(subgraph.GROUPS)}
    orn_class = np.full(len(group), -1, dtype=np.int16)
    orn_class[idx["orn"]] = np.repeat(np.arange(classes), 8)
    pre, post, weight = [], [], []

    def connect(a, b, w):
        pre.append(a); post.append(b); weight.append(w)

    for c in range(classes):
        for o in idx["orn"][orn_class[idx["orn"]] == c]:
            for p in idx["alpn"][c * 3:(c + 1) * 3]:
                connect(o, p, 4.0)
    for k in idx["kc"]:
        for p in rng.choice(idx["alpn"], 6, replace=False):
            connect(p, k, 8.0)
        for m in idx["mbon"]:
            connect(k, m, 0.5)
    for m in idx["mbon"]:
        connect(m, idx["kc"][0], -0.5)  # a non-plastic synapse that must never change
    return {"root_ids": np.arange(len(group), dtype=np.int64) + 10**17, "pre": np.asarray(pre, dtype=np.int32),
            "post": np.asarray(post, dtype=np.int32), "weight_mv": np.asarray(weight), "group": group,
            "orn_class": orn_class, "orn_types": np.asarray([f"ORN_T{c}" for c in range(classes)]),
            "meta": {"synthetic": True}, "sha256": f"synthetic-{seed}"}
