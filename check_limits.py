#!/usr/bin/env python3
"""Quick OpenRouter key status check.

Run:  python check_limits.py

Shows whether your key is on the free tier (50 requests/day) or has credits
(1000/day), your per-minute rate limit, and spend so far. The exact count of
free requests used *today* is best seen at https://openrouter.ai/activity
(each row is one request; failed 429s count too).
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect import load_api_key  # reuse the .env / env reader  # noqa: E402

AUTH_URL = "https://openrouter.ai/api/v1/auth/key"


def main() -> None:
    key = load_api_key()
    if not key:
        print("No OPENROUTER_API_KEY found (checked .env and environment).")
        return

    try:
        resp = requests.get(AUTH_URL, headers={"Authorization": f"Bearer {key}"}, timeout=30)
        resp.raise_for_status()
        d = resp.json().get("data", {})
    except Exception as exc:
        print(f"Could not reach OpenRouter: {exc}")
        return

    is_free = d.get("is_free_tier", True)
    daily_cap = 50 if is_free else 1000
    rl = d.get("rate_limit") or {}
    per_min = f"{rl.get('requests', '?')} requests / {rl.get('interval', '?')}"

    print("OpenRouter key status")
    print("-" * 34)
    print(f"  tier            : {'FREE' if is_free else 'has credits'}")
    print(f"  daily limit     : ~{daily_cap} free requests/day  (failed calls count too)")
    print(f"  per-minute limit: {per_min}")
    print(f"  spend so far    : ${d.get('usage', 0)}")
    if d.get("limit") is not None:
        print(f"  credit limit    : ${d.get('limit')}")
    print("-" * 34)
    print("  Exact requests used today -> https://openrouter.ai/activity")
    if is_free:
        print("  Tip: a one-time $10 top-up raises the daily limit to 1000 (and isn't")
        print("       spent on :free models — it just lifts the cap).")


if __name__ == "__main__":
    main()