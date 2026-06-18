"""Ingest — real rivers and city assets from OpenStreetMap via the Overpass API.
Plain requests, no extra installs. Run from the project root:

    python osm.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))  # project root on path
from config import AOI_BBOX  # noqa: E402

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
HEADERS = {
    "User-Agent": "RiverGuard/1.0 (Sofia hackathon project)",
    "Accept": "*/*",
}


def _bbox_str(bbox) -> str:
    """Our bbox is [min_lon, min_lat, max_lon, max_lat]; Overpass wants S,W,N,E."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return f"{min_lat},{min_lon},{max_lat},{max_lon}"


def fetch_overpass(query: str, timeout: int = 90) -> dict:
    """Try each Overpass mirror until one answers. A proper User-Agent avoids 406."""
    last_error = None
    for url in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(url, data={"data": query}, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # network, HTTP, or bad JSON -> try next mirror
            last_error = exc
            continue
    raise last_error if last_error else RuntimeError("all Overpass mirrors failed")


def get_rivers(bbox=AOI_BBOX) -> list:
    """All waterways in the bbox, with inline geometry. Coordinates are [lon, lat]."""
    b = _bbox_str(bbox)
    query = f"""[out:json][timeout:90];
(
  way["waterway"~"river|stream|canal"]({b});
);
out geom;"""
    try:
        data = fetch_overpass(query)
    except Exception as exc:
        print(f"[osm] rivers fetch failed: {exc}", file=sys.stderr)
        return []

    rivers = []
    for el in data.get("elements", []):
        geom = el.get("geometry")
        if not geom:
            continue
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en") or "unnamed"
        rivers.append({
            "id": str(el["id"]),
            "name": name,
            "geometry": {"type": "LineString",
                         "coordinates": [[g["lon"], g["lat"]] for g in geom]},
        })
    return rivers


def get_assets(bbox=AOI_BBOX) -> list:
    """Metro stations, hospitals and schools in the bbox. Returns points."""
    b = _bbox_str(bbox)
    query = f"""[out:json][timeout:90];
(
  node["station"="subway"]({b});
  node["railway"="station"]({b});
  node["amenity"="hospital"]({b});
  way["amenity"="hospital"]({b});
  node["amenity"="school"]({b});
  way["amenity"="school"]({b});
);
out center;"""
    try:
        data = fetch_overpass(query)
    except Exception as exc:
        print(f"[osm] assets fetch failed: {exc}", file=sys.stderr)
        return []

    assets = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue

        if tags.get("station") == "subway" or tags.get("subway") == "yes":
            atype = "metro_station"
        elif tags.get("railway") == "station":
            atype = "station"
        elif tags.get("amenity") == "hospital":
            atype = "hospital"
        elif tags.get("amenity") == "school":
            atype = "school"
        else:
            continue

        assets.append({"type": atype, "name": tags.get("name") or atype,
                       "lat": lat, "lon": lon})
    return assets


def pick_river(rivers, name_hint=("перлов", "perlov")):
    """Pick the Perlovska if present, else the longest waterway."""
    if not rivers:
        return None
    named = [r for r in rivers if any(h in r["name"].lower() for h in name_hint)]
    pool = named or rivers
    return max(pool, key=lambda r: len(r["geometry"]["coordinates"]))


def nearest_on_rivers(lat, lon, rivers):
    """Nearest vertex across all river geometries -> [lat, lon] (or None)."""
    best, best_d = None, float("inf")
    for r in rivers:
        for c in r["geometry"]["coordinates"]:   # c = [lon, lat]
            d = (c[1] - lat) ** 2 + (c[0] - lon) ** 2
            if d < best_d:
                best_d, best = d, [c[1], c[0]]
    return best


def save_raw(rivers, assets):
    out = Path(__file__).resolve().parent / "data" / "raw" / "osm"
    out.mkdir(parents=True, exist_ok=True)
    (out / "rivers.json").write_text(json.dumps(rivers, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "assets.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    rivers = get_rivers()
    assets = get_assets()
    out = save_raw(rivers, assets)

    print(f"rivers: {len(rivers)}  ·  assets: {len(assets)}")
    main = pick_river(rivers)
    if main:
        print(f"main river: {main['name']} ({len(main['geometry']['coordinates'])} points)")
    by_type = {}
    for a in assets:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
    print("assets by type:", by_type or "(none found - widen AOI_BBOX in config.py)")
    print(f"saved to {out}")