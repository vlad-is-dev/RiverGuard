# RiverGuard

**Turn the weather forecast into a work order — clear the right river blockage before it floods Sofia.**

RiverGuard is an early-warning system that, when heavy rain is forecast, finds the garbage and obstructions clogging Sofia's rivers from satellite imagery, calculates which one will cause the costliest flooding downstream, and tells crews exactly what to clear first — turning a few hundred leva of prevention into hundreds of thousands of leva of avoided damage.

Built for **Hack Smart Sofia** (challenge: *Sponge City & Urban Rivers*).

---

## The problem

Sofia floods roughly every 20 years, and each cycle is worse because the city keeps paving over land that used to absorb rainwater, while its rivers are increasingly clogged with dumped waste and narrowed by encroachment. More than half of riverbeds run through private property and most have incorrect cadastre mappings. When a storm hits, obstructions turn ordinary rain into a flood — and nobody has a prioritized, money-based list of *what to clear first*.

## What RiverGuard does

1. **Trigger** — watches the precipitation forecast; a coming storm starts the clock.
2. **Detect** — compares fresh satellite/aerial imagery of riverbeds against a clean baseline to find obstructions (dumping, debris, narrowing).
3. **Risk** — uses Sofia's terrain to estimate, for each obstruction, what gets flooded downstream (metro, roads, homes).
4. **ROI** — prices the cost of inaction (flood damage) against the cost of clearing now, and ranks by return.
5. **Dispatch** — generates a concrete work order for the crew: coordinates, deadline before the storm, reason, and the money saved.

---

## How it works: brain + showcase

The system is split in two so the live demo never depends on heavy computation or network calls.

```
  ┌─────────────────────────── BRAIN (Python, offline) ───────────────────────────┐
  │  Open-Meteo ─┐                                                                  │
  │  OpenTopo  ──┤                                                                  │
  │  OSM       ──┼─►  ingest ─► detect ─► risk ─► roi ─► dispatch ─► scenario.json  │
  │  Anthropic ──┘                                                                  │
  └────────────────────────────────────────────────────────────────────────────────┘
                                          │  (commit to GitHub)
                                          ▼
  ┌──────────────────────── SHOWCASE (frontend, Vercel) ───────────────────────────┐
  │  reads scenario.json  ─►  interactive map  ·  risk panel  ·  ROI  ·  work order  │
  └────────────────────────────────────────────────────────────────────────────────┘
```

- The **brain** (this Python project) calls every API **once, during the build**, and bakes the result into a single `scenario.json`.
- The **showcase** (a static site on Vercel) only reads that JSON. No keys, no API calls, nothing to crash on stage. The URL can be opened on any phone during the pitch.

`scenario.json` is the **contract** between the two — see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Repository structure

```
riverguard/
├── README.md              # this file
├── ARCHITECTURE.md        # data flow + scenario.json contract
├── DATA_SOURCES.md        # where every dataset comes from
├── requirements.txt       # Python dependencies
├── .env.example           # required API keys (copy to .env)
├── .gitignore
├── config.py              # AOI bbox, rain thresholds, cost norms
├── run.py                 # one command → builds scenario.json
│
├── src/
│   ├── ingest/            # weather.py dem.py osm.py satellite.py flood_maps.py
│   ├── detect/            # change_detection.py  (before/after obstruction finder)
│   ├── risk/              # flow.py exposure.py score.py
│   ├── roi/               # damage.py roi.py     (JRC depth-damage → cost)
│   ├── dispatch/          # ticket.py            (work-order generator)
│   └── pipeline.py        # glues stages 1→5
│
├── data/
│   ├── raw/               # downloaded source data (git-ignored)
│   ├── interim/           # reprojected / clipped to AOI
│   └── processed/
│       └── scenario.json  # ← the deliverable the frontend reads
│
└── web/                   # Vercel frontend (reads scenario.json)
    └── public/scenario.json
```

---

## Quickstart — the brain (Python engine)

```bash
# 1. environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. keys
cp .env.example .env             # then fill in your keys

# 3. build the scenario
python run.py                    # → data/processed/scenario.json
```

`run.py` runs the full pipeline for the configured area of interest and writes `scenario.json`, then copies it into `web/public/` for the frontend.

> Geospatial packages (`geopandas`, `rasterio`, `pysheds`) sometimes need system libraries. If `pip` struggles, use a conda environment, or let Claude Code resolve the install for your OS.

## Quickstart — the showcase (frontend)

The frontend lives in `web/` and reads `web/public/scenario.json`. Deploy to Vercel by connecting the GitHub repo (root directory: `web/`). For local preview, serve the `web/` folder with any static server. Map tiles use Mapbox (free token) or Leaflet + OpenStreetMap tiles (no token).

---

## Scope: MVP vs roadmap

| Stage | MVP (we build) | Roadmap (we narrate) |
|-------|----------------|----------------------|
| Trigger | Real Open-Meteo call + one chosen storm scenario | Continuous 24/7 monitoring, auto-activation |
| Detect | Change detection on 2–3 hero points | City-wide coverage, drone flights, IoT level sensors |
| Risk | Flow-from-point on real Sofia DEM + OSM assets | Full hydraulic modelling (HEC-RAS), all rain scenarios |
| ROI | JRC depth-damage × flood depth × asset exposure | Calibration on real damage history, insurer models |
| Dispatch | LLM-generated work order | Integration with municipal systems, execution tracking |

The demo hero is **Risk → ROI → Dispatch** on one scenario and a handful of points. Honesty about what is synthetic strengthens the pitch.

---

## Data sources

Every dataset is open and free. Full inventory with URLs, licenses and access methods in [`DATA_SOURCES.md`](./DATA_SOURCES.md). Headline sources: Open-Meteo (forecast), Copernicus GLO-30 via OpenTopography (terrain), JRC Global Flood Depth-Damage Functions (cost model), official EU Floods Directive hazard maps (flood depth), OpenStreetMap (assets), Sofiaplan / urbandata.sofia.bg (city context).

## Team

| Role | Owner |
|------|-------|
| Engine + data (Python) | — |
| Frontend + map (Vercel) | — |
| Economics + pitch | — |

## Credits & license

Data under their respective licenses (see `DATA_SOURCES.md`); Open-Meteo data CC BY 4.0. Prototype built at Hack Smart Sofia. Code released under the MIT License.
