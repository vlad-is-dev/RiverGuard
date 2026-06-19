"""AI detection — compare a MAP of where the river should be against a current
SATELLITE photo of the same spot, and let a vision model judge whether the
channel is obstructed.

Two image sources, both free and key-less:
  - map:       Esri World Topo Map  (shows the river channel)
  - satellite: Esri World Imagery   (current aerial view)

Needs a free OpenRouter key in a .env file at the project root:
    OPENROUTER_API_KEY=sk-or-...

For the demo you can also drop a real photo of a blockage at
web/tiles/<point_id>_input.jpg and it will analyse that single image instead.
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from config import VISION_MODELS
except Exception:
    VISION_MODELS = ["openrouter/free"]

ROOT = Path(__file__).resolve().parent
TILES = ROOT / "web" / "tiles"
ESRI_IMAGERY = ("https://services.arcgisonline.com/arcgis/rest/services/"
                "World_Imagery/MapServer/export")
ESRI_TOPO = ("https://services.arcgisonline.com/arcgis/rest/services/"
             "World_Topo_Map/MapServer/export")
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

# Compare two images: map (reference) vs satellite (current).
COMPARE_PROMPT = (
    "You are inspecting an urban river channel in Sofia. "
    "The FIRST image is a topographic MAP showing where the river channel should run. "
    "The SECOND image is a CURRENT SATELLITE photo of the exact same location. "
    "Compare them: is the river channel in the satellite obstructed, narrowed or "
    "encroached by construction debris, illegal dumping, dense vegetation or silt, "
    "compared with where the map shows the channel should be? "
    "Reply with ONLY a JSON object and nothing else:\n"
    '{"obstructed": true, "type": "construction_debris|dumping|vegetation|narrowing|clear", '
    '"channel_narrowing_pct": 0, "label": "short human description", "confidence": 0.0}'
)

# Analyse a single provided image (e.g. a real photo of a blockage).
SINGLE_PROMPT = (
    "You are inspecting an aerial/satellite image of an urban river channel in Sofia. "
    "Decide whether the watercourse is obstructed by construction debris, illegal "
    "dumping, dense vegetation, silt or narrowing. "
    "Reply with ONLY a JSON object and nothing else:\n"
    '{"obstructed": true, "type": "construction_debris|dumping|vegetation|narrowing|clear", '
    '"channel_narrowing_pct": 0, "label": "short human description", "confidence": 0.0}'
)


def load_api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _bbox_around(lat, lon, size_m=180):
    dlat = size_m / 111320.0
    dlon = size_m / (111320.0 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat  # W, S, E, N


def _fetch_tile(service_url, lat, lon, out_path, size_px=640, size_m=180):
    w, s, e, n = _bbox_around(lat, lon, size_m)
    params = {"bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 4326,
              "size": f"{size_px},{size_px}", "format": "jpg", "f": "image"}
    resp = requests.get(service_url, params=params, timeout=60)
    resp.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    return out_path


def fetch_satellite(lat, lon, out_path, **kw):
    return _fetch_tile(ESRI_IMAGERY, lat, lon, out_path, **kw)


def fetch_map(lat, lon, out_path, **kw):
    return _fetch_tile(ESRI_TOPO, lat, lon, out_path, **kw)


def _b64(path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def _parse_json(text: str) -> dict:
    t = text.strip()
    if "```" in t:
        t = t.split("```")[1]
        if t.lower().startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        return json.loads(t[start:end + 1])
    raise ValueError(f"no JSON in model reply: {text[:200]}")


def analyze(image_paths, prompt, api_key, models=None) -> dict:
    """Send the text prompt first, then the image(s). Try each free vision model in
    turn; if one is rate-limited (429) or errors, move to the next so load spreads."""
    models = models or VISION_MODELS
    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{_b64(p)}"}})
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_error = None
    for model in models:
        try:
            body = {"model": model, "messages": [{"role": "user", "content": content}]}
            resp = requests.post(OPENROUTER, headers=headers, json=body, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            if "choices" not in data:
                raise RuntimeError(f"OpenRouter: {data.get('error', data)}")
            return _parse_json(data["choices"][0]["message"]["content"])
        except Exception as exc:
            last_error = exc
            continue  # try the next free model
    raise last_error if last_error else RuntimeError("no vision model available")


def detect_obstruction(point_id, lat, lon, api_key, provided_image=None) -> dict | None:
    """Map-vs-satellite comparison (or a single provided image). Returns an
    obstruction dict, or None on failure. Retries the model call a few times."""
    try:
        if provided_image:
            shown = Path(provided_image)
            imgs, prompt = [shown], SINGLE_PROMPT
        else:
            map_img = fetch_map(lat, lon, TILES / f"{point_id}_map.jpg")
            sat_img = fetch_satellite(lat, lon, TILES / f"{point_id}.jpg")
            shown = sat_img  # the satellite is what we show in the panel
            imgs, prompt = [map_img, sat_img], COMPARE_PROMPT
    except Exception as exc:
        print(f"[detect] {point_id} image fetch failed: {exc}", file=sys.stderr)
        return None

    try:
        result = analyze(imgs, prompt, api_key)
    except Exception as exc:
        print(f"[detect] {point_id}: {exc}", file=sys.stderr)
        return None

    return {
        "type": result.get("type", "clear"),
        "label": result.get("label", "No obstruction detected"),
        "channel_narrowing_pct": int(result.get("channel_narrowing_pct", 0) or 0),
        "detected_by": "vision (map vs satellite)" if not provided_image else "vision",
        "confidence": round(float(result.get("confidence", 0) or 0), 2),
        "image_after": f"tiles/{Path(shown).name}",
    }


if __name__ == "__main__":
    key = load_api_key()
    if not key:
        print("No OPENROUTER_API_KEY found. Create .env with OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)
    print("Comparing map vs satellite on a test point (Perlovska)...")
    out = detect_obstruction("test", 42.685, 23.345, key)
    print(json.dumps(out, indent=2, ensure_ascii=False))