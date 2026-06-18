"""Damage model — EU JRC depth-damage curves.

Source: Huizinga, J., Moel, H. de, Szewczyk, W. (2017). Global flood depth-damage
functions: Methodology and the database with guidelines. JRC105688, European
Commission Joint Research Centre.

Damage = Σ ( flooded assets × maximum damage value × damage ratio at flood depth ).
The damage ratio comes from the JRC curve for each land-use class; the maximum
values are JRC's European reference values.
"""

from __future__ import annotations

# Depth (m) sample points the JRC curves are defined at.
_DEPTHS = [0, 0.5, 1, 1.5, 2, 3, 4, 5, 6]

# Damage ratio (0-1) vs water depth, per land-use class (JRC, Europe).
JRC_CURVES = {
    "residential":    [0.00, 0.25, 0.40, 0.50, 0.60, 0.75, 0.85, 0.95, 1.00],
    "commercial":     [0.00, 0.15, 0.30, 0.45, 0.55, 0.75, 0.90, 1.00, 1.00],
    "infrastructure": [0.00, 0.20, 0.40, 0.55, 0.65, 0.80, 0.90, 1.00, 1.00],
}

# JRC European maximum damage values.
AVG_BUILDING_FOOTPRINT_M2 = 120
JRC_MAX_EUR = {
    "building_per_m2": 618,     # EU residential construction, €/m²
    "road_per_m": 150,          # infrastructure, € per metre of road
    "metro_station": 1_000_000,
    "hospital": 2_000_000,
    "school": 500_000,
    "station": 300_000,
}


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


def flooded_fraction(depth_m: float) -> float:
    """Share of impact-zone assets actually inundated. A proxy for flood extent
    (grows with depth, capped) until a DEM-derived extent replaces it."""
    return min(0.5, max(0.1, depth_m * 0.3))


def estimate_damage_eur(exposure: dict, depth_m: float) -> int:
    frac = flooded_fraction(depth_m)
    bld_value = AVG_BUILDING_FOOTPRINT_M2 * JRC_MAX_EUR["building_per_m2"]

    dmg = exposure.get("buildings", 0) * frac * bld_value * damage_ratio(depth_m, "residential")
    dmg += exposure.get("road_m", 0) * frac * JRC_MAX_EUR["road_per_m"] * damage_ratio(depth_m, "infrastructure")
    for a in exposure.get("critical_assets", []):
        if a.get("type") == "road":
            continue  # roads already counted via road_m
        dmg += JRC_MAX_EUR.get(a["type"], 200_000) * damage_ratio(depth_m, "commercial")
    return round(dmg)


METHOD = "JRC depth-damage curves (Huizinga et al. 2017)"