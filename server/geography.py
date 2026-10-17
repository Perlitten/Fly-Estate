"""Location checks against a dated OpenStreetMap motorway geometry snapshot.

An advert map pin is source evidence, not a surveyed address. Area-centre pins
never establish which side of a motorway an individual apartment is on.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/"data/geography/highways-limassol.geojson"

@lru_cache(maxsize=1)
def roads():
    return json.loads(PATH.read_text())

def highway_position(listing):
    coords=listing.get("coords")
    if not coords or listing.get("coord_kind") != "source":
        return {"status":"unconfirmed","reason":"No individual advert map pin; an area centre cannot establish motorway position."}
    lat,lon=coords
    xscale=111320*math.cos(math.radians(lat));yscale=111320
    distances=[];crossings=[]
    for feature in roads()["features"]:
        points=feature["geometry"]["coordinates"]
        for a,b in zip(points,points[1:]):
            ax,ay=(a[0]-lon)*xscale,(a[1]-lat)*yscale
            bx,by=(b[0]-lon)*xscale,(b[1]-lat)*yscale
            dx,dy=bx-ax,by-ay
            t=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
            distances.append(math.hypot(ax+t*dx,ay+t*dy))
            if min(a[0],b[0])<=lon<=max(a[0],b[0]) and abs(b[0]-a[0])>1e-9:
                crossings.append(a[1]+(lon-a[0])/(b[0]-a[0])*(b[1]-a[1]))
    if not crossings or not distances:
        return {"status":"unconfirmed","reason":"The advert lies outside the stored road coverage."}
    crossings.sort();boundary=crossings[len(crossings)//2]
    return {"status":"source_pin","north_of_highway":lat>boundary,
            "distance_m":round(min(distances)),"near_highway":min(distances)<300,
            "source":"OpenStreetMap A1/A6 geometry","geometry_date":roads()["queried_at"],
            "caveat":"Based on the advert map pin; confirm the actual address before a viewing."}
