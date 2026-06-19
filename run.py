"""Build the first scenario.json from the live forecast plus sample obstruction
points. Run from the project root:

    python run.py

The forecast is real (Stage 1). The points here are PLACEHOLDERS so the frontend
can start and we can see the whole pipeline end-to-end. Later stages (osm, dem,
roi) will replace these sample numbers with computed ones.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from weather import build_forecast_block
from config import AOI_BBOX, CLEARING_CREW_COST_BGN_PER_HOUR, CLEARING_DEFAULT_HOURS, SCAN_SEEDS
import osm
import exposure as exp_mod
import damage as damage_mod
import detect
import discover
import flood

CLEARING_COST_EUR = round(CLEARING_CREW_COST_BGN_PER_HOUR * CLEARING_DEFAULT_HOURS)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "processed" / "scenario.json"
WEB_OUT = ROOT / "web" / "scenario.json"   # copy the frontend reads


def sample_rivers():
    return [{
        "id": "perlovska",
        "name": "Perlovska",
        "geometry": {
            "type": "LineString",
            "coordinates": [[23.31, 42.70], [23.33, 42.69], [23.35, 42.685]],
        },
    }]


def base_points():
    """The obstruction points. Exposure, damage and the work order are COMPUTED
    in build_scenario from real OSM data. `fallback_exposure` is used only if
    OpenStreetMap is unreachable, so the demo still runs offline."""
    return [
        {
            "id": "P1",
            "river_id": "perlovska",
            "river_name": "Perlovska",
            "lat": 42.685, "lon": 23.345,
            "crew": "Crew 4",
            "obstruction": {
                "type": "construction_debris",
                "label": "Construction debris narrowing the channel",
                "channel_narrowing_pct": 60,
                "detected_by": "manual",
                "image_before": "tiles/p1_before.jpg",
                "image_after": "tiles/p1_after.jpg",
            },
            "risk": {"score": 92, "level": "critical", "flood_depth_m": 1.2},
            "fallback_exposure": {
                "buildings": 18, "road_m": 240,
                "critical_assets": [{"type": "metro_station", "name": "Stadion"}],
            },
        },
        {
            "id": "P2",
            "river_id": "vladayska",
            "river_name": "Vladayska",
            "lat": 42.690, "lon": 23.300,
            "crew": "Crew 2",
            "obstruction": {
                "type": "narrowing",
                "label": "Vegetation and silt narrowing the channel",
                "channel_narrowing_pct": 35,
                "detected_by": "manual",
                "image_before": "tiles/p2_before.jpg",
                "image_after": "tiles/p2_after.jpg",
            },
            "risk": {"score": 61, "level": "medium", "flood_depth_m": 0.6},
            "fallback_exposure": {
                "buildings": 7, "road_m": 90,
                "critical_assets": [{"type": "road", "name": "Blvd", "length_m": 90}],
            },
        },
    ]


def _ticket_text(crew, lat, lon, obstruction_label, damage_eur):
    return (f"{crew} -> {lat}, {lon}. Clear {obstruction_label.lower()} before the "
            f"rain. Prevents ~{damage_eur:,} EUR damage.")


def estimate_depth_m(total_mm, narrowing_pct):
    """Flood depth estimate from forecast rainfall and AI-measured channel blockage.
    A transparent proxy until ПУРН/DEM hydraulic modelling is wired in."""
    base = (total_mm or 30) / 50.0                 # 42 mm -> ~0.84 m baseline
    return round(base * (0.5 + (narrowing_pct or 40) / 100.0), 2)


def _level_from_narrowing(pct):
    if pct >= 60:
        return "critical"
    if pct >= 35:
        return "medium"
    return "low"


def point_from_discovery(i, found):
    """Turn an auto-discovered obstruction into a point the pipeline can build."""
    c, o = found["candidate"], found["obstruction"]
    nar = int(o.get("channel_narrowing_pct", 40) or 40)
    return {
        "id": f"P{i + 1}",
        "river_id": (c["river_name"] or "river").lower().replace(" ", "_"),
        "river_name": c["river_name"] or "River",
        "lat": c["lat"], "lon": c["lon"],
        "crew": f"Crew {i + 1}",
        "obstruction": o,
        "risk": {"score": min(99, 40 + round(nar * 0.6)),
                 "level": _level_from_narrowing(nar), "flood_depth_m": 1.0},
        "fallback_exposure": {"buildings": 10, "road_m": 120, "critical_assets": []},
    }


def build_point(p, deadline, real_rivers, assets, storm_mm):
    # snap onto the real riverbed
    if real_rivers:
        snapped = osm.nearest_on_rivers(p["lat"], p["lon"], real_rivers)
        if snapped:
            p["lat"], p["lon"] = round(snapped[0], 6), round(snapped[1], 6)

    obstruction = p["obstruction"]  # already set by discovery (vision) or seed (manual)

    # flood depth from rainfall + AI-measured blockage (needed before the footprint)
    narrowing = int(obstruction.get("channel_narrowing_pct", 40) or 40)
    depth = estimate_depth_m(storm_mm, narrowing)
    p["risk"]["flood_depth_m"] = depth

    # --- real flood footprint from terrain (Open-Meteo / Copernicus elevation) ---
    flood_info, exposure = None, None
    try:
        ext = flood.flood_extent(p["lat"], p["lon"], depth)
    except Exception as exc:
        print(f"[flood] {p['id']}: {exc}", file=sys.stderr)
        ext = None
    if ext and ext["flooded_cells"] >= 3 and assets is not None:
        try:
            exposure = exp_mod.compute_exposure_flood(p["lat"], p["lon"], assets, ext)
            flood_info = {
                "polygon": ext["polygon"],
                "area_ha": round(ext["area_m2"] / 10000.0, 2),
                "depth_m": depth,
                "water_level_m": ext["water_level_m"],
                "cell_m": ext["cell_m"],
                "method": "Bathtub inundation on Copernicus GLO-90 terrain (Open-Meteo)",
            }
            print(f"  {p['id']} flood footprint: {flood_info['area_ha']} ha, "
                  f"depth {depth} m, {exposure['buildings']} buildings")
        except Exception as exc:
            print(f"[flood] {p['id']} exposure failed: {exc}", file=sys.stderr)
            exposure = None

    # fallback: radius-based exposure if the terrain footprint is unavailable
    if exposure is None or not exp_mod.has_data(exposure):
        exposure = exp_mod.compute_exposure(p["lat"], p["lon"], assets) if assets else {}
        if not exp_mod.has_data(exposure):
            exposure = p["fallback_exposure"]

    # damage from JRC depth-damage curves
    breakdown = None
    if exposure.get("_building_items") is not None:
        det = damage_mod.estimate_damage_detailed(
            exposure.pop("_building_items"), exposure.pop("_road_items"),
            exposure.pop("_asset_items"))
        damage = det["total_eur"]
        breakdown = det
    else:
        damage = damage_mod.estimate_damage_eur(exposure, depth)
    clearing = CLEARING_COST_EUR
    ratio = round(damage / clearing) if clearing else 0

    point = {
        "id": p["id"], "river_id": p["river_id"], "river_name": p["river_name"],
        "lat": p["lat"], "lon": p["lon"],
        "obstruction": obstruction,
        "risk": p["risk"],
        "exposure": exposure,
        "roi": {"damage_eur": damage, "clearing_cost_eur": clearing,
                "ratio": ratio, "net_saving_eur": damage - clearing,
                "method": damage_mod.METHOD},
        "dispatch": {
            "crew": p["crew"], "coords": [p["lat"], p["lon"]], "deadline": deadline,
            "reason": f"Prevent estimated {damage:,} EUR of flood damage downstream",
            "ticket_text": _ticket_text(p["crew"], p["lat"], p["lon"],
                                        obstruction["label"], damage),
        },
    }
    if breakdown:
        point["roi"]["breakdown"] = breakdown["breakdown"]
        point["roi"]["per_building_eur"] = breakdown["per_building_eur"]
        point["roi"]["avg_depth_m"] = breakdown["avg_depth_m"]
    if flood_info:
        point["flood"] = flood_info
    return point


def build_scenario():
    forecast = build_forecast_block()
    deadline = forecast["event"]["start"] if forecast["event"] else None
    storm_mm = forecast["event"]["total_mm"] if forecast["event"] else 30

    real_rivers = osm.get_rivers()
    rivers = real_rivers if real_rivers else sample_rivers()
    assets = osm.get_assets()

    api_key = detect.load_api_key()
    print("AI detection:", "ON (vision model)" if api_key else "OFF (no OPENROUTER_API_KEY)")

    # auto-discover obstruction sites by scanning the river network; fall back to
    # the known seed points if discovery is unavailable or finds nothing.
    base = base_points()
    if api_key and real_rivers:
        try:
            found = discover.discover(real_rivers, api_key, SCAN_SEEDS)
            if found:
                base = [point_from_discovery(i, f) for i, f in enumerate(found)]
                print(f"  using {len(base)} auto-discovered site(s)")
            else:
                print("  no sites flagged - using known seed points")
        except Exception as exc:
            print(f"  discovery failed ({exc}) - using known seed points")

    points = [build_point(p, deadline, real_rivers, assets, storm_mm) for p in base]
    points.sort(key=lambda p: p["roi"]["ratio"], reverse=True)

    return {
        "meta": {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "city": "Sofia",
            "scenario_name": "Sofia river network scan",
            "aoi_bbox": AOI_BBOX,
        },
        "forecast": forecast,
        "rivers": rivers,
        "points": points,
        "summary": {
            "points_total": len(points),
            "critical_count": sum(1 for p in points if p["risk"]["level"] == "critical"),
            "damage_at_risk_eur": sum(p["roi"]["damage_eur"] for p in points),
            "clearing_cost_total_eur": sum(p["roi"]["clearing_cost_eur"] for p in points),
        },
    }


if __name__ == "__main__":
    scenario = build_scenario()
    payload = json.dumps(scenario, indent=2, ensure_ascii=False)
    for path in (OUT, WEB_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")

    s = scenario["summary"]
    ev = scenario["forecast"]["event"]
    print(f"Wrote {OUT}")
    print(f"  and  {WEB_OUT}")
    print(f"  storm: in {ev['lead_time_h']} h, severity {scenario['forecast']['severity']}")
    print(f"  points: {s['points_total']} ({s['critical_count']} critical)")
    print(f"  damage at risk: {s['damage_at_risk_eur']:,} EUR  ·  "
          f"clearing: {s['clearing_cost_total_eur']:,} EUR")