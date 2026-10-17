"""Isolated photo-conditioning experiment; never publishes personal memory.

Compare reward paired with photo A, temporally unpaired PAM-only reward,
and the same A/B presentation sequence without reward, over specified seeds.
This measures plasticity and stimulus specificity, not apartment preference.
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np

from server import protocol
from server.storage import Store, ROOT, now
from server.jobs import Queue
from server.checkpoints import CheckpointStore, encode, decode
from server.engine.olfactory import OlfactoryMBEngine, Params
from server.engine.base import Stimulus
from server.engine import stimuli
from server.gallery import PhotoHashes
from server.vision import MODEL_ID, REVISION


def experiment(a_id, b_id, seeds, trials):
    data, queue, hashes = Store().get(), Queue(), PhotoHashes()
    listings = {l["id"]:l for l in data["listings"]}
    a,b = listings[a_id], listings[b_id]
    if not a.get("photos") or not b.get("photos"): raise ValueError("Both apartments need a stored photo.")
    if hashes(a["photos"][0]) == hashes(b["photos"][0]): raise ValueError("Choose two different photographs.")
    base_key = queue.state("memory_base_checkpoint")
    if not base_key: raise ValueError("Start the application worker to prepare the base checkpoint first.")
    saved = CheckpointStore(queue).load(base_key)
    engine = OlfactoryMBEngine(params=Params(**saved.meta["params"]))
    engine.restore(saved)
    original = engine.net.graph.data.copy()
    mode, settings = data["settings"]["mode"], data["settings"]
    center = None
    if mode == "cyborg":
        stored = queue.get_center(MODEL_ID,REVISION)
        if not stored: raise ValueError("Analyze a Cyborg gallery to prepare its fixed centre first.")
        center = stimuli.Center.of(*stored)
    inputs = {}
    for name,listing in (("A",a),("B",b)):
        sha = hashes(listing["photos"][0])
        vector = queue.get_embedding(sha,MODEL_ID,REVISION) if mode == "cyborg" else None
        if mode == "cyborg" and vector is None: raise ValueError("Analyze these Cyborg photographs to store their embeddings first.")
        stimulus,provenance = stimuli.encode(mode,listing["vision"]["per_photo"][0],listing,settings,engine.channels(),vector,center)
        inputs[name] = {"stimulus":stimulus,"photo":listing["photos"][0],"sha256":sha,"provenance":provenance}
    quiet = Stimulus("memory-control-pam-only-v1",())
    rows = []
    started = time.perf_counter()
    for seed in seeds:
        for arm in ("no_reward","paired_A","unpaired_PAM"):
            engine.restore(saved)
            def probe():
                return {name:engine.run_episode(item["stimulus"],seed=seed).to_json(ids=True) for name,item in inputs.items()}
            before = probe()
            episodes = []
            for trial in range(trials):
                for offset,name in enumerate(("A","B","quiet")):
                    stimulus = inputs[name]["stimulus"] if name in inputs else quiet
                    reward = (arm == "paired_A" and name == "A") or (arm == "unpaired_PAM" and name == "quiet")
                    result = engine.run_episode(stimulus,reward=reward,seed=seed+100+3*trial+offset,learning_rate=.1)
                    episodes.append({"trial":trial,"stimulus":name,"reward":reward,**result.to_json(ids=True)})
            after = probe()
            checkpoint = engine.checkpoint()
            engine.restore(decode(encode(checkpoint)))
            restored = probe()
            plastic = set(engine.plastic.tolist())
            changed = np.flatnonzero(engine.net.graph.data != original)
            rows.append({"seed":seed,"arm":arm,"before":before,"after":after,"restored":restored,
                         "episodes":episodes,"changed_connections":len(changed),
                         "changed_outside_declared_connections":sum(int(i) not in plastic for i in changed),
                         "effects":{name:{"before_mbon":sum(before[name]["mbon_spikes"]),
                                           "after_mbon":sum(after[name]["mbon_spikes"]),
                                           "restored_mbon":sum(restored[name]["mbon_spikes"])} for name in inputs}})
            print(f"seed {seed} · {arm} · {len(changed)} changed connections",flush=True)
    return {"protocol":"photo-memory-controls-v1","created":now(),"design":protocol.design(),
            "engine":engine.describe(),"base_checkpoint":base_key,"seeds":seeds,"trials":trials,
            "stimuli":{name:{k:(v.key() if k == "stimulus" else v) for k,v in item.items()} for name,item in inputs.items()},
            "seconds":time.perf_counter()-started,"runs":rows,
            "scope":"Artificial sensory adapter and PAM LTD only. Two photos do not establish recommendation quality or aversive polarity."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a",required=True,help="Stored apartment ID for the first photograph")
    parser.add_argument("--b",required=True,help="Stored apartment ID for an unrelated control photograph")
    parser.add_argument("--seeds",nargs="+",type=int,default=[0,1,2])
    parser.add_argument("--trials",type=int,choices=range(1,21),default=3)
    parser.add_argument("--output",type=Path,default=ROOT/".cache/research/photo-memory-controls.json")
    args = parser.parse_args()
    if args.a == args.b or any(seed < 0 for seed in args.seeds): parser.error("Choose distinct apartments and nonnegative seeds.")
    report = experiment(args.a,args.b,args.seeds,args.trials)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(f"Saved {args.output}")
