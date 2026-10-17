"""Record model design before any prospective feedback is collected."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("server/engine/base.py", "server/engine/lif.py", "server/engine/olfactory.py", "server/engine/stimuli.py",
         "server/engine/subgraph.py", "server/brain.py", "server/vision.py", "server/readout.py",
         "server/learning.py", "server/evaluation.py", "server/gallery.py", "server/prospective.py",
         "server/storage.py", "server/catalogue.py", "server/geography.py",
         "data/geography/highways-limassol.geojson", "docs/TEACHER_BRIEF.md", "server/protocol.py", "requirements.txt")


def design(root=ROOT):
    return {name: hashlib.sha256((Path(root) / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in FILES}


def require_design(saved):
    if not saved or saved != design():
        raise ValueError("Model design changed since this cohort was reserved. Restore the recorded code version before evaluating it.")
