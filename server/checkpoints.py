"""Atomic, content-addressed engine checkpoints.

Files live in `data/engine/checkpoints/<sha256>.npz`; the registry and the
current pointer live in the engine database (see `server.jobs`). A file is
written to a temporary name, flushed to disk and renamed, so a crash leaves
either the old checkpoint or the complete new one.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import numpy as np

from .engine.base import Checkpoint
from .jobs import Queue, now

DIRECTORY = Path(__file__).resolve().parents[1] / "data/engine/checkpoints"


def encode(checkpoint: Checkpoint) -> bytes:
    buffer = io.BytesIO()
    meta = np.frombuffer(json.dumps(checkpoint.meta, sort_keys=True).encode(), dtype=np.uint8)
    np.savez(buffer, meta=meta, **checkpoint.arrays)
    return buffer.getvalue()


def decode(data: bytes) -> Checkpoint:
    with np.load(io.BytesIO(data), allow_pickle=False) as saved:
        arrays = {k: saved[k] for k in saved.files if k != "meta"}
        meta = json.loads(saved["meta"].tobytes())
    return Checkpoint(arrays, meta)


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("wb") as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    os.replace(tmp, path)


class CheckpointStore:
    def __init__(self, queue: Queue, directory: Path = DIRECTORY):
        self.queue, self.directory = queue, directory

    def save(self, checkpoint: Checkpoint, label: str, parent: str | None = None, make_current: bool = True) -> str:
        data = encode(checkpoint)
        digest = hashlib.sha256(data).hexdigest()
        path = self.directory / f"{digest}.npz"
        if not path.exists():
            write_atomic(path, data)
        with self.queue.transaction() as db:
            db.execute("INSERT OR IGNORE INTO checkpoints VALUES (?,?,?,?,?,?,?)",
                       (digest, checkpoint.meta.get("fingerprint", ""), checkpoint.meta.get("version", ""),
                        label, parent, now(), json.dumps({k: v for k, v in checkpoint.meta.items()
                                                          if k not in ("rng", "history")})))
            if make_current:
                db.execute("INSERT OR REPLACE INTO engine_state VALUES ('current_checkpoint', ?)", (digest,))
        return digest

    def load(self, digest: str) -> Checkpoint:
        data = (self.directory / f"{digest}.npz").read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"checkpoint {digest[:12]} is corrupted")
        return decode(data)

    def current(self) -> dict | None:
        with self.queue.connect() as db:
            row = db.execute("SELECT c.* FROM engine_state s JOIN checkpoints c ON c.hash = s.value "
                             "WHERE s.key = 'current_checkpoint'").fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict]:
        with self.queue.connect() as db:
            return [dict(r) for r in db.execute("SELECT hash, fingerprint, version, label, parent, created "
                                                "FROM checkpoints ORDER BY created")]
