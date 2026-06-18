"""Stage 1 — Trigger.

Pull the precipitation forecast from Open-Meteo and detect the next heavy-rain
event over Sofia. Produces the `forecast` block of scenario.json.
No API key required.

Run from the project root:
    python src/ingest/weather.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# make the project root importable so `from config import ...` works
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import (  # noqa: E402
    SOFIA_LAT,
    SOFIA_LON,
    RAIN_THRESHOLD_MM_H,
    FORECAST_DAYS,
    SEVERITY_BANDS,
    USE_SYNTHETIC_FALLBACK,
    SYNTHETIC_STORM,
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(t: str) -> datetime:
    # Open-Meteo returns e.g. "2026-06-20T08:00"
    return datetime.fromisoformat(t).replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _severity(peak_mm_h: float) -> str:
    if peak_mm_h >= SEVERITY_BANDS["high"]:
        return "high"
    if peak_mm_h >= SEVERITY_BANDS["medium"]:
        return "medium"
    return "low"


def fetch_forecast(lat: float = SOFIA_LAT, lon: float = SOFIA_LON,
                   forecast_days: int = FORECAST_DAYS) -> dict:
    """Raw Open-Meteo response with hourly precipitation."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation",
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_storm_event(hourly: dict, threshold: float = RAIN_THRESHOLD_MM_H) -> dict | None:
    """Find the next future hour at/above `threshold` and the rain window around it.
    Returns {start, lead_time_h, peak_mm_h, total_mm} or None if no storm ahead."""
    times = hourly["time"]
    precip = hourly["precipitation"]
    now = _now()

    start_idx = None
    for i, (t, p) in enumerate(zip(times, precip)):
        if p is None:
            continue
        if _parse_iso(t) >= now and p >= threshold:
            start_idx = i
            break
    if start_idx is None:
        return None

    # extend the window while rain stays at least half the threshold
    end_idx = start_idx
    for j in range(start_idx, len(precip)):
        if precip[j] is not None and precip[j] >= threshold / 2:
            end_idx = j
        else:
            break

    window = [p for p in precip[start_idx:end_idx + 1] if p is not None]
    start_dt = _parse_iso(times[start_idx])
    return {
        "start": _iso(start_dt),
        "lead_time_h": round((start_dt - now).total_seconds() / 3600),
        "peak_mm_h": round(max(window), 1),
        "total_mm": round(sum(window), 1),
    }


def _synthetic_event() -> dict:
    start = _now() + timedelta(hours=SYNTHETIC_STORM["lead_time_h"])
    return {
        "start": _iso(start),
        "lead_time_h": SYNTHETIC_STORM["lead_time_h"],
        "peak_mm_h": SYNTHETIC_STORM["peak_mm_h"],
        "total_mm": SYNTHETIC_STORM["total_mm"],
    }


def build_forecast_block(lat: float = SOFIA_LAT, lon: float = SOFIA_LON) -> dict:
    """Assemble the `forecast` block of scenario.json."""
    synthetic = False
    try:
        raw = fetch_forecast(lat, lon)
        event = find_storm_event(raw["hourly"])
    except requests.RequestException as exc:
        print(f"[weather] network error: {exc}", file=sys.stderr)
        event = None

    if event is None and USE_SYNTHETIC_FALLBACK:
        event = _synthetic_event()
        synthetic = True

    return {
        "source": "open-meteo" if not synthetic else "open-meteo (synthetic fallback)",
        "issued_at": _iso(_now()),
        "event": event,
        "severity": _severity(event["peak_mm_h"]) if event else "none",
        "synthetic": synthetic,
    }


if __name__ == "__main__":
    block = build_forecast_block()
    print(json.dumps(block, indent=2, ensure_ascii=False))

    ev = block["event"]
    if ev:
        tag = " (synthetic demo storm)" if block["synthetic"] else ""
        print(
            f"\nStorm in {ev['lead_time_h']} h  ·  peak {ev['peak_mm_h']} mm/h  ·  "
            f"{ev['total_mm']} mm total  ·  severity {block['severity']}{tag}"
        )
    else:
        print("\nNo heavy-rain event found. Lower RAIN_THRESHOLD_MM_H in config.py "
              "or enable USE_SYNTHETIC_FALLBACK.")
