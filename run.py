"""Build the first scenario.json from the live forecast plus sample obstruction
points. Run from the project root:

    python run.py

The forecast is real (Stage 1). The points here are PLACEHOLDERS so the frontend
can start and we can see the whole pipeline end-to-end. Later stages (osm, dem,
roi) will replace these sample numbers with computed ones.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from weather import build_forecast_block
from config import AOI_BBOX, CLEARING_CREW_COST_BGN_PER_HOUR, CLEARING_DEFAULT_HOURS
import osm
import exposure as exp_mod
import damage as damage_mod
import detect

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


def build_point(p, deadline, real_rivers, assets, api_key=None):
    # snap onto the real riverbed
    if real_rivers:
        snapped = osm.nearest_on_rivers(p["lat"], p["lon"], real_rivers)
        if snapped:
            p["lat"], p["lon"] = round(snapped[0], 6), round(snapped[1], 6)

    # AI detection: a vision model inspects the river image and reports the blockage.
    # Uses a real photo at web/tiles/<id>_input.jpg if present, else a satellite tile.
    obstruction = p["obstruction"]
    if api_key:
        provided = detect.TILES / f"{p['id']}_input.jpg"
        result = detect.detect_obstruction(
            p["id"], p["lat"], p["lon"], api_key,
            provided_image=provided if provided.exists() else None)
        if result and result.get("type") not in (None, "clear"):
            obstruction = result

    # real exposure from OSM, with offline fallback
    exposure = exp_mod.compute_exposure(p["lat"], p["lon"], assets) if assets else {}
    if not exp_mod.has_data(exposure):
        exposure = p["fallback_exposure"]

    # damage from JRC depth-damage curves at the point's flood depth
    depth = p["risk"].get("flood_depth_m", 1.0)
    damage = damage_mod.estimate_damage_eur(exposure, depth)
    clearing = CLEARING_COST_EUR
    ratio = round(damage / clearing) if clearing else 0

    return {
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


def build_scenario():
    forecast = build_forecast_block()
    deadline = forecast["event"]["start"] if forecast["event"] else None

    real_rivers = osm.get_rivers()
    rivers = real_rivers if real_rivers else sample_rivers()
    assets = osm.get_assets()

    api_key = detect.load_api_key()
    print("AI detection:", "ON (vision model)" if api_key else "OFF (no OPENROUTER_API_KEY)")

    points = [build_point(p, deadline, real_rivers, assets, api_key) for p in base_points()]
    points.sort(key=lambda p: p["roi"]["ratio"], reverse=True)

    return {
        "meta": {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "city": "Sofia",
            "scenario_name": "Perlovska center - storm scenario",
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