"""Portable local sessions: SQLite snapshots, photographs and exact memory.

Export holds the application write lock and an engine write reservation while
copying both databases. Large immutable media files are packed afterwards.
Restore is an offline operation, validates the entire archive first, keeps a
recoverable copy of the previous state, and rolls back installation failures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import sqlite3
import tempfile
import uuid
import zipfile

from .storage import ROOT, Store, now
from .jobs import Queue
from .checkpoints import decode
from .protocol import design

FORMAT = "fly-estate-session-v1"
MAX_BYTES = 2 * 1024**3


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024**2), b""): h.update(block)
    return h.hexdigest()


def backup_db(source, target):
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def export_session(store, queue, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    root = store.path.parent.parent
    with tempfile.TemporaryDirectory(prefix="fly-session-") as temp:
        stage = Path(temp)
        (stage / "data/engine").mkdir(parents=True)
        with store.lock, queue.transaction() as db:
            backup_db(store.path, stage / "data/state.sqlite")
            backup_db(queue.path, stage / "data/engine/engine.sqlite")
            checkpoints = [r[0] for r in db.execute("SELECT hash FROM checkpoints")]
            current = db.execute("SELECT value FROM engine_state WHERE key='current_checkpoint'").fetchone()
        paths = [(p.relative_to(stage).as_posix(), p) for p in stage.rglob("*.sqlite")]
        paths += [("data/engine/checkpoints/" + key + ".npz", root / "data/engine/checkpoints" / (key + ".npz")) for key in checkpoints]
        subgraph = root / "data/engine/olfactory_mb_v783.npz"
        if subgraph.exists(): paths.append(("data/engine/olfactory_mb_v783.npz", subgraph))
        paths += [(p.relative_to(root).as_posix(), p) for p in (root / "data/photos").glob("*.jpg")]
        manifest = {"format": FORMAT, "created": now(), "checkpoint": current[0] if current else None,
                    "model_design": design(root),
                    "photo_count": sum(name.startswith("data/photos/") for name, _ in paths), "files": {},
                    "versions": {name: (root / name).read_text() for name in
                                 ("package.json", "requirements.txt", "research/upstream-manifest.json") if (root / name).exists()}}
        temporary = output.with_name(output.name + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
                for name, path in paths:
                    manifest["files"][name] = {"sha256": sha(path), "bytes": path.stat().st_size}
                    archive.write(path, name)
                archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return manifest


def allowed(name):
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name: return False
    return name in ("data/state.sqlite", "data/engine/engine.sqlite", "data/engine/olfactory_mb_v783.npz") or (
        len(p.parts) == 3 and p.parts[:2] == ("data", "photos") and p.suffix == ".jpg") or (
        len(p.parts) == 4 and p.parts[:3] == ("data", "engine", "checkpoints")
        and p.suffix == ".npz" and len(p.stem) == 64 and all(c in "0123456789abcdef" for c in p.stem))


def restore_session(path, root=ROOT, api_port=8000):
    root = Path(root)
    if (root / "data/engine/engine.sqlite").exists() and Queue(root / "data/engine/engine.sqlite").worker_status().get("alive"):
        raise ValueError("Stop Fly Estate and its engine worker before restoring a session.")
    with socket.socket() as sock:
        sock.settimeout(.2)
        if sock.connect_ex(("127.0.0.1", api_port)) == 0:
            raise ValueError(f"Stop the API on port {api_port} before restoring a session.")
    stage = Path(tempfile.mkdtemp(prefix=".session-restore-", dir=root))
    rollback = root / ".cache/session-restores" / uuid.uuid4().hex
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > 20000: raise ValueError("Invalid archive member count.")
            if archive.getinfo("manifest.json").file_size > 1024**2: raise ValueError("Manifest is too large.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != FORMAT: raise ValueError("Unsupported session version.")
            files = manifest["files"]
            if manifest.get("model_design") != design(root):
                raise ValueError("Session model code differs. Use the code version that created the archive before restoring.")
            if set(names) != set(files) | {"manifest.json"}: raise ValueError("Archive differs from its manifest.")
            if sum(i.file_size for i in archive.infolist()) > MAX_BYTES: raise ValueError("Session exceeds the 2 GB restore limit.")
            for name, info in files.items():
                if not allowed(name) or archive.getinfo(name).file_size != info["bytes"]: raise ValueError("Invalid session file.")
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, destination.open("wb") as target: shutil.copyfileobj(source, target)
                if sha(destination) != info["sha256"]: raise ValueError(f"Checksum mismatch: {name}")
                if name.startswith("data/engine/checkpoints/") and destination.stem != info["sha256"]:
                    raise ValueError(f"Checkpoint identity mismatch: {name}")
        for name in ("data/state.sqlite", "data/engine/engine.sqlite"):
            with sqlite3.connect(stage / name) as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok": raise ValueError(f"Invalid database: {name}")
        current = manifest.get("checkpoint")
        if current:
            from .engine.olfactory import OlfactoryMBEngine
            from .engine.subgraph import load
            raw = (stage / "data/engine/checkpoints" / (current + ".npz")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != current: raise ValueError("Memory checkpoint hash differs.")
            saved = decode(raw)
            from .engine.olfactory import Params
            engine = OlfactoryMBEngine(params=Params(**saved.meta["params"]), data=load(stage / "data/engine/olfactory_mb_v783.npz"))
            engine.restore(saved)
        with sqlite3.connect(stage / "data/engine/engine.sqlite") as db:
            pointer = db.execute("SELECT value FROM engine_state WHERE key='current_checkpoint'").fetchone()
            if (pointer[0] if pointer else None) != current: raise ValueError("Session memory pointer differs from manifest.")
            db.execute("DELETE FROM engine_state WHERE key IN ('worker','live_replay','memory_progress','evaluation_progress')")
        # All validation precedes any replacement. Keep the old session intact.
        rollback.mkdir(parents=True)
        moved, installed = [], []
        try:
            for name in ("state.sqlite", "state.sqlite-wal", "state.sqlite-shm", "engine", "photos"):
                destination = root / "data" / name
                if destination.exists(): os.replace(destination, rollback / name); moved.append(name)
            for name in ("state.sqlite", "engine", "photos"):
                source = stage / "data" / name
                if source.exists(): os.replace(source, root / "data" / name); installed.append(name)
        except BaseException:
            for name in installed:
                destination = root / "data" / name
                if destination.is_dir(): shutil.rmtree(destination)
                else: destination.unlink(missing_ok=True)
            for name in moved: os.replace(rollback / name, root / "data" / name)
            raise
        return {"restored": True, "checkpoint": current, "photos": manifest["photo_count"], "previous_session": str(rollback)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "restore"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()
    print(json.dumps(export_session(Store(), Queue(), args.path) if args.action == "export"
                     else restore_session(args.path, api_port=args.api_port), indent=2))
