"""Auto-discovery of obstruction sites.

Walk the real river network, drop inspection points every SCAN_SPACING_M, run the
AI map-vs-satellite check on each, and keep the ones the model flags as blocked.
Results are cached on disk (data/cache/detections.json) keyed by coordinates, so
re-runs are instant and don't re-call the model. Delete that file to force a fresh scan.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import SCAN_SPACING_M, SCAN_MAX_POINTS, MIN_NARROWING_PCT, SCAN_DELAY_S  # noqa: E402
import detect  # noqa: E402
import osm  # noqa: E402
from exposure import haversine_m  # noqa: E402

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "cache" / "detections.json"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_along_rivers(rivers, spacing_m, max_points, seeds):
    """Inspection points: the seeds (snapped to a river) plus points dropped every
    spacing_m while walking each river geometry."""
    pts = []
    for s in seeds:
        snap = osm.nearest_on_rivers(s["lat"], s["lon"], rivers) or [s["lat"], s["lon"]]
        pts.append({"lat": round(snap[0], 6), "lon": round(snap[1], 6),
                    "river_name": s.get("river_name", "River")})

    for r in rivers:
        coords = r.get("geometry", {}).get("coordinates", [])
        acc, last = 0.0, None
        for c in coords:
            lat, lon = c[1], c[0]
            if last is not None:
                acc += haversine_m(last[0], last[1], lat, lon)
            last = (lat, lon)
            if acc >= spacing_m:
                acc = 0.0
                pts.append({"lat": round(lat, 6), "lon": round(lon, 6),
                            "river_name": r.get("name", "River")})
            if len(pts) >= max_points:
                return pts
    return pts[:max_points]


def discover(rivers, api_key, seeds):
    """Scan candidate points, return the ones flagged as obstructed."""
    cache = _load_cache()
    candidates = sample_along_rivers(rivers, SCAN_SPACING_M, SCAN_MAX_POINTS, seeds)
    print(f"  scanning {len(candidates)} inspection points (cached: {len(cache)})...")

    found = []
    for i, c in enumerate(candidates):
        key = f"{c['lat']:.5f},{c['lon']:.5f}"
        if key in cache:
            res = cache[key]
        else:
            res = detect.detect_obstruction(f"S{i}", c["lat"], c["lon"], api_key)
            if res is None:               # rate-limited / failed: don't cache, retry next run
                print(f"  S{i}: no result (will retry next run)")
                continue
            cache[key] = res
            _save_cache(cache)            # persist after each success
            time.sleep(SCAN_DELAY_S)      # stay under the free rate limit

        if (res.get("type") not in (None, "clear")
                and int(res.get("channel_narrowing_pct", 0) or 0) >= MIN_NARROWING_PCT):
            found.append({"candidate": c, "obstruction": res})

    print(f"  obstructions found: {len(found)}")
    return found