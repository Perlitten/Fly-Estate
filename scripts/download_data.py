"""Download pinned, public primary-source data without Codex authentication."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
RAW.mkdir(parents=True, exist_ok=True)

def download(url, name, checksum=None):
    dest = RAW / name
    if not dest.exists():
        temp = dest.with_suffix(dest.suffix + ".part")
        print(f"Downloading {name}", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "FlyEstate-research/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
            size = int(response.headers.get("Content-Length", 0))
            total = 0
            last = 0
            while block := response.read(1024 * 1024):
                out.write(block)
                total += len(block)
                if total - last > 100 * 1024 * 1024:
                    print(f"  {total // 1024 // 1024} MB / {size // 1024 // 1024} MB", flush=True)
                    last = total
        temp.rename(dest)
    if checksum:
        h = hashlib.md5()
        with dest.open("rb") as f:
            while block := f.read(1024 * 1024):
                h.update(block)
        if h.hexdigest() != checksum.removeprefix("md5:"):
            raise RuntimeError(f"Checksum mismatch: {name}")
    return dest

record = json.load(urllib.request.urlopen("https://zenodo.org/api/records/10676866"))
edge = next(f for f in record["files"] if f["key"] == "proofread_connections_783.feather")
annotation_url = "https://raw.githubusercontent.com/flyconnectome/flywire_annotations/v3.1.0/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
download(annotation_url, "annotations_v3.1.0.tsv")
download(edge["links"]["self"], edge["key"], edge["checksum"])
manifest = {"dataset": "FAFB v783", "record": "https://zenodo.org/records/10676866", "edges": edge,
            "annotations": annotation_url, "annotation_version": "v3.1.0",
            "license": record["metadata"].get("license"),
            "method": "Real topology; artificial input encoding, rate dynamics and learned decision readout."}
(ROOT / "data/provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
print("Data downloaded and checksum verified.", flush=True)
