"""Build the translucent brain envelope drawn around the neuron cloud in BrainView.

The shell is derived from our own neuron positions, so it sits in exactly the
same coordinate frame as the points served by ``/api/brain/geometry``.

Pipeline
--------
1. Positions. ``data/brain/neurons.npz`` → ``positions`` (FlyWire v783 annotation
   anchors in 4×4×40 nm voxels). The transform is the one in
   ``server.brain.Brain.geometry``: scale to nm, drop invalid rows, subtract the
   median, divide by ``max(ptp) / 6`` (longest axis spans 6 scene units), flip Y.
   ``--check URL`` compares against the live endpoint.
2. Voxelise. A cubic-voxel grid over the padded bounding box, ``--grid`` cells
   along the longest axis (default 112). ``np.histogramdd`` counts neurons per
   voxel.
3. Blur. ``scipy.ndimage.gaussian_filter`` with ``--sigma`` voxels turns the
   counts into a smooth density.
4. Iso level. The level is chosen from the data, not by hand: it is the density
   value at the ``--coverage`` quantile of the density sampled at the neuron
   positions, i.e. roughly ``1 - coverage`` of neurons (the sparse strays) fall
   outside. Somata sit in a rind around neuropil, so the solid is then closed
   (``--close`` voxel ball), its internal cavities filled, and only connected
   parts holding at least 0.5 % of the voxels are kept (central brain plus both
   optic lobes; specks go).
5. Surface. The binary solid is blurred again (``--relax`` voxels) and the 0.5
   level is extracted with a numpy surface-nets mesher (dual contouring without
   the QEF: one vertex per sign-changing cell at the mean of its edge crossings,
   one quad per sign-changing grid edge, split into two triangles). This is the
   numpy-only stand-in for marching cubes; scikit-image is not a project
   dependency.
6. Smooth. Taubin smoothing (lambda 0.5 / mu -0.53, ``--smooth`` passes) removes
   the voxel terracing without shrinking the envelope.
7. Decimate. Uniform vertex clustering (Rossignac–Borrel) on a grid sized so the
   triangle count lands in ``--target`` (default 20k–40k), degenerate and
   duplicate faces removed, then two light Taubin passes.
8. Write ``public/data/brain-shell.bin`` (little-endian):
      char[4]   magic "FBS1"
      uint32    vertex count V
      uint32    triangle count T
      uint32    index width in bytes (2 or 4)
      float32   origin[3]      scene units
      float32   step[3]        scene units per quantisation step
      uint16    positions[3V]  position = origin + q * step
      (pad to 4 bytes)
      uint16|uint32 indices[3T], counter-clockwise seen from outside
   and ``public/data/brain-shell.json`` with the parameters and counts. Normals
   are computed in the browser.

Run: ``.venv/Scripts/python.exe scripts/build_brain_shell.py`` (numpy + scipy).
``--preview DIR`` writes PNG projections of the solid over the points.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from scipy import ndimage, sparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/brain/neurons.npz"
OUT_BIN = ROOT / "public/data/brain-shell.bin"
OUT_META = ROOT / "public/data/brain-shell.json"


def scene_positions() -> np.ndarray:
    """Neuron positions in scene units, identical to Brain.geometry()."""
    raw = np.load(SOURCE)["positions"].astype(np.float32) * np.array([4, 4, 40], np.float32)
    valid = np.isfinite(raw).all(axis=1) & (raw > 0).all(axis=1)
    centred = raw - np.median(raw[valid], axis=0)
    centred /= np.max(np.ptp(raw[valid], axis=0)) / 6
    centred[:, 1] *= -1
    return centred[valid]


def check_endpoint(points: np.ndarray, url: str) -> None:
    import urllib.request

    with urllib.request.urlopen(url, timeout=60) as r:
        served = np.frombuffer(r.read(), np.float32).reshape(-1, 4)
    served = served[served[:, 3] >= 0, :3]
    diff = float(np.abs(served - points).max()) if served.shape == points.shape else float("inf")
    print(f"endpoint check: max |difference| = {diff:.3g}")
    if diff > 1e-5:
        raise SystemExit("Positions differ from the endpoint; update scene_positions().")


def ball(radius: int) -> np.ndarray:
    r = np.arange(-radius, radius + 1)
    return (r[:, None, None] ** 2 + r[None, :, None] ** 2 + r[None, None, :] ** 2) <= radius * radius


def build_solid(points, grid, sigma, coverage, close):
    lo, hi = points.min(axis=0), points.max(axis=0)
    voxel = float((hi - lo).max()) / grid
    pad = int(np.ceil(close + 3 * sigma + 4))
    origin = lo - pad * voxel
    shape = np.ceil((hi - lo) / voxel).astype(int) + 2 * pad + 1
    edges = [origin[a] + voxel * np.arange(shape[a] + 1) for a in range(3)]
    counts, _ = np.histogramdd(points, bins=edges)
    density = ndimage.gaussian_filter(counts.astype(np.float32), sigma)
    cells = np.clip(((points - origin) / voxel).astype(int), 0, shape - 1)
    level = float(np.quantile(density[tuple(cells.T)], 1 - coverage))
    solid = density > level
    solid = ndimage.binary_closing(np.pad(solid, close), ball(close))[close:-close, close:-close, close:-close]
    solid = ndimage.binary_fill_holes(solid)
    labels, n = ndimage.label(solid)
    sizes = ndimage.sum(solid, labels, range(1, n + 1))
    keep = np.flatnonzero(sizes >= 0.005 * sizes.sum()) + 1
    solid = np.isin(labels, keep)
    inside = float(solid[tuple(cells.T)].mean())
    return solid, origin, voxel, level, density, int(len(keep)), inside


def surface_nets(field: np.ndarray, iso: float):
    """Vertices (grid units) and triangles of the iso surface; outside = below iso."""
    f = np.pad(field, 1, constant_values=field.min() - 1) - iso
    inside = f > 0
    nx, ny, nz = f.shape
    corners = np.array([[i, j, k] for k in (0, 1) for j in (0, 1) for i in (0, 1)])
    edge_pairs = [(a, b) for a in range(8) for b in range(a + 1, 8)
                  if np.abs(corners[a] - corners[b]).sum() == 1]
    cv = [f[c[0]:nx - 1 + c[0], c[1]:ny - 1 + c[1], c[2]:nz - 1 + c[2]] for c in corners]
    ci = [v > 0 for v in cv]
    mixed = np.zeros(cv[0].shape, bool)
    for v in ci[1:]:
        mixed |= v != ci[0]
    cell = np.argwhere(mixed)
    acc = np.zeros((len(cell), 3))
    cnt = np.zeros(len(cell))
    for a, b in edge_pairs:
        fa, fb = cv[a][mixed], cv[b][mixed]
        cross = (fa > 0) != (fb > 0)
        t = np.where(cross, fa / np.where(cross, fa - fb, 1), 0)
        p = corners[a] + t[:, None] * (corners[b] - corners[a])
        acc[cross] += p[cross]
        cnt += cross
    verts = cell + acc / cnt[:, None] - 1  # undo padding
    index = -np.ones(mixed.shape, np.int64)
    index[mixed] = np.arange(len(cell))
    faces = []
    for a in range(3):
        b, c = (a + 1) % 3, (a + 2) % 3
        lo = [slice(None)] * 3
        hi = [slice(None)] * 3
        lo[a] = slice(0, -1)
        hi[a] = slice(1, None)
        s0, s1 = inside[tuple(lo)], inside[tuple(hi)]
        where = np.argwhere(s0 != s1)
        outward = s0[tuple(where.T)]  # inside at the low end: normal points +a
        ok = (where[:, b] >= 1) & (where[:, c] >= 1) & (where[:, b] < f.shape[b] - 1) & (where[:, c] < f.shape[c] - 1)
        where, outward = where[ok], outward[ok]

        def cell_at(db, dc):
            q = where.copy()
            q[:, b] += db
            q[:, c] += dc
            return index[tuple(q.T)]

        quad = np.stack([cell_at(-1, -1), cell_at(0, -1), cell_at(0, 0), cell_at(-1, 0)], axis=1)
        quad[~outward] = quad[~outward][:, ::-1]
        faces.append(np.r_[quad[:, [0, 1, 2]], quad[:, [0, 2, 3]]])
    faces = np.concatenate(faces)
    return verts, faces[(faces >= 0).all(axis=1)]


def taubin(verts, faces, passes, lam=0.5, mu=-0.53):
    n = len(verts)
    i = np.r_[faces[:, 0], faces[:, 1], faces[:, 2], faces[:, 1], faces[:, 2], faces[:, 0]]
    j = np.r_[faces[:, 1], faces[:, 2], faces[:, 0], faces[:, 0], faces[:, 1], faces[:, 2]]
    adj = sparse.coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    adj.data[:] = 1
    deg = np.maximum(np.asarray(adj.sum(axis=1)).ravel(), 1)[:, None]
    v = verts.astype(np.float64)
    for _ in range(passes):
        for w in (lam, mu):
            v = v + w * (adj @ v / deg - v)
    return v


def clean(verts, faces):
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    key = np.sort(faces, axis=1)
    _, first = np.unique(key, axis=0, return_index=True)
    faces = faces[np.sort(first)]
    used = np.unique(faces)
    remap = -np.ones(len(verts), np.int64)
    remap[used] = np.arange(len(used))
    return verts[used], remap[faces]


def cluster(verts, faces, cell):
    q = np.floor(verts / cell).astype(np.int64)
    _, rep, inverse = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.ravel()
    sums = np.zeros((len(rep), 3))
    np.add.at(sums, inverse, verts)
    counts = np.bincount(inverse, minlength=len(rep))[:, None]
    return clean(sums / counts, inverse[faces])


def decimate(verts, faces, target):
    lo_t, hi_t = target
    if len(faces) <= hi_t:
        return verts, faces, 0.0
    lo, hi = 0.2, 6.0  # clustering cell in grid units
    best = None
    for _ in range(24):
        cell = (lo + hi) / 2
        v, f = cluster(verts, faces, cell)
        best = (v, f, cell)
        if len(f) > hi_t:
            lo = cell
        elif len(f) < lo_t:
            hi = cell
        else:
            break
    return best


def orient_outward(verts, faces):
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    volume = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6
    return faces if volume > 0 else faces[:, ::-1].copy()


def write(verts, faces, meta):
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    step = np.maximum(hi - lo, 1e-6) / 65535
    q = np.round((verts - lo) / step).astype(np.uint16)
    width = 2 if len(verts) <= 65535 else 4
    body = bytearray()
    body += b"FBS1" + struct.pack("<3I", len(verts), len(faces), width)
    body += struct.pack("<6f", *lo.astype(np.float32), *step.astype(np.float32))
    body += q.astype("<u2").tobytes()
    body += b"\0" * (-len(body) % 4)
    body += faces.astype("<u2" if width == 2 else "<u4").tobytes()
    OUT_BIN.parent.mkdir(parents=True, exist_ok=True)
    OUT_BIN.write_bytes(bytes(body))
    meta["bytes"] = len(body)
    OUT_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def preview(points, solid, origin, voxel, folder: Path):
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    cells = ((points - origin) / voxel).astype(int)
    for name, axis, (u, v) in [("front", 2, (0, 1)), ("top", 1, (0, 2)), ("side", 0, (2, 1))]:
        proj = solid.any(axis=axis).T[::-1].astype(np.uint8)
        img = np.zeros(proj.shape + (3,), np.uint8)
        img[proj > 0] = (54, 84, 76)
        rows = proj.shape[0] - 1 - cells[:, v]
        hits = np.zeros(proj.shape, np.int32)
        np.add.at(hits, (rows, cells[:, u]), 1)
        img[hits > 0] = (220, 235, 213)
        Image.fromarray(img).resize((proj.shape[1] * 4, proj.shape[0] * 4), Image.NEAREST).save(folder / f"{name}.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--grid", type=int, default=112)
    ap.add_argument("--sigma", type=float, default=1.6)
    ap.add_argument("--coverage", type=float, default=0.97)
    ap.add_argument("--close", type=int, default=3)
    ap.add_argument("--relax", type=float, default=1.2)
    ap.add_argument("--smooth", type=int, default=12)
    ap.add_argument("--target", type=int, nargs=2, default=(20000, 40000))
    ap.add_argument("--check", metavar="URL")
    ap.add_argument("--preview", type=Path)
    args = ap.parse_args()

    points = scene_positions()
    if args.check:
        check_endpoint(points, args.check)
    solid, origin, voxel, level, density, parts, inside = build_solid(
        points, args.grid, args.sigma, args.coverage, args.close)
    print(f"grid {solid.shape}, voxel {voxel:.4f}, iso {level:.3f} neurons/voxel, "
          f"{parts} part(s), {inside:.1%} of neurons inside")
    if args.preview:
        preview(points, solid, origin, voxel, args.preview)
    field = ndimage.gaussian_filter(solid.astype(np.float32), args.relax)
    verts, faces = surface_nets(field, 0.5)
    print(f"surface nets: {len(verts)} vertices, {len(faces)} triangles")
    verts = taubin(verts, faces, args.smooth)
    verts, faces, cell = decimate(verts, faces, args.target)
    verts = taubin(verts, faces, 2)
    verts = origin + (verts + 0.5) * voxel  # voxel centres → scene units
    faces = orient_outward(verts, faces)
    print(f"final: {len(verts)} vertices, {len(faces)} triangles (cluster cell {cell:.2f} voxels)")
    meta = {
        "source": "data/brain/neurons.npz",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:16],
        "frame": "Brain.geometry(): nm, median-centred, longest axis = 6 units, Y flipped",
        "neurons": int(len(points)),
        "grid": list(map(int, solid.shape)),
        "voxel": round(voxel, 5),
        "sigma_voxels": args.sigma,
        "coverage": args.coverage,
        "iso_neurons_per_voxel": round(level, 4),
        "neurons_inside": round(inside, 4),
        "parts": parts,
        "close_voxels": args.close,
        "relax_voxels": args.relax,
        "taubin_passes": args.smooth,
        "cluster_cell_voxels": round(float(cell), 3),
        "vertices": int(len(verts)),
        "triangles": int(len(faces)),
    }
    write(verts, faces, meta)
    print(f"wrote {OUT_BIN.relative_to(ROOT)} ({meta['bytes'] / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
