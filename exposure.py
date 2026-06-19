"""Exposure — for each obstruction point, find the real assets that sit in its
flood-impact zone (buildings, roads, metro/hospital/school from OpenStreetMap)
and derive a damage estimate in EUR. Plain requests, no extra installs.

Damage here uses simple per-asset unit costs as an MVP. The next step swaps these
for the official EU JRC depth-damage curves.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import FLOOD_RADIUS_M  # noqa: E402
import osm  # reuse fetch_overpass (with User-Agent + mirrors)  # noqa: E402

# Rough replacement costs in EUR (MVP placeholders; JRC curves come next).
UNIT_DAMAGE_EUR = {
    "building": 5000,      # per building
    "road_m": 200,         # per metre of road
    "metro_station": 50000,
    "hospital": 100000,
    "school": 30000,
    "station": 20000,
}


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _line_length_m(coords) -> float:
    """coords = [[lon, lat], ...]"""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        total += haversine_m(lat1, lon1, lat2, lon2)
    return total


def count_buildings(lat, lon, radius_m) -> int:
    query = f"""[out:json][timeout:60];
way["building"](around:{radius_m},{lat},{lon});
out count;"""
    try:
        data = osm.fetch_overpass(query)
        for el in data.get("elements", []):
            total = el.get("tags", {}).get("total")
            if total is not None:
                return int(total)
    except Exception as exc:
        print(f"[exposure] buildings failed: {exc}", file=sys.stderr)
    return 0


def roads_near(lat, lon, radius_m):
    query = f"""[out:json][timeout:60];
way["highway"~"motorway|trunk|primary|secondary|tertiary|residential"](around:{radius_m},{lat},{lon});
out geom;"""
    try:
        data = osm.fetch_overpass(query)
    except Exception as exc:
        print(f"[exposure] roads failed: {exc}", file=sys.stderr)
        return 0.0, []

    total_m, names = 0.0, []
    for el in data.get("elements", []):
        geom = el.get("geometry")
        if not geom:
            continue
        total_m += _line_length_m([[g["lon"], g["lat"]] for g in geom])
        name = el.get("tags", {}).get("name")
        if name and name not in names:
            names.append(name)
    return total_m, names


def compute_exposure(lat, lon, assets, radius_m=FLOOD_RADIUS_M) -> dict:
    """Real assets within the flood-impact radius of the point."""
    near = []
    for a in assets:
        d = haversine_m(lat, lon, a["lat"], a["lon"])
        if d <= radius_m:
            near.append((d, a))
    near.sort(key=lambda x: x[0])
    critical = [{"type": a["type"], "name": a["name"]} for _, a in near[:3]]

    buildings = count_buildings(lat, lon, radius_m)
    road_m, road_names = roads_near(lat, lon, radius_m)
    if road_names:
        critical.append({"type": "road", "name": road_names[0], "length_m": round(road_m)})

    return {"buildings": buildings, "road_m": round(road_m), "critical_assets": critical}


def estimate_damage_eur(exposure: dict, depth_factor: float = 1.0) -> int:
    """Derive a damage estimate from the exposed assets, scaled by flood depth."""
    dmg = exposure["buildings"] * UNIT_DAMAGE_EUR["building"]
    dmg += exposure["road_m"] * UNIT_DAMAGE_EUR["road_m"]
    for a in exposure["critical_assets"]:
        if a["type"] == "road":
            continue  # already counted via road_m
        dmg += UNIT_DAMAGE_EUR.get(a["type"], 10000)
    return round(dmg * depth_factor)


def has_data(exposure: dict) -> bool:
    return bool(exposure.get("buildings") or exposure.get("road_m")
                or exposure.get("critical_assets"))


# ---------------------------------------------------------------------------
# Footprint-based exposure: keep only the assets that fall inside the REAL
# flood footprint computed from terrain (flood.flood_extent), not a radius.
# ---------------------------------------------------------------------------
def buildings_geom(lat, lon, radius_m):
    """Buildings near the point as (centroid_lat, centroid_lon, area_m2),
    so damage can use each building's real footprint, not a flat average."""
    query = f"""[out:json][timeout:60];
way["building"](around:{radius_m},{lat},{lon});
out geom;"""
    out = []
    try:
        data = osm.fetch_overpass(query)
    except Exception as exc:
        print(f"[exposure] building geom failed: {exc}", file=sys.stderr)
        return out
    for el in data.get("elements", []):
        g = el.get("geometry") or []
        if len(g) < 3:
            continue
        clat = sum(p["lat"] for p in g) / len(g)
        clon = sum(p["lon"] for p in g) / len(g)
        # shoelace area in m² using a local equirectangular projection
        mlon = 111_320.0 * math.cos(math.radians(clat))
        xy = [((p["lon"] - clon) * mlon, (p["lat"] - clat) * 111_320.0) for p in g]
        area = 0.0
        for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
            area += x1 * y2 - x2 * y1
        out.append((clat, clon, abs(area) / 2.0))
    return out


def roads_geom(lat, lon, radius_m):
    """Road ways near the point with geometry: list of (name, [[lon,lat], ...])."""
    query = f"""[out:json][timeout:60];
way["highway"~"motorway|trunk|primary|secondary|tertiary|residential"](around:{radius_m},{lat},{lon});
out geom;"""
    ways = []
    try:
        data = osm.fetch_overpass(query)
        for el in data.get("elements", []):
            geom = el.get("geometry")
            if geom:
                ways.append((el.get("tags", {}).get("name"),
                             [[g["lon"], g["lat"]] for g in geom]))
    except Exception as exc:
        print(f"[exposure] roads geom failed: {exc}", file=sys.stderr)
    return ways


def compute_exposure_flood(lat, lon, assets, ext) -> dict:
    """Exposure from the real flood footprint `ext` (from flood.flood_extent):
    only assets in inundated cells, each tagged with its own terrain depth so the
    damage model can value it at the right severity. Returns UI fields plus the
    per-asset items (_building_items / _road_items / _asset_items) for damage."""
    import flood  # local import avoids any import cycle

    lats, lons = ext["lats"], ext["lons"]
    radius_m = haversine_m(lat, lon, lats[0], lons[0])  # centre -> box corner

    building_items = []   # (area_m2, depth_m)
    for (blat, blon, area) in buildings_geom(lat, lon, radius_m):
        if flood.point_flooded(ext, blat, blon):
            building_items.append((area, flood.local_depth(ext, blat, blon)))

    road_items, road_m, road_names = [], 0.0, []
    for name, coords in roads_geom(lat, lon, radius_m):
        for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
            mlat, mlon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
            if flood.point_flooded(ext, mlat, mlon):
                seg = haversine_m(lat1, lon1, lat2, lon2)
                road_items.append((seg, flood.local_depth(ext, mlat, mlon)))
                road_m += seg
                if name and name not in road_names:
                    road_names.append(name)

    asset_items, critical = [], []
    for a in (assets or []):
        if flood.point_flooded(ext, a["lat"], a["lon"]):
            d = flood.local_depth(ext, a["lat"], a["lon"])
            asset_items.append((a["type"], d))
            if len(critical) < 3:
                critical.append({"type": a["type"], "name": a["name"]})
    if road_names:
        critical.append({"type": "road", "name": road_names[0], "length_m": round(road_m)})

    return {
        "buildings": len(building_items),
        "road_m": round(road_m),
        "critical_assets": critical,
        "_building_items": building_items,
        "_road_items": road_items,
        "_asset_items": asset_items,
    }