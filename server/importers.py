from pathlib import Path
import base64
import hashlib
import io
import json
import re
import socket
import ipaddress
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageOps
from .storage import now, ROOT

ALLOWED_SOURCES = {"www.rentspotcy.com", "rentspotcy.com", "foxrealty.eu", "www.foxrealty.eu",
                   "www.bazaraki.com", "bazaraki.com", "index.cy"}
PHOTO_HOSTS = ALLOWED_SOURCES | {"kzqfyrabaeobdtmemyzl.supabase.co", "cdn.bazaraki.com", "cdn1.bazaraki.com", "cdn2.bazaraki.com"}

class SourceBlocked(ValueError):
    """A source explicitly refused or throttled the request."""
    pass

class SourceRemoved(ValueError):
    """Only an explicit 404/410 establishes that this source URL is gone."""
    pass

def public_url(url, hosts):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError("An HTTPS URL from a supported site is required.")
    for item in socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise ValueError("Local addresses are not allowed.")
    return url

def fetch(url, hosts, limit):
    public_url(url,hosts)
    with httpx.Client(timeout=30,follow_redirects=False,headers={"User-Agent":"FlyEstate-personal-research/0.1"}) as client:
        for _ in range(5):
            with client.stream("GET",url) as r:
                if r.is_redirect:
                    url = public_url(urljoin(url,r.headers["location"]),hosts)
                    continue
                if r.status_code in (403,429):
                    raise SourceBlocked("The site rejected direct import. Use the bookmark button on an open listing or enter it manually.")
                if r.status_code in (404,410):
                    raise SourceRemoved(f"Source returned HTTP {r.status_code}.")
                r.raise_for_status()
                data = bytearray()
                for chunk in r.iter_bytes():
                    data.extend(chunk)
                    if len(data) > limit: raise ValueError("File is too large.")
                return bytes(data)
    raise ValueError("Too many redirects.")

def from_schema(x):
    about = x.get("about") or x.get("itemOffered") or x
    if isinstance(about,list): about = about[0]
    offers = x.get("offers",{})
    if isinstance(offers,list): offers = offers[0]
    address = about.get("address",{})
    if isinstance(address,str): address={"streetAddress":address}
    amenities = {str(a.get("name","")).lower():a.get("value") for a in about.get("amenityFeature",[]) if isinstance(a,dict)}
    title = x.get("name",about.get("name","Apartment"))
    desc = x.get("description",about.get("description",""))
    balcony=amenities.get("balcony")
    if balcony is None: balcony=bool(re.search(r"\b(?:balcony|balconies|veranda|loggia|terrace)\b|балкон|лоджи",desc,re.I)) and not bool(re.search(r"no\s+(?:balcony|terrace)|без\s+балкона",desc,re.I))
    sizes=[float(v) for v in re.findall(r"(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|м²)\s*(?:(?:of\s+)?(?:covered|uncovered)\s+)?(?:veranda|balcony|loggia|terrace|балкон|лоджи)",desc,re.I)]
    balcony_size=max([v for v in sizes if 0<v<500],default=None)
    price = offers.get("price",offers.get("priceSpecification",{}).get("price"))
    size = about.get("floorSize",{}); size = size.get("value") if isinstance(size,dict) else size
    if size is None:
        stated_area=re.search(r"\b(?:total(?:\s+covered)?|internal|covered)\s+area\s*(?::|of|is)?\s*(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm)\b",desc,re.I)
        if stated_area: size=float(stated_area.group(1))
    labelled = re.findall(r"\b(internal|total(?:\s+covered)?)\s+area\s*(?::|of|is)?\s*(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm)\b",desc,re.I)
    kinds = {"internal" if label.lower()=="internal" else "total" for label,value in labelled
             if size is not None and abs(float(value)-float(size)) < .01}
    size_kind = next(iter(kinds)) if len(kinds)==1 else "unknown"
    images = x.get("image",[])
    if isinstance(images,str): images=[images]
    images=[i.get("url") if isinstance(i,dict) else i for i in images]
    geo = about.get("geo",{})
    coords = [float(geo["latitude"]),float(geo["longitude"])] if geo.get("latitude") is not None and geo.get("longitude") is not None else None
    return {"url":x.get("url",x.get("@id","")),"title":title,"price":price,
            "bedrooms":about.get("numberOfBedrooms"),"size":size,
            "size_kind":size_kind,
            "area":address.get("streetAddress", ""),"city":address.get("addressLocality","Limassol"),
            "parking":amenities.get("parking","unknown"),"balcony":balcony is True,"balcony_size":balcony_size,
            "balcony_covered":True if re.search(r"\bcovered\s+(?:veranda|balcony|terrace|loggia)|крыт\w*\s+(?:балкон|лоджи)",desc,re.I) else None,
            "furnished":bool(re.search(r"fully furnished|partially furnished",desc,re.I)),
            "description":desc,"photo_urls":images,"coords":coords,"published_at":x.get("datePosted"),
            "available":not any(v in str(offers.get("availability","")) for v in ["SoldOut","Discontinued"])}

def walk_schema(x):
    if isinstance(x,list):
        for item in x: yield from walk_schema(item)
    elif isinstance(x,dict):
        if x.get("@type") in ("RealEstateListing","Apartment","Product","House","Accommodation") and (x.get("offers") or x.get("price")):
            yield from_schema(x)
        for key in ("@graph","itemListElement"):
            if key in x: yield from walk_schema(x[key])
        if "item" in x: yield from walk_schema(x["item"])

def parse_schema_blocks(html):
    """Raw schema.org listing nodes of a page (an `@type` may be a list, as on Bazaraki)."""
    def nodes(x):
        if isinstance(x,list):
            for item in x: yield from nodes(item)
        elif isinstance(x,dict):
            kinds=x.get("@type"); kinds=kinds if isinstance(kinds,list) else [kinds]
            if {"Apartment","RealEstateListing","House","Accommodation"} & set(kinds): yield x
            if "@graph" in x: yield from nodes(x["@graph"])
    for script in BeautifulSoup(html,"html.parser").select('script[type="application/ld+json"]'):
        try: yield from nodes(json.loads(script.get_text()))
        except (json.JSONDecodeError,TypeError,ValueError): pass

def parse(payload):
    if isinstance(payload,dict):
        if payload.get("@type"): return list(walk_schema(payload))
        if "listings" in payload: return parse(payload["listings"])
        return [payload]
    if isinstance(payload,list):
        return [l for item in payload for l in parse(item)]
    try: return parse(json.loads(payload))
    except (json.JSONDecodeError,TypeError): pass
    soup = BeautifulSoup(payload,"html.parser")
    items = []
    for script in soup.select('script[type="application/ld+json"]'):
        try: items.extend(walk_schema(json.loads(script.get_text())))
        except (json.JSONDecodeError,TypeError,ValueError): pass
    if items: return items
    text = soup.get_text("\n",strip=True)
    def match(pattern):
        found=re.search(pattern,text,re.I)
        return found.group(1) if found else None
    price = match(r"€\s*([\d\s.,]+)")
    bedrooms = match(r"(?:Bedrooms|СПАЛЬНИ)\s*[:\n]?\s*(\d+)") or match(r"(\d+)\s*[- ]?bedroom")
    size = match(r"(?:Property area|Floor area|Internal area|Total(?: covered)? area|Covered area)\s*[:\n]?\s*(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|м²)")
    if not price or not bedrooms or not size:
        raise ValueError("Price, bedrooms and floor area were not found. Use the bookmark button, JSON or the manual form.")
    return [{"title":(soup.find('h1').get_text(strip=True) if soup.find('h1') else text.splitlines()[0])[:160],
             "price":float(re.sub(r"[^\d]","",price)),"bedrooms":int(bedrooms),"size":float(size),
             "area":match(r"(?:Location|Район)\s*[:\n]\s*([^\n]+)") or "", "city":"Limassol",
             "parking":"covered" if re.search(r"covered parking|крытая парковка|Parking\s*[:\n]\s*Covered",text,re.I) else "unknown",
             "description":text,"photo_urls":[i.get('src') for i in soup.select('img[src]') if i.get('src','').startswith('https://')]}]

def normalize(item):
    if item.get("@type"): item=from_schema(item)
    url=str(item.get("url","")).strip()
    if url: public_url(url,ALLOWED_SOURCES)
    title=str(item.get("title","Apartment"))[:180]
    try:
        price=float(item["price"]); bedrooms=int(item["bedrooms"]); size=float(item["size"])
    except (TypeError,KeyError,ValueError): raise ValueError("Numeric price, bedroom count and floor area are required.")
    if not (100 <= price <= 100000 and 0 <= bedrooms <= 20 and 10 <= size <= 5000):
        raise ValueError("Check the price, bedroom count and floor area.")
    area = str(item.get("area") or "").strip()
    area = {"Неаполи":"Neapolis","Туристическая зона":"Germasogeia Tourist Area",
            "Потамос Гермасойи":"Potamos Germasogeias","Агиос Афанасиос":"Agios Athanasios",
            "Трахони":"Trachoni Lemesou","Пиргос":"Pyrgos","Закаки":"Zakaki",
            "Ипсонас":"Ypsonas","Пареклисия":"Pareklisia","Писсури":"Pissouri",
            "Колосси":"Kolossi","Агиос Тихонас":"Agios Tychonas","Agios Tychon":"Agios Tychonas",
            "Polemidia Kato":"Kato Polemidia","Полемидия":"Kato Polemidia",
            "Гермасойя":"Germasogeia","Меса-Гитонья":"Mesa Geitonia",
            "Агиос Николаос":"Agios Nikolaos","Апостолос Андреас":"Apostolos Andreas"}.get(area,area)
    known = json.loads((ROOT / "data/areas.json").read_text(encoding="utf-8")) if (ROOT / "data/areas.json").exists() else {}
    if not area:
        # Only infer an area explicitly named in the source title, never an exact address.
        area = next((a for a in sorted(known,key=len,reverse=True) if a.casefold() in title.casefold()), "Area unspecified")
    coords = item.get("coords")
    coord_kind = item.get("coord_kind", "source") if coords else "area"
    if coord_kind not in ("source", "area"): coord_kind="source" if coords else "area"
    if coords:
        coords=list(map(float,coords))
        if len(coords)!=2 or not all(__import__('math').isfinite(v) for v in coords) or not (34 <= coords[0] <= 36 and 32 <= coords[1] <= 35):
            raise ValueError("Coordinates must be in Cyprus.")
    else: coords=known.get(area,{}).get("coords")
    parking=str(item.get("parking","unknown")).lower()
    parking={"крытая":"covered","крытая парковка":"covered","открытая":"uncovered","no":"none"}.get(parking,parking)
    if parking not in ("covered","uncovered","none","unknown"): parking="unknown"
    id=hashlib.sha256((url or json.dumps([title,price,area])).encode()).hexdigest()[:16]
    photo_urls=list(dict.fromkeys(item.get("photo_urls",[])))
    if len(photo_urls)>100: raise ValueError("More than 100 photos in this listing: split the import. Photos have not been truncated.")
    balcony_size=item.get("balcony_size")
    if balcony_size is not None:
        balcony_size=float(balcony_size)
        if not (0<balcony_size<500): raise ValueError("Check the stated balcony area.")
    return {"id":id,"url":url,"title":title,"price":price,"bedrooms":bedrooms,"size":size,
            "area":area,"city":str(item.get("city") or "Limassol"),"parking":parking,
            "balcony":bool(item.get("balcony",False) or balcony_size),"balcony_size":balcony_size,"balcony_covered":item.get("balcony_covered") if type(item.get("balcony_covered")) is bool else None,"furnished":bool(item.get("furnished",False)),
            "size_kind":item.get("size_kind") if item.get("size_kind") in ("internal","total") else "unknown",
            "field_sources":{k:{"url":url or None,"field":k,"method":"source field" if url else "manual entry"} for k in ("size","balcony","balcony_size","balcony_covered")},
            "coords":coords,"coord_kind":coord_kind if coords else "unknown",
            "published_at":item.get("published_at"),"captured_at":now(),"updated_at":now(),
            "available":item.get("available",True),"source":urlparse(url).hostname or "Manual entry",
            "photo_urls":photo_urls,"photos":[],"vision":None,
            "description":f'{bedrooms} bedrooms · {size:g} m² · {area}. Parking: {parking}. Listing snapshot; confirm availability with the owner.'}

def save_photo(data,name):
    with Image.open(io.BytesIO(data)) as im:
        if im.width*im.height > 50000000: raise ValueError("Image is too large.")
        im=ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((1400,1000))
        output=io.BytesIO()
        im.save(output,"JPEG",quality=88)
        encoded=output.getvalue()
        # The stored bytes identify the image, independent of its source URL.
        dest=ROOT / "data/photos" / (hashlib.sha256(encoded).hexdigest()+".jpg")
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            from .checkpoints import write_atomic
            write_atomic(dest,encoded)
    return "/data/photos/"+dest.name

def photos(listing,uploads=None,previous=None):
    warnings=[]
    outcomes=[]
    old={entry.get("url"):entry for entry in (previous or {}).get("photo_downloads",[]) if entry.get("url")}
    if previous and len(previous.get("photo_urls",[])) == len(previous.get("photos",[])):
        for url,path in zip(previous.get("photo_urls",[]),previous.get("photos",[])):
            old.setdefault(url,{"path":path})
    for url in listing["photo_urls"]:
        name=hashlib.sha256(url.encode()).hexdigest()[:24]
        try:
            dest=ROOT / "data/photos" / (name+".jpg")
            path=save_photo(fetch(url,PHOTO_HOSTS,12*1024*1024),name)
            listing["photos"].append(path)
            outcomes.append({"url":url,"status":"available","path":path,"captured_at":now()})
        except Exception as e:
            prior=old.get(url)
            kept=prior.get("path") if prior else None
            if kept and (ROOT / kept.lstrip("/")).exists():
                listing["photos"].append(kept)
                outcomes.append({"url":url,"status":"cached","path":kept,"error":str(e),"captured_at":now()})
            else:
                outcomes.append({"url":url,"status":"unavailable","error":str(e),"captured_at":now()})
            warnings.append(f"{url}: {e}")
    for encoded in (uploads or []):
        if len(encoded)>16*1024*1024: raise ValueError("Photo exceeds 12 MB.")
        data=base64.b64decode(encoded.split(',')[-1],validate=True)
        listing["photos"].append(save_photo(data,hashlib.sha256(data).hexdigest()[:24]))
    listing["photos"]=list(dict.fromkeys(listing["photos"]))
    listing["photo_downloads"]=outcomes
    return warnings
