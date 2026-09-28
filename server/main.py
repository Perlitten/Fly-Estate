from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
import json
import threading
import uuid
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, model_validator
from .storage import Store, ROOT, DEFAULT_SETTINGS, filter_reasons, now
from .brain import Brain, distance_km
from .vision import Vision
from . import importers

store=Store()
brain=None
vision=Vision()
model_lock=threading.RLock()
jobs={}
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
    with model_lock:
        eligible=[l for l in data["listings"] if not filter_reasons(l,data["settings"])]
        predictions,training=brain.predict(eligible,data["settings"],data["ratings"],data["comparisons"])
    for l in data["listings"]:
        l["prediction"]=predictions.get(l["id"],{"decision":"waiting","probability":0.5,"price_aversion":0,"trace":{},
                "distance":round(distance_km(data["settings"]["ideal"],l["coords"]),1) if l.get("coords") else None})
        l["filter_reasons"]=filter_reasons(l,data["settings"])
        l["rating"]=data["ratings"].get(l["id"])
    return {**data,"brain":brain.summary,"training":training,"areas":json.loads((ROOT/"data/areas.json").read_text())}

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
    store.rating(payload.id,payload.value)
    return {"ok":True}

class Comparison(BaseModel):
    a:str
    b:str
    choice:Literal[-1,0,1]

@app.post("/api/compare")
def compare(payload:Comparison):
    data=store.get()
    valid={l["id"] for l in data["listings"] if not filter_reasons(l,data["settings"]) and l.get("vision")}
    if payload.a==payload.b or payload.a not in valid or payload.b not in valid:
        raise HTTPException(422,"Two different apartments with photos that pass your filters are required.")
    store.compare(payload.a,payload.b,payload.choice)
    return {"ok":True}

class Import(BaseModel):
    url:str=""
    content:str=Field(default="",max_length=4000000)
    listing:dict|None=None
    uploads:list[str]=Field(default_factory=list,max_length=100)

def import_job(id,payload):
    job=jobs[id]
    try:
        content=payload.listing or payload.content
        if not content and payload.url:
            content=importers.fetch(payload.url,importers.ALLOWED_SOURCES,4*1024*1024).decode("utf8",errors="replace")
        backup=content if isinstance(content,dict) else None
        if isinstance(content,str):
            try: backup=json.loads(content)
            except (ValueError,TypeError): pass
        if not isinstance(backup,dict) or backup.get("version")!=1 or "listings" not in backup: backup=None
        restored_settings=Settings.model_validate(backup["settings"]).model_dump() if backup else None
        items=importers.parse(content)
        if not items or len(items)>100: raise ValueError("Import between 1 and 100 listings at a time.")
        job["total"]=len(items)
        import_settings=store.get()["settings"]
        restored_ids={}
        for item in items:
            try:
                if not item.get("url") and payload.url: item["url"]=payload.url
                l=importers.normalize(item)
                job["phase"]="Downloading photos"
                warnings=importers.photos(l,payload.uploads if len(items)==1 else [])
                if warnings: job["warnings"].append(l["title"]+f': available {len(l["photos"])} of {max(len(l["photo_urls"]),len(l["photos"]))} photos.')
                job["phase"]="Photos → encoder → neural signals"
                if l["photos"]:
                    with model_lock:
                        l["vision"]=vision.encode(l["photos"])
                        job["phase"]="Every photo → neurons → MBON/CX"
                        brain.features([l],import_settings)
                l["import_warnings"]=warnings
                if not l["photos"]: job["warnings"].append(l["title"]+": photos could not be downloaded; rating is disabled.")
                store.listing(l)
                if item.get("id"): restored_ids[item["id"]]=l["id"]
                job["imported"]+=1
            except Exception as e:
                logging.exception("Listing import failed")
                job["errors"].append(str(e))
            job["done"]+=1
        if not job["imported"]: raise ValueError("; ".join(job["errors"]) or "Import did not complete.")
        if backup:
            for old_id,value in backup.get("ratings",{}).items():
                if old_id in restored_ids and type(value) is int and value in (-1,0,1): store.rating(restored_ids[old_id],value)
            for pair in backup.get("comparisons",[]):
                if pair.get("a") in restored_ids and pair.get("b") in restored_ids and pair["a"]!=pair["b"] and type(pair.get("choice")) is int and pair["choice"] in (-1,0,1):
                    store.compare(restored_ids[pair["a"]],restored_ids[pair["b"]],pair["choice"])
            store.settings(restored_settings)
            job["warnings"].append("Rules and ratings restored for successfully imported apartments. Manually uploaded photos must be added again.")
        job.update(status="done",phase="Done")
    except Exception as e:
        logging.exception("Import failed")
        job.update(status="error",phase="Error",error=str(e))

@app.post("/api/import")
def start_import(payload:Import):
    if len([j for j in jobs.values() if j["status"]=="running"])>=1:
        raise HTTPException(409,"Wait for the current import to finish.")
    id=uuid.uuid4().hex
    jobs[id]={"id":id,"status":"running","phase":"Reading listing","total":0,"done":0,"imported":0,"errors":[],"warnings":[]}
    threading.Thread(target=import_job,args=(id,payload),daemon=True).start()
    return {"job":id}

@app.get("/api/jobs/{id}")
def job(id:str):
    if id not in jobs: raise HTTPException(404,"Import not found.")
    return jobs[id]

@app.get("/api/export")
def export():
    data=store.get()
    # Portable public listing snapshots, annotations and preferences. Photos can be downloaded again.
    return JSONResponse({"version":1,"exported_at":now(),**data},headers={"Content-Disposition":"attachment; filename=fly-estate-backup.json"})

@app.get("/api/catalogue")
def catalogue():
    fields=["url","title","price","bedrooms","size","area","city","parking","balcony","balcony_size","balcony_covered","furnished","coords","coord_kind","photo_urls","published_at"]
    return [{k:l.get(k) for k in fields} for l in store.get()["listings"]]

@app.get("/api/health")
def health(): return {"ok":True,"dataset":brain.summary["dataset"],"neurons":brain.summary["neurons"]}

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
