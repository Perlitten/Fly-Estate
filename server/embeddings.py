"""Backfill CLIP image embeddings for photos imported before R3.

`python -m server.embeddings` embeds every stored photo that has no
embedding for the pinned CLIP revision. Embeddings are keyed by photo
content, so duplicates across listings are computed once. Afterwards the
mean embedding is frozen as the cyborg codec's centre, unless one exists;
`--refresh-center` replaces it.
"""
from __future__ import annotations

import argparse
import sys

from .engine.stimuli import Center
from .gallery import PhotoHashes
from .jobs import Queue
from .storage import Store
from .vision import MODEL_ID, REVISION, Vision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--refresh-center", action="store_true",
                        help="replace the frozen CLIP centre; earlier cyborg results stop matching")
    args = parser.parse_args(argv)
    queue, hashes = Queue(), PhotoHashes()
    done = queue.embedded(MODEL_ID, REVISION)
    todo, seen, unreadable = [], set(), 0
    for listing in Store().get()["listings"]:
        for photo in listing.get("photos") or []:
            try:
                sha = hashes(photo)
            except OSError:
                unreadable += 1
                continue
            if sha not in done and sha not in seen:
                seen.add(sha)
                todo.append((photo, sha))
    print(f"{len(done)} embedded, {len(todo)} to embed, {unreadable} unreadable", flush=True)
    vision = Vision() if todo else None
    for start in range(0, len(todo), args.batch):
        chunk = todo[start:start + args.batch]
        for (_, sha), vector in zip(chunk, vision.embed([p for p, _ in chunk])):
            queue.put_embedding(sha, MODEL_ID, REVISION, vector)
        print(f"{min(start + args.batch, len(todo))}/{len(todo)}", flush=True)
    vector, photos = queue.freeze_center(MODEL_ID, REVISION, refresh=args.refresh_center)
    print(f"CLIP centre: {photos} photos, sha256 {Center.of(vector, photos).sha256[:12]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
