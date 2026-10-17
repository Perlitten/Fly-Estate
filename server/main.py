from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
import json
import threading
import uuid
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response, FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, model_validator
from .storage import Store, ROOT, DEFAULT_SETTINGS, filter_reasons, now
from .brain import Brain, distance_km
from .vision import Vision, MODEL_ID, REVISION
from . import bazaraki, importers, learning, evaluation, prospective, catalogue as catalogue_data
from .jobs import Queue
from .checkpoints import CheckpointStore
from .engine import subgraph
from .engine.stimuli import context_signals
from . import readout
from .geography import highway_position
from .gallery import PhotoHashes, gallery, job_params, portfolio
from .replay import project as project_replay

store=Store()
brain=None
vision=Vision()
# The brain and CLIP are locked separately: encoding a listing's photos takes tens of
# seconds and must not hold up /api/state or activity requests, which only need the brain.
model_lock=threading.RLock()
vision_lock=threading.Lock()
jobs={}
engine_queue=Queue()
learning.initialise(engine_queue)
engine_checkpoints=CheckpointStore(engine_queue)
photo_hashes=PhotoHashes()
geometry=None
lines=None

@asynccontextmanager
async def lifespan(app):
    global brain,geometry,lines
    brain=Brain()
    geometry,lines=brain.geometry()
    yield

app=FastAPI(title="Fly Estate",lifespan=lifespan)
(ROOT / "data/photos").mkdir(parents=True,exist_ok=True)
app.mount("/data/photos",StaticFiles(directory=ROOT / "data/photos"),name="photos")

class Settings(BaseModel):
    budget:float=Field(ge=100,le=20000)
    ceiling:float=Field(ge=100,le=100000)
    min_bedrooms:int=Field(ge=0,le=10)
    covered_parking:bool
    excluded:list[str]=Field(max_length=30)
    ideal:list[float]=Field(min_length=2,max_length=2)
    radius:float=Field(ge=0.1,le=30)
    mode:Literal["pure","cyborg"]
    @model_validator(mode="after")
    def validate_values(self):
        if self.ceiling<self.budget: raise ValueError("The hard limit cannot be lower than the target budget.")
        if not (34<=self.ideal[0]<=36 and 32<=self.ideal[1]<=35): raise ValueError("The preferred point must be in Cyprus.")
        self.excluded=[x.strip()[:80] for x in self.excluded if x.strip()]
        return self

@app.get("/api/state")
def state():
    data=store.get()
    train_ratings, train_pairs, held = prospective.training(data,store,photo_hashes)
    group_of=readout.groups(data["listings"],lambda p:photo_hashes(p) if photo_hashes.path(p).exists() else p)
    with model_lock:
        eligible=[l for l in data["listings"] if not filter_reasons(l,data["settings"])]
        predictions,training=brain.predict(eligible,data["settings"],train_ratings,train_pairs,
                                          normalization_ids=[l["id"] for l in eligible if l["id"] not in held and l.get("vision")])
    for l in data["listings"]:
        l["prediction"]=predictions.get(l["id"],{"decision":"waiting","probability":0.5,"price_aversion":0,"trace":{},
                "distance":round(distance_km(data["settings"]["ideal"],l["coords"]),1) if l.get("coords") else None})
        l["filter_reasons"]=filter_reasons(l,data["settings"])
        origin=data.get("feedback_provenance",{}).get(f"rating:{l['id']}",{})
        l["rating"]=data["ratings"].get(l["id"]) if origin.get("actor") != "agent" else None
        l["teacher_review"]=origin if origin.get("actor") == "agent" else None
        if l["teacher_review"]:
            l["teacher_review"]={**origin,"stale":
                origin.get("inspected_photo_sha256") != [photo_hashes(p) for p in l.get("photos",[])]
                or origin.get("listing_snapshot") != teacher_listing_snapshot(l)
                or origin.get("location") != highway_position(l) or l.get("available") is False}
        l["highway_position"]=highway_position(l)
        l["evaluation_only"] = l["id"] in held
        l["freshness"] = catalogue_data.freshness(l)
        l["apartment_group"] = group_of[l["id"]]
        l["stimulus_context"] = context_signals(l,data["settings"])
        l["prediction"]["source"]="rate"
    if int(engine_queue.state("memory_revision") or 0):
        learned=portfolio_readout()
        for l in data["listings"]:
            if l["id"] in learned["scores"]:
                p=learned["scores"][l["id"]]
                l["prediction"].update(probability=p,decision="approach" if p>.58 else "avoid" if p<.42 else "maybe",
                                        source="spiking-memory")
    return {**data,"brain":brain.summary,"training":training,"areas":json.loads((ROOT/"data/areas.json").read_text(encoding="utf-8"))}

@app.put("/api/settings")
def settings(payload:Settings):
    store.settings(payload.model_dump())
    return {"ok":True}

class Rating(BaseModel):
    id:str
    value:Literal[-1,0,1]|None

@app.post("/api/rating")
def rating(payload:Rating):
    data=store.get()
    l=next((l for l in data["listings"] if l["id"]==payload.id),None)
    if not l: raise HTTPException(404,"Apartment not found.")
    if payload.value is not None and (filter_reasons(l,data["settings"]) or not l.get("vision")):
        raise HTTPException(422,"You can rate apartments with photos that pass your filters.")
    context=learning.snapshot([l],data["settings"],[l["id"]] if payload.value==1 else [],photo_hashes,engine_queue)
    try: event=store.rating(payload.id,payload.value,context=context)
    except ValueError as error: raise HTTPException(409,str(error))
    return {"ok":True,"memory_event":event,"evaluation_only":event is None}

class Comparison(BaseModel):
    a:str
    b:str
    choice:Literal[-1,0,1]

class TeacherReview(BaseModel):
    id:str
    value:Literal[-1,0,1]
    criteria_id:str=Field(min_length=1,max_length=100)
    confidence:Literal["high","medium","low"]
    reasons:list[str]=Field(min_length=1,max_length=12)
    unknowns:list[str]=Field(max_length=12)
    inspected_photo_sha256:list[str]=Field(min_length=1,max_length=100)
    photo_notes:list[str]=Field(min_length=1,max_length=100)
    location:dict
    listing_snapshot:dict
    price_per_m2:float|None=None

class TeacherBatch(BaseModel):
    reviews:list[TeacherReview]=Field(min_length=1,max_length=100)

def teacher_listing_snapshot(listing):
    return {k:listing.get(k) for k in ("price","size","bedrooms","coords","coord_kind","parking",
                                      "balcony","balcony_size","balcony_covered")}

@app.post("/api/teacher/reviews")
def teacher_reviews(payload:TeacherBatch):
    data=store.get()
    listings={l["id"]:l for l in data["listings"]}
    contexts=[]
    if len({r.id for r in payload.reviews}) != len(payload.reviews):
        raise HTTPException(422,"Review each apartment once per batch.")
    for review in payload.reviews:
        l=listings.get(review.id)
        if not l or not l.get("vision"):
            raise HTTPException(422,"Assistant reviews require photos.")
        if review.value==1 and filter_reasons(l,data["settings"]):
            raise HTTPException(422,"A shortlist recommendation must pass the brief.")
        actual=[photo_hashes(p) for p in l["photos"]]
        if review.listing_snapshot != teacher_listing_snapshot(l) or review.location != highway_position(l):
            raise HTTPException(409,"The listing or location evidence changed since the assistant inspection.")
        if review.inspected_photo_sha256 != actual or len(review.photo_notes) != len(actual):
            raise HTTPException(409,"Inspect and describe every current photo before recording an assistant review.")
        if review.value==1:
            position=highway_position(l)
            if position["status"] != "source_pin" or position["north_of_highway"] or position["near_highway"]:
                raise HTTPException(422,"A shortlist recommendation requires an individual source pin south of the motorway and at least 300 m from it.")
        context=learning.snapshot([l],data["settings"],[l["id"]] if review.value==1 else [],photo_hashes,engine_queue)
        context["teacher_review"]={"actor":"agent",**review.model_dump()}
        contexts.append(context)
    try: events=store.teacher_reviews([r.model_dump() for r in payload.reviews],contexts)
    except ValueError as error: raise HTTPException(409,str(error))
    return {"ok":True,"reviews":events,"label_source":"agent","human_choices_created":0}

@app.post("/api/compare")
def compare(payload:Comparison):
    data=store.get()
    valid={l["id"] for l in data["listings"] if not filter_reasons(l,data["settings"]) and l.get("vision")}
    if payload.a==payload.b or payload.a not in valid or payload.b not in valid:
        raise HTTPException(422,"Two different apartments with photos that pass your filters are required.")
    members=[l for l in data["listings"] if l["id"] in (payload.a,payload.b)]
    winner=[payload.a] if payload.choice==1 else [payload.b] if payload.choice==-1 else []
    context=learning.snapshot(members,data["settings"],winner,photo_hashes,engine_queue)
    try: event=store.compare(payload.a,payload.b,payload.choice,context=context)
    except ValueError as error: raise HTTPException(409,str(error))
    return {"ok":True,"memory_event":event,"evaluation_only":event is None}

@app.get("/api/learning")
def learning_status():
    return {**learning.status(store,engine_queue),"evaluation":evaluation.latest(engine_queue),
            "prospective":prospective.latest(store),
            "analysis_stamp":engine_queue.activity_stamp(),
            "evaluation_progress":json.loads(engine_queue.state("evaluation_progress") or "null")}

@app.post("/api/learning/sync")
def sync_learning():
    """Use the actual saved choices, including choices predating the journal."""
    data=store.get()
    listings={l["id"]:l for l in eligible_listings(data)}
    journal=[]
    for id,value in data["ratings"].items():
        if id in listings:
            context=learning.snapshot([listings[id]],data["settings"],[id] if value==1 else [],photo_hashes,engine_queue)
            origin=data.get("feedback_provenance",{}).get(f"rating:{id}",{})
            if origin.get("actor")=="agent": context["teacher_review"]=origin
            journal.append((f"rating:{id}","rating",value,context))
    for pair in data["comparisons"]:
        if pair["a"] in listings and pair["b"] in listings:
            members=[listings[pair["a"]],listings[pair["b"]]]
            winners=[pair["a"]] if pair["choice"]==1 else [pair["b"]] if pair["choice"]==-1 else []
            context=learning.snapshot(members,data["settings"],winners,photo_hashes,engine_queue)
            journal.append((f"pair:{pair['a']}:{pair['b']}","comparison",pair["choice"],context))
    # Bootstrap is one publication: the worker never sees a partial history,
    # and copying existing feedback preserves its original timestamps.
    with store.lock, store.connect() as db:
        for key,kind,value,context in journal:
            if not prospective.feedback_is_held(db,context): learning.record(db,key,kind,value,context)
    return learning_status()

@app.post("/api/learning/retry")
def retry_learning():
    engine_queue.set_state("memory_last_attempt",engine_queue.state("memory_revision") or "0")
    return {"ok":True}

@app.post("/api/learning/evaluate")
def evaluate_learning():
    try:
        key=evaluation.enqueue(engine_queue,store,photo_hashes)
        engine_queue.set_state("selected_evaluation",key)
    except (ValueError,OSError) as error:
        raise HTTPException(422,str(error))
    return {"id":key}

class Reservation(BaseModel):
    candidate_ids:list[str]|None=Field(default=None,max_length=100)

@app.post("/api/learning/reserve")
def reserve_cohort(payload:Reservation|None=None):
    try: return prospective.reserve(store,engine_queue,photo_hashes,
                                   candidate_ids=payload.candidate_ids if payload else None)
    except (ValueError,OSError) as error: raise HTTPException(422,str(error))

@app.post("/api/learning/evaluate-prospective")
def evaluate_cohort():
    try:
        key=evaluation.enqueue_prospective(engine_queue,store)
        engine_queue.set_state("selected_evaluation",key)
        return {"id":key}
    except (ValueError,OSError) as error: raise HTTPException(422,str(error))

@app.get("/api/learning/report")
def evaluation_report():
    report=evaluation.latest(engine_queue)
    if not report or not report.get("result"): raise HTTPException(404,"No completed evaluation report yet.")
    return JSONResponse(report,headers={"Content-Disposition":"attachment; filename=fly-estate-evaluation.json"})

@app.get("/api/learning/replay/{revision}/{phase}")
def learning_replay(revision:int,phase:Literal["before","after"]):
    with engine_queue.connect() as db:
        row=db.execute("SELECT result FROM learning_runs WHERE revision=? AND status='done'",(revision,)).fetchone()
    if not row: raise HTTPException(404,"Memory recording not found.")
    result=json.loads(row["result"])
    recorded=result["recordings"].get(phase)
    if not recorded: raise HTTPException(409,"No recorded probe for this choice.")
    checkpoint=result["before_checkpoint"] if phase=="before" else result["checkpoint"]
    with engine_queue.connect() as db:
        cp=db.execute("SELECT fingerprint FROM checkpoints WHERE hash=?",(checkpoint,)).fetchone()
    return {**replay_display(recorded["trace"]),"listing_id":result["listing_id"],"position":recorded["position"],
            "checkpoint":checkpoint,"fingerprint":cp["fingerprint"],"live":False,"memory_phase":phase}

@app.get("/api/learning/connections/{revision}")
def learning_connections(revision:int):
    with engine_queue.connect() as db:
        row=db.execute("SELECT result FROM learning_runs WHERE revision=? AND status='done'",(revision,)).fetchone()
    if not row: raise HTTPException(404,"Memory changes not found.")
    result=json.loads(row["result"])
    indices={str(id):i for i,id in enumerate(brain.nodes["ids"])}
    return {"revision":revision,"changed_connections":result["changed_connections"],"checkpoint":result["checkpoint"],
            "edges":[{**e,"pre":indices[e["pre_id"]],"post":indices[e["post_id"]]} for e in result["edges"]
                     if e["pre_id"] in indices and e["post_id"] in indices]}

class Import(BaseModel):
    url:str=""
    content:str=Field(default="",max_length=4000000)
    listing:dict|None=None
    uploads:list[str]=Field(default_factory=list,max_length=100)
    urls:list[str]=Field(default_factory=list,max_length=100)

def store_embedding(photo,vector):
    engine_queue.put_embedding(photo_hashes(photo),MODEL_ID,REVISION,vector)

def ensure_embeddings(photos):
    """CLIP embeddings for the Cyborg codec, computed once per photo content."""
    missing=[p for p in photos if engine_queue.get_embedding(photo_hashes(p),MODEL_ID,REVISION) is None]
    if missing:
        with vision_lock: vectors=vision.embed(missing)
        for photo,vector in zip(missing,vectors): store_embedding(photo,vector)

def import_job(id,payload):
    job=jobs[id]
    try:
        content=payload.listing or payload.content
        advert_urls=payload.urls or ([payload.url] if not content and bazaraki.ADVERT.match(importers.urlparse(payload.url).path or "")
                                     and importers.urlparse(payload.url).hostname in ("www.bazaraki.com","bazaraki.com") else [])
        if advert_urls:
            # Bazaraki adverts are read from their page data one by one (server/bazaraki.py).
            content=[{"_bazaraki":u} for u in dict.fromkeys(advert_urls)]
        elif not content and payload.url:
            content=importers.fetch(payload.url,importers.ALLOWED_SOURCES,4*1024*1024).decode("utf8",errors="replace")
        backup=content if isinstance(content,dict) else None
        if isinstance(content,str):
            try: backup=json.loads(content)
            except (ValueError,TypeError): pass
        if not isinstance(backup,dict) or backup.get("version")!=1 or "listings" not in backup: backup=None
        restored_settings=Settings.model_validate(backup["settings"]).model_dump() if backup else None
        items=content if advert_urls else importers.parse(content)
        limit=1000 if backup else 100
        if not items or len(items)>limit: raise ValueError(f"Import between 1 and {limit:,} listings at a time.")
        job["total"]=len(items)
        import_settings=store.get()["settings"]
        existing={l["id"]:l for l in store.get()["listings"]}
        restored_ids={}
        for item in items:
            try:
                if "_bazaraki" in item:
                    job["phase"]="Reading the advert"
                    item=bazaraki.advert(item["_bazaraki"])
                if not item.get("url") and payload.url: item["url"]=payload.url
                l=importers.normalize(item)
                job["phase"]="Downloading photos"
                previous=existing.get(l["id"]) or next((p for p in existing.values() if catalogue_data.same_apartment(p,l)),None)
                warnings=importers.photos(l,payload.uploads if len(items)==1 else [],previous)
                if warnings: job["warnings"].append(l["title"]+f': available {len(l["photos"])} of {max(len(l["photo_urls"]),len(l["photos"]))} photos.')
                job["phase"]="Photos → encoder → neural signals"
                if l["photos"]:
                    with vision_lock:
                        l["vision"]=vision.encode(l["photos"],on_embedding=store_embedding)
                    job["phase"]="Every photo → neurons → MBON/CX"
                    with model_lock:
                        brain.features([l],import_settings)
                l["import_warnings"]=warnings
                if not l["photos"]: job["warnings"].append(l["title"]+": photos could not be downloaded; rating is disabled.")
                store.listing(l)
                existing[l["id"]]=l
                job["listing_ids"].append(l["id"])
                if item.get("id"): restored_ids[item["id"]]=l["id"]
                job["imported"]+=1
            except Exception as e:
                logging.exception("Listing import failed")
                if isinstance(e,importers.SourceRemoved): store.source_removed(item.get("_bazaraki") or item.get("url") or payload.url)
                job["errors"].append(str(e))
            job["done"]+=1
        if not job["imported"]: raise ValueError("; ".join(job["errors"]) or "Import did not complete.")
        if backup:
            for old_id,value in backup.get("ratings",{}).items():
                if backup.get("feedback_provenance",{}).get(f"rating:{old_id}",{}).get("actor")=="agent":
                    continue
                if old_id in restored_ids and type(value) is int and value in (-1,0,1): store.rating(restored_ids[old_id],value)
            for pair in backup.get("comparisons",[]):
                if pair.get("a") in restored_ids and pair.get("b") in restored_ids and pair["a"]!=pair["b"] and type(pair.get("choice")) is int and pair["choice"] in (-1,0,1):
                    store.compare(restored_ids[pair["a"]],restored_ids[pair["b"]],pair["choice"])
            store.settings(restored_settings)
            job["warnings"].append("Rules and ratings restored for successfully imported apartments. Manually uploaded photos must be added again.")
        job.update(status="done",phase="Done")
    except Exception as e:
        logging.exception("Import failed")
        if isinstance(e,importers.SourceRemoved) and payload.url: store.source_removed(payload.url)
        job.update(status="error",phase="Error",error=str(e))

@app.post("/api/import")
def start_import(payload:Import):
    if len([j for j in jobs.values() if j["status"]=="running"])>=1:
        raise HTTPException(409,"Wait for the current import to finish.")
    id=uuid.uuid4().hex
    jobs[id]={"id":id,"status":"running","phase":"Reading listing","total":0,"done":0,"imported":0,"errors":[],"warnings":[],"listing_ids":[],
              "source":"import","started_at":now()}
    threading.Thread(target=import_job,args=(id,payload),daemon=True).start()
    return {"job":id}

@app.get("/api/sources/bazaraki")
def bazaraki_market(pages:int=Query(bazaraki.PAGES,ge=1,le=10),force:bool=False):
    """Offers on Bazaraki under the brief's hard limit, for the map and the brief (D1)."""
    settings=store.get()["settings"]
    try: market=bazaraki.market(settings["ceiling"],settings["min_bedrooms"],pages,force=force)
    except importers.SourceBlocked as e: raise HTTPException(503,f"Source blocked or rate limited: {e}")
    except Exception as e: raise HTTPException(502,f"Bazaraki could not be read: {e}")
    listings=store.get()["listings"]
    known={catalogue_data.identity(s.get("url")):l["id"] for l in listings
           for s in ([l]+l.get("sources",[])) if s.get("url")}
    excluded={x.casefold() for x in settings["excluded"]}
    offers=[{**o,"listing_id":known.get(catalogue_data.identity(o["url"])),
             "excluded_area":any(x in o["area"].casefold() for x in excluded)} for o in market["offers"]]
    return {**market,"offers":offers,"imported":sum(1 for o in offers if o["listing_id"]),
            "new":sum(1 for o in offers if not o["listing_id"] and not o["excluded_area"])}

class Sync(BaseModel):
    limit:int=Field(40,ge=1,le=100)
    pages:int=Field(bazaraki.PAGES,ge=1,le=10)

@app.post("/api/catalogue/refresh/{listing_id}")
def refresh_listing(listing_id:str):
    listing=next((l for l in store.get()["listings"] if l["id"]==listing_id),None)
    if not listing or not listing.get("url"): raise HTTPException(422,"A source URL is needed to refresh this apartment.")
    return start_import(Import(url=listing["url"]))

@app.get("/api/catalogue/status")
def catalogue_status():
    listings=store.get()["listings"]
    return {"listings":len(listings),"stale":sum(catalogue_data.freshness(l)["stale"] for l in listings),
            "unavailable":sum(l.get("available") is False for l in listings),
            "failed_photos":sum(p.get("status")=="unavailable" for l in listings for p in l.get("photo_downloads",[])),
            "source":bazaraki.connector_status()}

@app.get("/api/sources/status")
def source_status(): return {"bazaraki":bazaraki.connector_status()}

@app.post("/api/sources/bazaraki/sync")
def bazaraki_sync(payload:Sync):
    """The agent's search: import the newest Bazaraki offers that fit the brief and are not in the file yet."""
    urls=[o["url"] for o in bazaraki_market(payload.pages)["offers"] if not o["listing_id"] and not o["excluded_area"]]
    if not urls: return {"job":None,"queued":0,"remaining":0}
    started=start_import(Import(urls=urls[:payload.limit]))
    jobs[started["job"]]["source"]="bazaraki"
    return {**started,"queued":min(len(urls),payload.limit),"remaining":max(0,len(urls)-payload.limit)}

@app.get("/api/jobs")
def job_list(limit:int=Query(10,ge=1,le=50)):
    """Running and recent import jobs, newest first; the map panel finds a search started elsewhere with it."""
    recent=list(jobs.values())[::-1]
    return {"running":[j for j in recent if j["status"]=="running"],"recent":recent[:limit]}

@app.get("/api/jobs/{id}")
def job(id:str):
    if id not in jobs: raise HTTPException(404,"Import not found.")
    return jobs[id]

@app.get("/api/export")
def export():
    data=store.get(archived=True)
    data["ratings"]={i:v for i,v in data["ratings"].items()
                     if data.get("feedback_provenance",{}).get(f"rating:{i}",{}).get("actor")!="agent"}
    data["transfer_note"]="This lightweight file restores human choices only. Use the full session ZIP for assistant reviews and exact learned memory."
    # Recompute machine-local photo paths and encoder tensors after restoring.
    data["listings"]=[{k:v for k,v in l.items() if k not in ("photos","vision","import_warnings","photo_downloads")} for l in data["listings"]]
    return JSONResponse({"version":1,"exported_at":now(),**data},headers={"Content-Disposition":"attachment; filename=fly-estate-backup.json"})

@app.get("/api/session/export")
def session_export():
    from .session import export_session
    if any(j["status"]=="running" for j in jobs.values()):
        raise HTTPException(409,"Wait for the current import to finish before exporting a session.")
    directory=ROOT/".cache/session-exports"
    path=directory/(uuid.uuid4().hex+".zip")
    try: export_session(store,engine_queue,path)
    except Exception as error:
        path.unlink(missing_ok=True)
        raise HTTPException(500,f"Session export failed: {error}")
    return FileResponse(path,media_type="application/zip",filename="fly-estate-session.zip",
                        background=BackgroundTask(path.unlink,missing_ok=True))

@app.get("/api/catalogue")
def catalogue():
    fields=["url","title","price","bedrooms","size","area","city","parking","balcony","balcony_size","balcony_covered","furnished","coords","coord_kind","photo_urls","published_at"]
    return [{k:l.get(k) for k in fields} for l in store.get()["listings"]]

@app.get("/api/health")
def health(): return {"ok":True,"dataset":brain.summary["dataset"],"neurons":brain.summary["neurons"]}

@app.get("/api/engine")
def engine_status():
    """Spiking engine: worker liveness, current weights and queue. The engine runs in `server.worker`."""
    return {"engine":engine_queue.state("engine_version"),"subgraph_ready":subgraph.OUTPUT.exists(),
            "worker":engine_queue.worker_status(),"checkpoint":engine_checkpoints.current(),
            "queue":engine_queue.counts()}

class Simulation(BaseModel):
    listing_id:str=Field(min_length=1,max_length=64)

@app.post("/api/simulations")
def start_simulation(payload:Simulation):
    """Queue every photo of a listing with the brief's current codec (Pure/Cyborg) and brief snapshot."""
    data=store.get()
    l=next((l for l in data["listings"] if l["id"]==payload.listing_id),None)
    if not l: raise HTTPException(404,"Apartment not found.")
    if not l.get("photos") or not (l.get("vision") or {}).get("per_photo"):
        raise HTTPException(422,"Photos with encoder signals are required for a simulation.")
    params=job_params(data["settings"])
    if params["mode"]=="cyborg":
        try: ensure_embeddings(l["photos"])
        except OSError as e: raise HTTPException(422,f"A photo could not be read: {e}")
        try: engine_queue.freeze_center(MODEL_ID,REVISION)
        except LookupError as e: raise HTTPException(422,str(e))
    job,created=engine_queue.enqueue(l["id"],l["photos"],params)
    return {"job":job,"created":created,"worker":engine_queue.worker_status()}

def eligible_listings(data):
    return [l for l in data["listings"] if not filter_reasons(l,data["settings"]) and l.get("photos") and (l.get("vision") or {}).get("per_photo")]

@app.post("/api/simulations/portfolio")
def start_portfolio():
    """Queue every photo of every listing that passes the brief and is not yet fully simulated."""
    data=store.get()
    listings=eligible_listings(data)
    params=job_params(data["settings"])
    if params["mode"]=="cyborg":
        try: ensure_embeddings([p for l in listings for p in l["photos"]])
        except OSError as e: raise HTTPException(422,f"A photo could not be read: {e}")
        try: engine_queue.freeze_center(MODEL_ID,REVISION)
        except LookupError as e: raise HTTPException(422,str(e))
    ready=portfolio_readout()
    queued=[]
    for l in listings:
        if l["id"] not in ready["complete_ids"]:
            job,_=engine_queue.enqueue(l["id"],l["photos"],params)
            queued.append(job["id"])
    return {"queued":len(queued),"complete":len(ready["complete_ids"]),"eligible":len(listings),"worker":engine_queue.worker_status()}

PROXY_STUDY=ROOT/"reports/results/aggregation_proxy.json"
readout_cache={}

def portfolio_readout():
    data=store.get()
    train_ratings,train_pairs,held=prospective.training(data,store,photo_hashes)
    listings=eligible_listings(data)
    key=json.dumps([engine_queue.state("current_fingerprint"),job_params(data["settings"]),engine_queue.activity_stamp(),
                    train_ratings,train_pairs,sorted(held),[(l["id"],l.get("updated_at")) for l in listings]],sort_keys=True,default=str)
    if key not in readout_cache:
        fallback=None
        if PROXY_STUDY.exists():
            study=json.loads(PROXY_STUDY.read_text(encoding="utf-8"))
            fallback={"selected":study["selected"],"reason":study["reason"],"label":study["label"],
                      "results":study.get("results"),"study":PROXY_STUDY.relative_to(ROOT).as_posix()}
        result=portfolio(engine_queue,listings,data["settings"],train_ratings,train_pairs,photo_hashes,fallback,
                         normalization_ids=[l["id"] for l in listings if l["id"] not in held])
        readout_cache.clear()
        readout_cache[key]=result
    return readout_cache[key]

@app.get("/api/engine/readout")
def engine_readout():
    """Spiking score of every fully simulated listing, the photo aggregator and how it was selected."""
    return {k:v for k,v in portfolio_readout().items() if k!="complete_ids"}

@app.get("/api/simulations")
def simulations(listing_id:str|None=None,limit:int=Query(default=20,ge=1,le=100)):
    return engine_queue.list(listing_id,limit)

@app.get("/api/simulations/{id}")
def simulation(id:str):
    job=engine_queue.get(id)
    if not job: raise HTTPException(404,"Simulation not found.")
    return job

@app.post("/api/simulations/{id}/cancel")
def cancel_simulation(id:str):
    job=engine_queue.cancel(id)
    if not job: raise HTTPException(404,"Simulation not found.")
    return job

@app.get("/api/engine/gallery/{id}")
def engine_gallery(id:str):
    """Per-photo readiness under the current brief, codec and weights."""
    data=store.get()
    l=next((l for l in data["listings"] if l["id"]==id),None)
    if not l: raise HTTPException(404,"Apartment not found.")
    return gallery(engine_queue,l,data["settings"],photo_hashes)

@app.get("/api/engine/activity/{id}")
def engine_activity(id:str):
    """Latest spiking result per photo; `stale` marks results produced with other weights."""
    return engine_queue.listing_activity(id)

def replay_display(trace):
    try:
        return project_replay(trace, brain.nodes["ids"], subgraph.OUTPUT)
    except (ValueError, OSError) as error:
        raise HTTPException(409,str(error))

@app.get("/api/engine/replay/{key}")
def engine_replay(key:str):
    result=engine_queue.get_activity(key)
    if not result: raise HTTPException(404,"Spiking response not found.")
    trace=result["result"].get("replay")
    if not trace: raise HTTPException(409,"Run the model to record its spikes for the brain view.")
    return {**replay_display(trace),"position":result["position"],"listing_id":result["listing_id"],
            "checkpoint":result["checkpoint"],"fingerprint":result["fingerprint"],"live":False}

@app.get("/api/engine/live/{job_id}")
def engine_live(job_id:str,photo:int=Query(ge=0)):
    live=json.loads(engine_queue.state("live_replay") or "null")
    job=engine_queue.get(job_id,items=False)
    if not live or not job or job["status"]!="running" or live["job_id"]!=job_id or live["position"]!=photo:
        return {"available":False}
    return {**replay_display(live["trace"]),"position":photo,"listing_id":live["listing_id"],
            "fingerprint":live["fingerprint"],"checkpoint":job["checkpoint"],"live":True}

@app.get("/api/brain/geometry")
def geometry_data(): return Response(geometry.tobytes(),media_type="application/octet-stream")

@app.get("/api/brain/lines")
def line_data(): return Response(lines.tobytes(),media_type="application/octet-stream")

@app.get("/api/brain/meta")
def geometry_meta():
    return {"neurons":len(geometry),"lines":len(lines),"frames":16,"coordinates":"Annotation anchors, voxel size 4×4×40 nm; not neuron morphologies.","activity":"Relative absolute rate, square-root scaled per frame; not measured firing rates."}

@app.get("/api/brain/neuron/{index}")
def neuron(index:int):
    if not 0<=index<len(brain.nodes["ids"]): raise HTTPException(404,"Neuron not found.")
    return {"id":str(brain.nodes["ids"][index]),"type":str(brain.nodes["types"][index]) or "Untyped", "group":str(brain.nodes["classes"][index]) or "Other group",
            "incoming":brain.w[index].nnz,"outgoing":brain.w.getcol(index).nnz}

@app.get("/api/brain/activity/{id}")
def activity(id:str,photo:int|None=Query(default=None,ge=0)):
    data=store.get();l=next((l for l in data["listings"] if l["id"]==id),None)
    if not l or not l.get("vision"): raise HTTPException(422,"Photos are required to compute activity.")
    if filter_reasons(l,data["settings"]): raise HTTPException(422,"Apartment excluded by hard filters.")
    if photo is not None:
        photo_signals=l["vision"].get("per_photo",[])
        if photo>=len(photo_signals): raise HTTPException(422,"This photo has not been processed yet: import the listing again.")
        l={**l,"vision":photo_signals[photo]}
    with model_lock: _,_,frames=brain.features([l],data["settings"],record=True)
    return Response(frames.tobytes(),media_type="application/octet-stream",headers={"X-Neurons":str(frames.shape[1]),"X-Frames":str(frames.shape[0])})
