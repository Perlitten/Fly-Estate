from pathlib import Path
import json
import sqlite3
import threading
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = {"budget":1800,"ceiling":2800,"min_bedrooms":1,"covered_parking":True,
                    "excluded":["Ypsonas"],"ideal":[34.710,33.050],"radius":3,"mode":"cyborg"}

def now(): return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path=None):
        self.path = path or ROOT / "data/state.sqlite"
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS listings (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ratings (id TEXT PRIMARY KEY, value INTEGER NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS comparisons (a TEXT NOT NULL,b TEXT NOT NULL,choice INTEGER NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(a,b));
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES (1,?)", (json.dumps(DEFAULT_SETTINGS),))
            self._migrate_english_copy(db)

    @staticmethod
    def _migrate_english_copy(db):
        """Translate application-generated legacy copy without changing IDs or ratings."""
        for id, text in db.execute("SELECT id,data FROM listings").fetchall():
            listing = json.loads(text)
            original_area = listing.get("area", "")
            if original_area == "Район не указан":
                listing["area"] = "Area unspecified"
            if listing.get("source") == "Ручной ввод":
                listing["source"] = "Manual entry"
            bedrooms, size, parking = listing.get("bedrooms"), listing.get("size"), listing.get("parking")
            if bedrooms is not None and size is not None:
                old = f'{bedrooms} спальни · {size:g} м² · {original_area}. Парковка: {parking}. Данные — снимок объявления; доступность уточняется у владельца.'
                if listing.get("description") == old:
                    listing["description"] = f'{bedrooms} bedrooms · {size:g} m² · {listing.get("area", "")}. Parking: {parking}. Listing snapshot; confirm availability with the owner.'
            updated = json.dumps(listing, ensure_ascii=False)
            if updated != text:
                db.execute("UPDATE listings SET data=? WHERE id=?", (updated, id))

    def connect(self): return sqlite3.connect(self.path,timeout=30)

    def get(self):
        with self.lock, self.connect() as db:
            return {"settings":json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0]),
                    "listings":[json.loads(r[0]) for r in db.execute("SELECT data FROM listings ORDER BY id")],
                    "ratings":dict(db.execute("SELECT id,value FROM ratings")),
                    "comparisons":[dict(zip(["a","b","choice"],r)) for r in db.execute("SELECT a,b,choice FROM comparisons")]}

    def listing(self, data):
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO listings VALUES (?,?)",(data["id"],json.dumps(data,ensure_ascii=False)))

    def settings(self, settings):
        with self.lock, self.connect() as db:
            db.execute("UPDATE settings SET data=? WHERE id=1",(json.dumps(settings),))

    def rating(self, id, value):
        with self.lock, self.connect() as db:
            if value is None: db.execute("DELETE FROM ratings WHERE id=?",(id,))
            else: db.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?)",(id,value,now()))

    def compare(self, a, b, choice):
        if a > b: a,b,choice = b,a,-choice
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO comparisons VALUES (?,?,?,?)",(a,b,choice,now()))

def filter_reasons(l, settings):
    reasons = []
    if l.get("city","").casefold() != "limassol": reasons.append("Outside Limassol")
    if l["price"] > settings["ceiling"]: reasons.append("Above the hard limit")
    if l["bedrooms"] < settings["min_bedrooms"]: reasons.append("Not enough bedrooms")
    if settings["covered_parking"] and l.get("parking") != "covered":
        reasons.append("No confirmed covered parking")
    if any(e.casefold() in l.get("area","").casefold() for e in settings["excluded"]): reasons.append("Excluded area")
    if l.get("available") is False: reasons.append("Listing no longer available")
    return reasons
