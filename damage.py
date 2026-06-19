"""Damage model — EU JRC depth-damage curves, Bulgaria-adjusted.

Source: Huizinga, J., Moel, H. de, Szewczyk, W. (2017). Global flood depth-damage
functions: Methodology and the database with guidelines. JRC105688, European
Commission Joint Research Centre.

Method per asset:
    damage = exposed value  ×  damage_ratio(local water depth)
where the damage ratio (0–1) is the JRC concave curve for that land-use class,
and the maximum value is the JRC country-scale value. JRC sets country values
from construction-cost surveys; Bulgaria's construction-cost level is roughly
45% of the EU average, so we scale the EU reference values down accordingly
instead of using the EU mean — otherwise Bulgarian damages are overstated.

Two entry points:
  • estimate_damage_detailed(...) — rigorous: each building/road/asset carries
    its OWN depth taken from the terrain flood model (used with flood.py).
  • estimate_damage_eur(exposure, depth) — legacy proxy used only when the
    terrain footprint is unavailable (radius fallback).
"""
from __future__ import annotations

# Depth (m) sample points the JRC curves are defined at.
_DEPTHS = [0, 0.5, 1, 1.5, 2, 3, 4, 5, 6]

# Damage ratio (0-1) vs water depth, per land-use class (JRC, Europe; concave).
JRC_CURVES = {
    "residential":    [0.00, 0.25, 0.40, 0.50, 0.60, 0.75, 0.85, 0.95, 1.00],
    "commercial":     [0.00, 0.15, 0.30, 0.45, 0.55, 0.75, 0.90, 1.00, 1.00],
    "infrastructure": [0.00, 0.20, 0.40, 0.55, 0.65, 0.80, 0.90, 1.00, 1.00],
}

# Bulgaria scaling vs JRC EU reference (construction-cost level ~45% of EU avg).
BG_FACTOR = 0.45

# Maximum (fully-destroyed) damage values, Bulgaria-adjusted.
AVG_BUILDING_FOOTPRINT_M2 = 110          # fallback when a real footprint is unknown
EU_RESIDENTIAL_PER_M2 = 618              # JRC EU reference, €/m²
BUILDING_PER_M2 = round(EU_RESIDENTIAL_PER_M2 * BG_FACTOR)   # ~278 €/m² for Bulgaria
ROAD_PER_M = 90                          # surface + sub-base repair, € per metre

# Point assets: conservative replacement values (Bulgaria), depth-scaled on use.
ASSET_MAX_EUR = {
    "hospital": 600_000,
    "metro_station": 350_000,
    "station": 150_000,
    "school": 120_000,
}

METHOD = "JRC depth-damage curves (Huizinga et al. 2017), Bulgaria-adjusted"


def damage_ratio(depth_m: float, curve: str = "residential") -> float:
    """JRC damage ratio at a given depth, linearly interpolated between points."""
    pts = JRC_CURVES[curve]
    if depth_m <= _DEPTHS[0]:
        return pts[0]
    if depth_m >= _DEPTHS[-1]:
        return pts[-1]
    for i in range(1, len(_DEPTHS)):
        if depth_m <= _DEPTHS[i]:
            d0, d1 = _DEPTHS[i - 1], _DEPTHS[i]
            r0, r1 = pts[i - 1], pts[i]
            return r0 + (r1 - r0) * (depth_m - d0) / (d1 - d0)
    return pts[-1]


# --- per-asset damage (rigorous path) -------------------------------------
def building_damage(depth_m: float, area_m2: float | None = None) -> float:
    # cap the footprint: residential €/m² shouldn't be applied to a whole
    # warehouse/mall; keeps a stray large polygon from dominating the estimate.
    area = min(area_m2 or AVG_BUILDING_FOOTPRINT_M2, 800)
    return area * BUILDING_PER_M2 * damage_ratio(depth_m, "residential")


def road_damage(length_m: float, depth_m: float) -> float:
    return length_m * ROAD_PER_M * damage_ratio(depth_m, "infrastructure")


def asset_damage(asset_type: str, depth_m: float) -> float:
    return ASSET_MAX_EUR.get(asset_type, 120_000) * damage_ratio(depth_m, "commercial")


def estimate_damage_detailed(building_items, road_items, asset_items) -> dict:
    """building_items: list of (area_m2, depth_m); road_items: list of
    (length_m, depth_m); asset_items: list of (type, depth_m). Each item carries
    its own terrain-derived depth. Returns total + a transparent breakdown."""
    b = sum(building_damage(d, a) for (a, d) in building_items)
    r = sum(road_damage(L, d) for (L, d) in road_items)
    s = sum(asset_damage(t, d) for (t, d) in asset_items)
    depths = [d for (_, d) in building_items]
    avg_depth = round(sum(depths) / len(depths), 2) if depths else 0.0
    return {
        "total_eur": round(b + r + s),
        "breakdown": {"buildings_eur": round(b), "roads_eur": round(r),
                      "assets_eur": round(s)},
        "buildings": len(building_items),
        "avg_depth_m": avg_depth,
        "per_building_eur": round(b / len(building_items)) if building_items else 0,
    }


# --- legacy proxy (radius fallback only) ----------------------------------
def flooded_fraction(depth_m: float) -> float:
    """Share of impact-zone assets actually inundated — a proxy for extent used
    ONLY when no terrain footprint is available."""
    return min(0.5, max(0.1, depth_m * 0.3))


def estimate_damage_eur(exposure: dict, depth_m: float) -> int:
    frac = flooded_fraction(depth_m)
    bld_value = AVG_BUILDING_FOOTPRINT_M2 * BUILDING_PER_M2
    dmg = exposure.get("buildings", 0) * frac * bld_value * damage_ratio(depth_m, "residential")
    dmg += exposure.get("road_m", 0) * frac * ROAD_PER_M * damage_ratio(depth_m, "infrastructure")
    for a in exposure.get("critical_assets", []):
        if a.get("type") == "road":
            continue
        dmg += asset_damage(a["type"], depth_m)
    return round(dmg)