"""Central configuration for the RiverGuard engine.
Edit values here; every stage imports from this file."""

# --- Area of interest: hero river segment (Perlovska, central Sofia) ---
# bbox = [min_lon, min_lat, max_lon, max_lat]
AOI_BBOX = [23.27, 42.64, 23.44, 42.73]

# Representative point for the city precipitation forecast
SOFIA_LAT = 42.6977
SOFIA_LON = 23.3219

# --- Storm trigger ---
RAIN_THRESHOLD_MM_H = 7.0        # hourly precipitation at/above this = "heavy"
FORECAST_DAYS = 7                # how far ahead to scan
SEVERITY_BANDS = {"high": 15.0, "medium": 7.0}   # by peak mm/h; below medium = "low"

# Demo fallback: if no real storm is in the forecast window, use a synthetic one
# so the rest of the pipeline always has an event to work with.
USE_SYNTHETIC_FALLBACK = True
SYNTHETIC_STORM = {"lead_time_h": 38, "peak_mm_h": 18.0, "total_mm": 42.0}

# --- Cost norms for the ROI engine (clearing a blockage) ---
CLEARING_CREW_COST_BGN_PER_HOUR = 150.0
CLEARING_DEFAULT_HOURS = 3

# --- Exposure ---
FLOOD_RADIUS_M = 200   # assets within this radius of a point are in its flood-impact zone

# --- AI detection (OpenRouter) ---
# Several FREE multimodal (vision) models. detect.py tries them in order and moves
# to the next on a rate-limit (429) or error, so load is spread and one model being
# busy doesn't block a scan. Verify/replace slugs at openrouter.ai/models (Free + image input).
VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-4-maverick:free",
    "qwen/qwen2.5-vl-32b-instruct:free",
]

# --- Auto-discovery of obstruction sites ---
SCAN_SPACING_M = 700      # drop an inspection point every ~700 m along the rivers
SCAN_MAX_POINTS = 6       # cap total AI scans per run (free-tier friendly)
SCAN_DELAY_S = 4          # pause between scans to stay under the free rate limit
MIN_NARROWING_PCT = 35    # keep a site only if the channel is >= this % blocked
SCAN_SEEDS = [            # known hotspots, always inspected
    {"lat": 42.685, "lon": 23.345, "river_name": "Perlovska"},
    {"lat": 42.690, "lon": 23.300, "river_name": "Vladayska"},
]

# --- Currency ---
EUR_TO_BGN = 1.95583