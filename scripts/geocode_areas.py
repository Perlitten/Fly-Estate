from pathlib import Path
import json,time,urllib.request,urllib.parse

ROOT=Path(__file__).resolve().parents[1]
names=["Agios Athanasios","Germasogeia Tourist Area","Germasogeia","Agia Fyla","Trachoni Lemesou","Pyrgos","Panthea","Zakaki","Neapolis","Potamos Germasogeias","Mesa Geitonia","Ypsonas","Agios Tychonas","Agios Tychon","Polemidia Kato","Kato Polemidia","Pareklisia","Pissouri","Kolossi","Kapsalos","Agia Triada","Agios Nikolaos","Apostolos Andreas","Agios Spyridon","Agios Ioannis","Agia Paraskevi","Ekali"]
path=ROOT/"data/areas.json"
areas=json.loads(path.read_text()) if path.exists() else {}
for name in names:
    if name in areas: continue
    query={"Agios Nikolaos":"Άγιος Νικόλαος, Λεμεσός, Cyprus","Ekali":"Εκάλη, Λεμεσός, Cyprus","Polemidia Kato":"Kato Polemidia, Limassol, Cyprus"}.get(name,name+", Limassol, Cyprus")
    url="https://nominatim.openstreetmap.org/search?"+urllib.parse.urlencode({"q":query,"format":"jsonv2","limit":5,"countrycodes":"cy"})
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"FlyEstate-personal-local-research/0.1"}),timeout=20))
        # Reject shops, bus stops and similarly named POIs outside the requested area.
        result=next((x for x in r if x.get("category") in ("place","boundary") and x.get("addresstype") in ("quarter","suburb","neighbourhood","village","town","city","municipality")),None)
        if result:
            areas[name]={"coords":[float(result["lat"]),float(result["lon"])],"name":result.get("display_name"),"source":"OpenStreetMap/Nominatim","source_url":url,"precision":"area","license":"ODbL"}
            print(name,areas[name]["coords"],flush=True)
        else: print("No result:",name,flush=True)
    except Exception as e: print(name,str(e),flush=True)
    path.write_text(json.dumps(areas,indent=2,ensure_ascii=False))
    time.sleep(1.1)
if "Germasogeia Tourist Area" not in areas and "Potamos Germasogeias" in areas:
    areas["Germasogeia Tourist Area"]={**areas["Potamos Germasogeias"],"note":"Approximation using the coastal Potamos Germasogeias district."}
path.write_text(json.dumps(areas,indent=2,ensure_ascii=False))
