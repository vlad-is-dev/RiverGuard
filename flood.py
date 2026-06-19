#!/usr/bin/env python3
"""Real flood footprint from terrain (bathtub inundation model).

When a river is blocked, water backs up and spreads over the low ground around it.
This module reproduces that with real elevation data instead of a fixed radius:

  1. Pull an elevation grid around the obstruction from the Open-Meteo Elevation
     API (free, no key; Copernicus GLO-90 terrain, ~90 m).
  2. Set a water level = riverbed elevation + flood depth (depth comes from the
     rainfall + AI-measured blockage).
  3. Flood-fill outward from the river cell to every *connected* cell whose ground
     is below that water level. The wetted area is the flood footprint.

This is a planar / "bathtub" inundation model with connectivity — the standard
first-order method for rapid flood mapping. It is driven by real terrain, so it
shows which low-lying streets and blocks actually take on water, not a circle.
It is not a full hydrodynamic (shallow-water) solver; we state that openly.
"""
import math
import sys
from collections import deque

import requests

ELEV_URL = "https://api.open-meteo.com/v1/elevation"
M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(lat: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat))


def build_grid(lat: float, lon: float, half_m: float = 600.0, n: int = 25):
    """An n x n grid of (lat, lon) spanning +/- half_m around the center.
    n is forced odd so the centre cell is the obstruction itself."""
    if n % 2 == 0:
        n += 1
    dlat = half_m / M_PER_DEG_LAT
    dlon = half_m / _m_per_deg_lon(lat)
    lats = [lat - dlat + 2 * dlat * i / (n - 1) for i in range(n)]
    lons = [lon - dlon + 2 * dlon * j / (n - 1) for j in range(n)]
    cell_m = (2 * half_m) / (n - 1)
    return lats, lons, cell_m


def fetch_elevations(latlons):
    """latlons: list of (lat, lon). Returns list of elevations in metres.
    Open-Meteo accepts up to 100 coordinate pairs per request, so we batch."""
    out = []
    for k in range(0, len(latlons), 100):
        chunk = latlons[k:k + 100]
        params = {
            "latitude": ",".join(f"{a:.5f}" for a, _ in chunk),
            "longitude": ",".join(f"{b:.5f}" for _, b in chunk),
        }
        r = requests.get(ELEV_URL, params=params, timeout=60)
        r.raise_for_status()
        out.extend(r.json()["elevation"])
    return out


def flood_extent(lat: float, lon: float, depth_m: float,
                 half_m: float = 600.0, n: int = 25):
    """Flood footprint around (lat, lon) for the given depth.

    Returns a dict (or None on network failure):
      polygon        outline [[lat,lon], ...] to draw on the map
      area_m2        flooded ground area
      flooded_cells  number of wet grid cells
      water_level_m  riverbed elevation + depth
      base_elev_m    riverbed (centre) elevation
      cell_m         grid resolution in metres
      lats/lons/flooded   grid + boolean mask (for building intersection)
    """
    lats, lons, cell_m = build_grid(lat, lon, half_m, n)
    n = len(lats)
    coords = [(la, lo) for la in lats for lo in lons]   # row-major: idx = i*n + j
    try:
        flat = fetch_elevations(coords)
    except Exception as exc:
        print(f"[flood] elevation fetch failed: {exc}", file=sys.stderr)
        return None
    if len(flat) != n * n:
        print("[flood] unexpected elevation count", file=sys.stderr)
        return None

    E = [flat[i * n:(i + 1) * n] for i in range(n)]
    ci = cj = n // 2
    base = E[ci][cj]
    water = base + depth_m

    flooded = [[False] * n for _ in range(n)]
    if base <= water:
        dq = deque([(ci, cj)])
        flooded[ci][cj] = True
        while dq:
            i, j = dq.popleft()
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    ni, nj = i + di, j + dj
                    if (0 <= ni < n and 0 <= nj < n
                            and not flooded[ni][nj] and E[ni][nj] <= water):
                        flooded[ni][nj] = True
                        dq.append((ni, nj))

    pts = [(lats[i], lons[j]) for i in range(n) for j in range(n) if flooded[i][j]]
    polygon = _convex_hull(pts) if len(pts) >= 3 else [[a, b] for a, b in pts]
    return {
        "polygon": polygon,
        "area_m2": round(len(pts) * cell_m * cell_m),
        "flooded_cells": len(pts),
        "water_level_m": round(water, 1),
        "base_elev_m": round(base, 1),
        "cell_m": round(cell_m, 1),
        "lats": lats, "lons": lons, "flooded": flooded,
    }


def point_flooded(extent, lat: float, lon: float) -> bool:
    """Does (lat, lon) fall inside a flooded cell?"""
    lats, lons, flooded = extent["lats"], extent["lons"], extent["flooded"]
    i = min(range(len(lats)), key=lambda k: abs(lats[k] - lat))
    j = min(range(len(lons)), key=lambda k: abs(lons[k] - lon))
    return flooded[i][j]


def buildings_in_extent(extent, building_latlons) -> int:
    """Count building points that fall within the flood footprint."""
    return sum(1 for (la, lo) in building_latlons if point_flooded(extent, la, lo))


def _convex_hull(points):
    """Andrew's monotone chain hull. points: list of (lat, lon)."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return [[a, b] for a, b in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return [[a, b] for a, b in hull]


if __name__ == "__main__":
    # Real Sofia test point (Perlovska corridor). Depth ~1.2 m of backed-up water.
    lat, lon, depth = 42.685, 23.345, 1.2
    print(f"Flood footprint @ {lat},{lon}  depth {depth} m  (Open-Meteo / Copernicus)")
    ext = flood_extent(lat, lon, depth, half_m=600, n=25)
    if not ext:
        print("  no result (check network)")
        sys.exit(1)
    print(f"  riverbed elevation : {ext['base_elev_m']} m")
    print(f"  water level        : {ext['water_level_m']} m")
    print(f"  grid resolution    : {ext['cell_m']} m/cell")
    print(f"  flooded cells      : {ext['flooded_cells']}")
    print(f"  flooded area       : {ext['area_m2']:,} m²  (~{ext['area_m2'] / 10000:.2f} ha)")
    print(f"  footprint vertices : {len(ext['polygon'])}")