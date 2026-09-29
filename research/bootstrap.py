"""Fetch pinned upstream source/data; keep large files outside Git.

Run: .venv/bin/python -m research.bootstrap
After the initial run, the committed manifest verifies every cached/downloaded
file against its SHA256. Source files are never modified in this cache.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/research/upstream"
MANIFEST = ROOT / "research/upstream-manifest.json"
SOURCES = {
    "shiu": {
        "repository": "philshiu/Drosophila_brain_model",
        "revision": "91bdd1e7dcf193f3e7ca5a8933497fcef63b7960",
        "files": [
            "LICENSE", "Readme.md", "environment_full.yml", "model.py", "utils.py",
            "2023_03_23_completeness_630_final.csv",
            "2023_03_23_connectivity_630_final.parquet",
            "Completeness_783.csv", "Connectivity_783.parquet",
        ],
    },
    "fly-api": {
        "repository": "dtch1997/fly-api",
        "revision": "a6ad07a810b1a43cd0356149c07b32105eb46d2a",
        "files": [
            "LICENSE", "README.md", "demo/track_a_lif.py", "docs/demo-report.md",
            "experiments/learning/model_ext.py",
            "experiments/learning/learning_driver_mb.py",
            "experiments/learning/report.md", "experiments/learning/notes.md",
            "experiments/learning/sugar_ids_783.json",
        ],
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    prior = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    expected = {f["cache_path"]: f for s in prior.get("sources", []) for f in s["files"]}
    output = {"schema_version": 1, "sources": []}
    for name, source in SOURCES.items():
        entry = {"name": name, "repository": source["repository"],
                 "revision": source["revision"], "license": "MIT", "files": []}
        for filename in source["files"]:
            url = f"https://raw.githubusercontent.com/{source['repository']}/{source['revision']}/{filename}"
            path = CACHE / name / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            relative = path.relative_to(ROOT).as_posix()
            known = expected.get(relative)
            if path.exists() and known and sha256(path) != known["sha256"]:
                raise RuntimeError(f"Cached file changed: {path}")
            if not path.exists():
                tmp = path.with_name(path.name + ".part")
                print(f"Downloading {name}/{filename}", flush=True)
                req = urllib.request.Request(url, headers={"User-Agent": "Fly-Estate-research/1"})
                try:
                    with urllib.request.urlopen(req, timeout=90) as response, tmp.open("wb") as f:
                        while block := response.read(1024 * 1024):
                            f.write(block)
                    if known and sha256(tmp) != known["sha256"]:
                        raise RuntimeError(f"Checksum mismatch: {url}")
                    tmp.replace(path)
                finally:
                    tmp.unlink(missing_ok=True)
            entry["files"].append({"path": filename, "cache_path": relative,
                                   "url": url, "bytes": path.stat().st_size,
                                   "sha256": sha256(path)})
        output["sources"].append(entry)
    text = json.dumps(output, indent=2) + "\n"
    if prior and output != prior:
        raise RuntimeError("Manifest changed; review pins before accepting new sources")
    MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    print(f"Verified {sum(len(s['files']) for s in output['sources'])} upstream files", flush=True)


if __name__ == "__main__":
    main()
