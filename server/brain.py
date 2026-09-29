"""Connectome-constrained reservoir and an explicitly artificial task readout."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
import pickle
import threading
import numpy as np
from scipy import sparse, optimize
from scipy.special import expit
from .vision import SEMANTIC_KEYS

ROOT = Path(__file__).resolve().parents[1]
# Признаки объявлений переживают перезапуск: без этого первый /api/state считал все фото заново.
CACHE_PATH = ROOT / ".cache/brain_features.pkl"

def distance_km(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2-lat1, math.radians(b[1]-a[1])
    s = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371*2*math.asin(min(1, math.sqrt(s)))

class Brain:
    def __init__(self):
        self.summary = json.loads((ROOT / "data/brain/summary.json").read_text(encoding="utf-8"))
        self.w = sparse.load_npz(ROOT / "data/brain/weights.npz")
        self.cx_pool = sparse.load_npz(ROOT / "data/brain/cx_pool.npz")
        self.nodes = np.load(ROOT / "data/brain/neurons.npz")
        # scipy умножает разреженную матрицу в один поток; строки весов делятся между потоками
        # (sparsetools отпускает GIL), результат побитно тот же.
        workers = max(1, min(12, os.cpu_count() or 1))
        bounds = np.linspace(0, self.w.shape[0], workers + 1).astype(int)
        self.row_blocks = [(a, b, self.w[a:b]) for a, b in zip(bounds[:-1], bounds[1:])]
        self.pool = ThreadPoolExecutor(workers) if workers > 1 else None
        self.cache_lock = threading.Lock()
        self.cache_tag = self._cache_tag()
        self.cache = self._load_cache()
        self.rng = np.random.default_rng(783)
        self.semantic_projection = self.rng.normal(0, 1, (len(self.nodes["cyborg"]), len(SEMANTIC_KEYS))).astype(np.float32) / np.sqrt(len(SEMANTIC_KEYS))
        for name in ("spacious", "large_balcony", "sheltered_balcony"):
            col = SEMANTIC_KEYS.index(name)
            self.semantic_projection[:, col] = np.abs(self.semantic_projection[:, col])
        self.meta_projection = self.rng.normal(0, 1, (len(self.nodes["metadata"]), 8)).astype(np.float32) / np.sqrt(8)
        # User-specified positive sensory drives for space, balcony, its size and shelter.
        # These are artificial preference channels, not identified biological functions.
        self.meta_projection[:,[1,5,6,7]]=np.abs(self.meta_projection[:,[1,5,6,7]])
        self.nav_projection = self.rng.normal(0, 1, (len(self.nodes["nav"]), 4)).astype(np.float32) / 2

    def _cache_tag(self):
        """Код расчёта и файлы весов: при их изменении сохранённые признаки не используются."""
        digest = hashlib.sha256(Path(__file__).read_bytes())
        for name in ("weights.npz", "cx_pool.npz", "neurons.npz"):
            stat = (ROOT / "data/brain" / name).stat()
            digest.update(f"{name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        return digest.hexdigest()

    def _load_cache(self):
        try:
            saved = pickle.loads(CACHE_PATH.read_bytes())
            return saved["entries"] if saved.get("tag") == self.cache_tag else {}
        except (OSError, pickle.UnpicklingError, EOFError, KeyError, TypeError, AttributeError):
            return {}

    def _save_cache(self):
        with self.cache_lock:
            payload = pickle.dumps({"tag": self.cache_tag, "entries": dict(self.cache)})
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary = CACHE_PATH.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(payload)
            os.replace(temporary, CACHE_PATH)

    def _step(self, state, drive):
        """Один шаг резервуара; каждый поток считает свой блок строк целиком."""
        if not self.pool:
            return 0.35*state + 0.65*np.tanh(0.92*(self.w @ state) + drive)
        out = np.empty_like(state)
        def run(block):
            a, b, rows = block
            out[a:b] = 0.35*state[a:b] + 0.65*np.tanh(0.92*(rows @ state) + drive[a:b])
        list(self.pool.map(run, self.row_blocks))
        return out

    def features(self, listings, settings, record=False):
        if not listings: return np.zeros((0,len(self.nodes["mbon"])+self.cx_pool.shape[0])),[]
        outputs,signals=[],[]
        recorded=None;computed=False
        for listing in listings:
            key=json.dumps([settings["mode"],settings["budget"],settings["ideal"],listing["id"],listing.get("updated_at"),"all-photos-v2"],sort_keys=True)
            if not record and key in self.cache:
                out,signal=self.cache[key];outputs.append(out);signals.append(signal);continue
            vision=listing.get("vision")
            photo_signals=(vision.get("per_photo") or [vision]) if vision else [None]
            photo_listings=[{**listing,"vision":v} for v in photo_signals]
            count=len(photo_listings)
            accumulated=None;trace={};base_signal=None;amplitudes=None
            for start in range(0,count,24):
                batch=photo_listings[start:start+24]
                result=self._calculate(batch,settings,record=record)
                x,batch_signals=result[:2]
                accumulated=x.sum(axis=0) if accumulated is None else accumulated+x.sum(axis=0)
                base_signal=batch_signals[0]
                for signal in batch_signals:
                    for name,value in signal["trace"].items(): trace[name]=trace.get(name,0)+value
                if record:
                    weighted=result[2]*len(batch)
                    amplitudes=weighted if amplitudes is None else amplitudes+weighted
            out=accumulated/count
            signal={**base_signal,"trace":{k:round(v/count,6) for k,v in trace.items()},"photos_analyzed":count if vision else 0}
            outputs.append(out);signals.append(signal)
            if not record:
                if len(self.cache)>=1024: self.cache.pop(next(iter(self.cache)))
                self.cache[key]=(out,signal);computed=True
            else:
                amplitude=amplitudes/count
                maximum=np.maximum(amplitude.max(axis=1,keepdims=True),1e-8)
                recorded=(np.sqrt(amplitude/maximum)*255).astype(np.uint8)
        if computed: self._save_cache()
        return (np.array(outputs),signals,recorded) if record else (np.array(outputs),signals)

    def _calculate(self, listings, settings, record=False):
        n, batch = self.w.shape[0], len(listings)
        if not batch:
            return np.zeros((0, len(self.nodes["mbon"]) + self.cx_pool.shape[0])), []
        drive = np.zeros((n, batch), np.float32)
        signals = []
        for j, l in enumerate(listings):
            v = l.get("vision")
            if not v:
                signals.append({"distance": None, "price_aversion": 0, "trace": {}})
                continue
            if settings["mode"] == "pure":
                retina = np.asarray(v["retina"], np.float32)
                visual = self.nodes["visual"]
                # Deterministic custom retinal adapter, not a recovered biological retinotopy.
                drive[visual, j] = retina[self.nodes["ids"][visual] % len(retina)] * 1.5
            else:
                semantic = np.asarray([v["attributes"].get(k, 0.5) for k in SEMANTIC_KEYS], np.float32)
                drive[self.nodes["cyborg"], j] = np.tanh(self.semantic_projection @ (semantic * 2-1)) * 0.8
            coords = l.get("coords")
            dist = distance_km(settings["ideal"], coords) if coords else None
            aversion = np.clip((l["price"]-settings["budget"])/settings["budget"], -1, 2)
            meta = np.array([aversion, np.clip(l["size"]/120, 0, 2), l["bedrooms"]/3,
                             float(l.get("parking") == "covered"), float(l.get("furnished", False)),
                             float(l.get("balcony", False)),min((l.get("balcony_size") or 0)/30,2),
                             float(l.get("balcony_covered") is True)], np.float32)
            drive[self.nodes["metadata"], j] = np.tanh(self.meta_projection @ meta) * 0.8
            if coords:
                dy, dx = coords[0]-settings["ideal"][0], coords[1]-settings["ideal"][1]
                angle = math.atan2(dy, dx)
                nav = np.array([math.sin(angle), math.cos(angle), min(dist/12, 2), 1/(1+dist)], np.float32)
                drive[self.nodes["nav"], j] = np.tanh(self.nav_projection @ nav) * 0.8
            signals.append({"distance": round(dist, 1) if dist is not None else None,
                            "price_aversion": round(float(aversion), 3), "trace": {}})
        state = np.zeros_like(drive)
        frames = []
        for _ in range(16):
            state = self._step(state, drive)
            if record:
                frames.append(np.abs(state).mean(axis=1))
        outputs = np.vstack([state[self.nodes["mbon"]], self.cx_pool @ state]).T.astype(np.float64)
        for name, cls in [("vision", "visual"), ("memory", "Kenyon_Cell"), ("navigation", "CX"), ("output", "MBON")]:
            idx = self.nodes["classes"] == cls
            activity = np.abs(state[idx]).mean(axis=0)
            for j in range(batch): signals[j]["trace"][name] = round(float(activity[j]), 6)
        if record: return outputs, signals, np.array(frames,dtype=np.float32)
        return outputs, signals

    @staticmethod
    def fit(x, listings, ratings, comparisons):
        if not len(x): return np.array([]), {}
        ids = {l["id"]: i for i, l in enumerate(listings)}
        center = x.mean(axis=0)
        scale = np.maximum(x.std(axis=0), 0.002)
        normalized = (x-center)/scale
        rows, targets = [], []
        for id, rating in ratings.items():
            if id in ids:
                rows.append(np.r_[normalized[ids[id]], 1])
                targets.append((rating+1)/2)
        for pair in comparisons:
            if pair["a"] in ids and pair["b"] in ids:
                rows.append(np.r_[normalized[ids[pair["a"]]]-normalized[ids[pair["b"]]], 0])
                targets.append((pair["choice"]+1)/2)
        weights = np.zeros(x.shape[1]+1)
        if rows:
            design, y = np.asarray(rows), np.asarray(targets)
            def loss(w):
                logits = design @ w
                regularizer = np.r_[np.ones(len(w)-1), 0.05]
                cost = np.mean(np.logaddexp(0, logits)-y*logits) + 0.08*np.sum(regularizer*w*w)
                grad = design.T @ (expit(logits)-y) / len(y) + 0.16*regularizer*w
                return cost, grad
            result = optimize.minimize(loss, weights, jac=True, method="L-BFGS-B", options={"maxiter":100})
            weights = result.x
        logits = normalized @ weights[:-1] + weights[-1]
        probability = expit(logits)
        class_diversity = len({v for v in ratings.values() if v != 0}) >= 2
        trained = (len(ratings)+len(comparisons) >= 5) and (class_diversity or len(comparisons) >= 5)
        info = {"ratings": len(ratings), "comparisons":len(comparisons), "ready":trained,
                "has_both_classes": class_diversity, "task": "Artificial logistic MBON/CX readout",
                "next": "Rate at least five apartments, including one you like and one you dislike." if not trained else "Your fly is learning your preferences. Add ratings to evaluate its choices on new apartments."}
        return probability, info

    def predict(self, listings, settings, ratings, comparisons):
        x, signals = self.features(listings, settings)
        photos = [l for l in listings if l.get("vision")]
        valid_idx = [i for i, l in enumerate(listings) if l.get("vision")]
        # Missing photos never enter the preference model as a zero-vector example.
        train_ratings = {k:v for k,v in ratings.items() if any(l["id"] == k for l in photos)}
        valid_ids = {l["id"] for l in photos}
        train_pairs = [p for p in comparisons if p["a"] in valid_ids and p["b"] in valid_ids]
        p, info = self.fit(x[valid_idx], photos, train_ratings, train_pairs)
        if not info:
            info = {"ratings":0,"comparisons":0,"ready":False,"has_both_classes":False,"next":"Add apartments with photos."}
        probabilities = dict(zip([l["id"] for l in photos], p))
        predictions = {}
        for i, l in enumerate(listings):
            prob = float(probabilities.get(l["id"], 0.5))
            decision = "waiting"
            if not l.get("vision"): decision = "no_photo"
            elif info["ready"]:
                decision = "approach" if prob > 0.58 else "avoid" if prob < 0.42 else "maybe"
            predictions[l["id"]] = {"decision":decision,"probability":round(prob,5), **signals[i]}
        return predictions, info

    def geometry(self):
        coordinates=self.nodes["positions"].astype(np.float32)*np.array([4,4,40],np.float32)
        valid=np.isfinite(coordinates).all(axis=1)&(coordinates>0).all(axis=1)
        centered=coordinates-np.median(coordinates[valid],axis=0)
        centered/=np.max(np.ptp(coordinates[valid],axis=0))/6
        centered[:,1]*=-1
        centered[~valid]=0
        codes=np.zeros(len(coordinates),np.float32)
        for cls,code in [("visual",1),("Kenyon_Cell",2),("CX",3),("MBON",4),("ALPN",5),("DAN",6)]:
            codes[self.nodes["classes"]==cls]=code
        codes[~valid]=-1
        vertices=np.c_[centered,codes].astype(np.float32)
        coo=self.w.tocoo()
        rng=np.random.default_rng(783)
        random=rng.choice(len(coo.data),min(6500,len(coo.data)),replace=False)
        core=np.flatnonzero(np.isin(self.nodes["classes"][coo.row],["Kenyon_Cell","MBON","CX"]))
        strongest=core[np.argpartition(coo.data[core],-3500)[-3500:]] if len(core)>3500 else core
        selection=np.unique(np.r_[random,strongest])
        selection=selection[valid[coo.row[selection]]&valid[coo.col[selection]]]
        lines=np.c_[coo.col[selection],coo.row[selection]].astype(np.uint32)
        return vertices,lines
