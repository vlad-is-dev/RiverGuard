#!/usr/bin/env python3
"""AI clearing plan — turn a detected obstruction into a concrete crew work order.

Detection tells us *what* is blocking the river. This asks a language model for
the *response*: a short, practical plan a field crew can act on (steps, gear,
access, a time estimate). Runs in the engine (offline at demo time) and bakes the
result into scenario.json, so the console never needs a key live.

Plans are cached by location so re-runs don't spend free-tier quota.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect  # reuse OPENROUTER url, models, key loader, JSON parser  # noqa: E402

CACHE = Path(__file__).resolve().parent / "data" / "cache" / "plans.json"

PROMPT = """You are dispatching a municipal river-maintenance crew in Sofia.
A river channel is partially blocked and heavy rain is forecast. From the facts,
write a short, practical clearing plan the crew can act on TODAY.

Facts:
- River: {river}
- Obstruction: {label} (channel narrowed ~{narrowing}%)
- If it overflows: {buildings} buildings and {road_m} m of road in the flood zone, water up to {depth} m
- Estimated damage prevented: about {damage} EUR

Reply ONLY with JSON, no prose, no code fences:
{{"headline": "<=8 word action summary",
  "steps": ["3 to 5 short imperative steps"],
  "equipment": ["2 to 4 items"],
  "access": "<one short note on reaching the site>",
  "eta_hours": <number>}}"""


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _text_call(prompt: str, api_key: str) -> dict:
    """Text-only OpenRouter call, trying each free model until one answers."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last = None
    for model in detect.VISION_MODELS:
        try:
            body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
            r = requests.post(detect.OPENROUTER, headers=headers, json=body, timeout=90)
            r.raise_for_status()
            data = r.json()
            if "choices" not in data:
                raise RuntimeError(data.get("error", data))
            return detect._parse_json(data["choices"][0]["message"]["content"])
        except Exception as exc:
            last = exc
            continue
    raise last if last else RuntimeError("no model available")


def _clean(plan: dict) -> dict | None:
    """Keep only well-formed fields; return None if unusable."""
    if not isinstance(plan, dict):
        return None
    steps = [str(s).strip() for s in (plan.get("steps") or []) if str(s).strip()][:5]
    equip = [str(s).strip() for s in (plan.get("equipment") or []) if str(s).strip()][:4]
    if not steps:
        return None
    try:
        eta = round(float(plan.get("eta_hours", 3)), 1)
    except Exception:
        eta = 3.0
    return {
        "headline": (str(plan.get("headline", "")).strip() or "Clear the channel")[:80],
        "steps": steps,
        "equipment": equip,
        "access": str(plan.get("access", "")).strip()[:160],
        "eta_hours": eta,
        "by": "ai",
    }


def generate_plan(ctx: dict, api_key: str | None) -> dict | None:
    """ctx: river, label, narrowing, buildings, road_m, depth, damage, lat, lon.
    Returns a plan dict (cached) or None if unavailable."""
    key = f"{ctx.get('lat'):.5f},{ctx.get('lon'):.5f}|{ctx.get('narrowing')}"
    cache = _load_cache()
    if key in cache:
        return cache[key]
    if not api_key:
        return None
    prompt = PROMPT.format(
        river=ctx.get("river", "river"), label=ctx.get("label", "obstruction"),
        narrowing=ctx.get("narrowing", 40), buildings=ctx.get("buildings", 0),
        road_m=ctx.get("road_m", 0), depth=ctx.get("depth", 0.5),
        damage=f"{ctx.get('damage', 0):,}")
    try:
        plan = _clean(_text_call(prompt, api_key))
    except Exception as exc:
        print(f"[ai_plan] {key}: {exc}", file=sys.stderr)
        return None
    if plan:
        cache[key] = plan
        _save_cache(cache)
    return plan