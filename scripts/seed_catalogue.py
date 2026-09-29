"""Import the public source-backed catalogue, without writing any user ratings."""
from pathlib import Path
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.storage import Store, ROOT
from server.vision import Vision
from server.importers import normalize,photos

store,vision=Store(),Vision()
existing={l["id"]:l for l in store.get()["listings"]}
items=json.loads((ROOT/"data/listings.json").read_text(encoding="utf-8"))
for i,item in enumerate(items):
    try:
        l=normalize(item)
        old=existing.get(l["id"],{})
        if (old.get("vision") or {}).get("algorithm")=="all-photos-v2" and old.get("photo_urls")==l["photo_urls"]: continue
        print(f'[{i+1}/{len(items)}] {l["title"]}',flush=True)
        l["import_warnings"]=photos(l)
        l["vision"]=vision.encode(l["photos"])
        store.listing(l)
    except Exception as e: print(f'Skipped {item.get("url")}: {e}',flush=True)
print('Public catalogue ready; personal ratings were not changed.',flush=True)
