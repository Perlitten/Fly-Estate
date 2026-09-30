from pathlib import Path
import json
import sqlite3
import threading
from . import learning
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
            db.executescript(learning.JOURNAL_SCHEMA)
            db.execute("CREATE TABLE IF NOT EXISTS prospective_cohorts (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS feedback_provenance (key TEXT PRIMARY KEY, actor TEXT NOT NULL, data TEXT NOT NULL, updated TEXT NOT NULL)")
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

    def get(self, archived=False):
        """Current state. Archived listings (kept, e.g. an earlier source) are left out unless asked for."""
        with self.lock, self.connect() as db:
            listings=[json.loads(r[0]) for r in db.execute("SELECT data FROM listings ORDER BY id")]
            return {"settings":json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0]),
                    "listings":[l for l in listings if archived or not l.get("archived")],
                    "ratings":dict(db.execute("SELECT id,value FROM ratings")),
                    "comparisons":[dict(zip(["a","b","choice"],r)) for r in db.execute("SELECT a,b,choice FROM comparisons")],
                    "feedback_provenance":{key:{"actor":actor,**json.loads(text)} for key,actor,text in db.execute("SELECT key,actor,data FROM feedback_provenance")}}

    def listing(self, data):
        from .catalogue import same_apartment, enrich
        with self.lock, self.connect() as db:
            rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM listings")]
            previous = next((r for r in rows if r["id"] == data["id"]), None)
            previous = previous or next((r for r in rows if same_apartment(r, data)), None)
            data = enrich(data, previous)
            db.execute("INSERT OR REPLACE INTO listings VALUES (?,?)",(data["id"],json.dumps(data,ensure_ascii=False)))
            return data["id"]

    def settings(self, settings):
        with self.lock, self.connect() as db:
            db.execute("UPDATE settings SET data=? WHERE id=1",(json.dumps(settings),))

    def source_removed(self, url):
        from .catalogue import identity
        with self.lock, self.connect() as db:
            for id,text in db.execute("SELECT id,data FROM listings").fetchall():
                listing=json.loads(text)
                sources=listing.get("sources") or [{"url":listing.get("url"),"available":listing.get("available")}]
                changed=False
                for source in sources:
                    if identity(source.get("url")) == identity(url):
                        source.update(available=False,updated_at=now()); changed=True
                if not changed: continue
                before=listing.get("available")
                listing["sources"]=sources
                listing["available"]=False if all(s.get("available") is False for s in sources) else True if any(s.get("available") is True for s in sources) else None
                listing["last_checked_at"]=now()
                listing.setdefault("source_history",[]).append({"checked_at":now(),"url":url,
                    "changes":{"available":{"before":before,"after":listing["available"]}},"reason":"HTTP 404/410"})
                db.execute("UPDATE listings SET data=? WHERE id=?",(json.dumps(listing),id))

    def rating(self, id, value, context=None):
        with self.lock, self.connect() as db:
            if value is None: db.execute("DELETE FROM ratings WHERE id=?",(id,))
            else: db.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?)",(id,value,now()))
            db.execute("INSERT OR REPLACE INTO feedback_provenance VALUES (?,?,?,?)",(f"rating:{id}","human","{}",now()))
            if context is not None:
                from .prospective import feedback_is_held
                if not feedback_is_held(db, context,validate=value is not None): return learning.record(db, f"rating:{id}", "rating", value, context)

    def teacher_reviews(self, reviews, contexts):
        from .prospective import feedback_is_held
        events=[]
        with self.lock, self.connect() as db:
            for review,context in zip(reviews,contexts):
                id,value=review["id"],review["value"]
                key=f"rating:{id}"
                existing=db.execute("SELECT value FROM ratings WHERE id=?",(id,)).fetchone()
                origin=db.execute("SELECT actor FROM feedback_provenance WHERE key=?",(key,)).fetchone()
                if existing and (not origin or origin[0] != "agent"):
                    raise ValueError("Assistant reviews cannot overwrite a human rating.")
                held=feedback_is_held(db,context)
                db.execute("INSERT OR REPLACE INTO ratings VALUES (?,?,?)",(id,value,now()))
                db.execute("INSERT OR REPLACE INTO feedback_provenance VALUES (?,?,?,?)",(key,"agent",json.dumps(review),now()))
                event=None if held else learning.record(db,key,"rating",value,context)
                events.append({"id":id,"event":event,"evaluation_only":held})
        return events

    def compare(self, a, b, choice, context=None):
        if a > b: a,b,choice = b,a,-choice
        with self.lock, self.connect() as db:
            db.execute("INSERT OR REPLACE INTO comparisons VALUES (?,?,?,?)",(a,b,choice,now()))
            if context is not None:
                from .prospective import feedback_is_held
                if not feedback_is_held(db, context): return learning.record(db, f"pair:{a}:{b}", "comparison", choice, context)

def feedback_counts(data, ids=None):
    allowed=set(ids) if ids is not None else None
    ratings={i:v for i,v in data["ratings"].items() if allowed is None or i in allowed}
    agent=sum(data.get("feedback_provenance",{}).get(f"rating:{i}",{}).get("actor")=="agent" for i in ratings)
    pairs=[p for p in data["comparisons"] if allowed is None or (p["a"] in allowed and p["b"] in allowed)]
    return {"human":len(ratings)-agent+len(pairs),"agent":agent}

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
