# RiverGuard

**Turn the weather forecast into a work order — clear the right river blockage before it floods Sofia.**

> Hack Smart Sofia** (challenge: *Sponge City & Urban Rivers*).
> Live demo: **https://river-guard-blush.vercel.app**

RiverGuard is an early-warning system. When heavy rain is forecast, it scans Sofia's
rivers from satellite with AI, finds the channels clogged by debris, dumping or
overgrowth, models which streets and buildings will flood and the damage in euros,
and hands a crew a ranked work order — turning a few hundred euros of prevention
into hundreds of thousands of euros of avoided damage.

---

## The problem

Sofia floods almost every summer. In 2020 the **Perlovska** and **Vladayska** rivers
burst their banks — metro stations and underpasses underwater, 140+ emergency calls
in one night. It keeps happening (2018, 2020, 2022…). Bulgaria loses **~€58M/year** to
floods; only **~10%** of homes are insured, so the state and citizens absorb the rest.
A blocked channel turns ordinary rain into a flood — and nobody has a prioritized,
money-based list of *what to clear first*.

## What RiverGuard does

1. **Trigger** — watches the rain forecast; an incoming storm starts the clock.
2. **Detect** — for each point along the rivers, an AI compares the live satellite
   image against the map and flags blocked / overgrown / narrowed channels.
3. **Flood model** — pulls real terrain and spreads the backed-up water over the low
   ground to see which blocks and roads go under, and how deep.
4. **ROI** — prices the damage (EU JRC depth-damage curves, Bulgaria-adjusted) against
   the €450 cost of clearing, and ranks every site by return.
5. **Dispatch** — an AI writes the crew a concrete plan: what to clear, what gear, by when.

## How it works: brain + showcase

The system is split in two so the live demo never depends on network calls or keys.

```
  ┌──────────── BRAIN (Python, offline) ─────────────┐
  │  Open-Meteo  ┐                                    │
  │  OpenStreetMap├─ ingest → detect → flood → roi    │
  │  Esri imagery │           → plan → scenario.json  │
  │  OpenRouter  ┘                                    │
  └──────────────────────────────────────────────────┘
                     │ (commit to GitHub)
                     ▼
  ┌──────────── SHOWCASE (static, Vercel) ───────────┐
  │  reads scenario.json → landing + map console      │
  │  flood zone · risk panel · ROI · AI work order    │
  └──────────────────────────────────────────────────┘
```

- The **brain** (`run.py` + modules) calls every API once and bakes the result into a
  single `scenario.json`.
- The **showcase** (static site on Vercel) only reads that JSON — no keys, no API calls,
  nothing to crash on stage. Open it on any phone during the pitch.

## What's real vs modeled (we say so plainly)

- **Real data:** rivers & city assets (OpenStreetMap), satellite imagery (Esri),
  AI blockage detection, terrain (Copernicus GLO-90 via Open-Meteo), the flood
  footprint over real terrain, exposed buildings/roads, damage € (JRC).
- **Real data + first-order model:** water depth (rainfall × blockage proxy) and the
  bathtub inundation spread — not a full hydrodynamic solve.
- **Demo:** the storm is a demo event when no real rain is forecast (real Open-Meteo
  wired as the trigger).

## Tech & data sources

| Source | Used for | Key? |
|--------|----------|------|
| Open-Meteo | rain forecast + terrain elevation (Copernicus GLO-90) | no |
| OpenStreetMap / Overpass | rivers, buildings, roads, hospitals, stations | no |
| Esri World Imagery + Topo | satellite vs map images for the AI | no |
| OpenRouter | vision model (detection) + text model (work order) | yes |
| EU JRC — Huizinga et al. 2017 | depth-damage curves, Bulgaria-adjusted | open |
| Leaflet + CartoDB | dark basemap for the console | no |

## Quickstart

**Engine (Python):**
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add your OPENROUTER_API_KEY
python run.py               # → writes data/processed/scenario.json and web/scenario.json
```

**Frontend (static):**
```bash
cd web && python -m http.server 8000   # open http://localhost:8000
```
`web/index.html` is the landing page; `web/console.html` is the live map console;
both read `web/scenario.json`. Map tiles are Leaflet + CartoDB (no token). Deploy by
connecting the repo to Vercel with root directory `web/`.

## Repository

```
RiverGuard/
├── run.py            # orchestrator → scenario.json
├── weather.py        # Open-Meteo forecast + storm detection
├── osm.py            # OpenStreetMap rivers & assets (Overpass)
├── detect.py         # AI vision: satellite vs map → blockage
├── discover.py       # auto-discovery of obstruction points along rivers
├── flood.py          # terrain flood footprint (bathtub inundation)
├── exposure.py       # buildings/roads/assets inside the flood zone
├── damage.py         # JRC depth-damage, Bulgaria-adjusted, per-building
├── ai_plan.py        # AI clearing plan for the crew
├── check_limits.py   # OpenRouter quota helper
├── config.py         # area of interest, thresholds, cost norms
└── web/
    ├── index.html    # landing page
    ├── console.html  # live map console
    └── scenario.json # the brain↔showcase contract
```

## Roadmap

Full hydraulic modelling (DEM + HEC-RAS, official EU Floods Directive / PURN maps)
instead of the depth proxy · live storm trigger · dispatcher workflow (dispatched /
cleared, prevented-€ tracking) · validation against historical floods · multi-city ·
integration with municipal systems.

## Team

| Role | Owner |
|------|-------|
| Engine, data & frontend | **Vladislav Yakunin** ([@vlad-is-dev](https://github.com/vlad-is-dev)) |
| Pitch & business | **Vladislav Yakunin** |

## License

Code under the **MIT License**. Data under their respective licenses (Open-Meteo CC BY 4.0,
OpenStreetMap ODbL, Esri terms, Copernicus free, EU JRC open). Built at Hack Smart Sofia.