# Data sources

Every dataset RiverGuard uses is open and free, and reachable within the hackathon. All API calls happen in the engine at build time. This is the team's reference for *what to download, from where, and how*.

---

## A. Weather forecast — the trigger

**Open-Meteo** — `https://api.open-meteo.com/v1/forecast`
- No API key, JSON over HTTP, hourly precipitation up to 16 days, license CC BY 4.0.
- Sofia coordinates: `latitude=42.70&longitude=23.32`.
- Useful params: `hourly=precipitation,precipitation_probability`, `forecast_days`, `timezone=auto`.
- Historical archive (for synthetic / past events): `https://archive-api.open-meteo.com/v1/archive`.
- Flood-specific API (river discharge): `https://flood-api.open-meteo.com/v1/flood` — optional, roadmap.
- Used in: `src/ingest/weather.py` → `forecast` block of `scenario.json`.

## B. Terrain / elevation — where water flows

**Copernicus DEM GLO-30** (30 m digital surface model) via **OpenTopography**
- API: `https://portal.opentopography.org/API/globaldem` (param `demtype=COP30`, plus AOI bounds and `API_Key`).
- Free key: register at `https://portal.opentopography.org/`.
- Output: GeoTIFF / Cloud-Optimized GeoTIFF.
- Higher resolution alternative if granted access: orthophoto / elevation from `gis-sofia.bg` (SOFCAR).
- Used in: `src/ingest/dem.py` → flow direction / accumulation for `src/risk/flow.py`.

## C. Flood hazard maps — flood depth

**EU Floods Directive (2007/60/EC) hazard & risk maps** — official, modelled with HEC-RAS, showing flood depth, extent, hazard degree, water velocity.
- Ministry portal: `https://www.moew.government.bg/bg/karti-na-rajonite-pod-zaplaha-i-s-risk-ot-navodneniya/`
- Sofia sits in the **Danube Basin Directorate (BDDR)** area (Iskar river basin and tributaries).
- Note: often published as GIS layers (WMS) or PDF map sheets. If not machine-readable, use scenario depths (0.5 / 1.0 / 2.0 m) in `config.py`.
- Used in: `src/ingest/flood_maps.py` → `risk.flood_depth_m`.

## D. Satellite / aerial imagery — obstruction detection

**Sentinel-2** (10 m optical, free) via **Copernicus Data Space Ecosystem** — `https://dataspace.copernicus.eu/`
- For before/after change detection on riverbeds.
**Sentinel-1 SAR** (cloud-penetrating) — flood extent during storms (roadmap).
**High-resolution orthophotos** — `gis-sofia.bg`, plus public aerial tiles, needed to actually see debris/dumping in channels (Sentinel-2 is too coarse for small litter — use ortho tiles for the hero points).
- The challenge slides (8–10) already provide before/after pollution examples usable for the demo.
- Used in: `src/ingest/satellite.py`, `src/detect/change_detection.py`.

## E. City assets & rivers — what gets flooded

**OpenStreetMap** via Overpass API / `osmnx`
- Overpass: `https://overpass-api.de/api/interpreter`
- Bulgaria bulk extract: `https://download.geofabrik.de/europe/bulgaria.html`
- Tags we use: `waterway=river|stream|canal` (rivers), `building` (homes → damage), `amenity=hospital|school`, `railway=station` / metro, `highway` (roads).
- Used in: `src/ingest/osm.py` → `rivers[]` and `exposure` in `scenario.json`.

## F. Sofia open data — context & credibility

- **Sofiaplan API** — `https://api.sofiaplan.bg` (JSON, downloadable layers, open license).
- **urbandata.sofia.bg** — the municipality's new urban-data platform / "digital twin of Sofia" (data maintained by GIS-Sofia). Strong narrative hook: RiverGuard as a module for it.
- **gis-sofia.bg / SOFCAR** — cadastre and regulation plans (river-vs-property conflicts, if shown).
- **sofiyskavoda.bg** (Sofiyska Voda / water utility) — sewer & water network context.
- **avarii.bg/sofia** — real-time water/utility outages (potential live signal, roadmap).

## G. Damage / cost model — defending the ROI

**JRC Global Flood Depth-Damage Functions** (EUR 28552, Huizinga, de Moel & Szewczyk, 2017)
- Repository: `https://publications.jrc.ec.europa.eu/repository/handle/JRC105688`
- Depth → fractional-damage curves + maximum replacement values per asset class, for Europe. CSV.
- Ready-to-use packaging in HydroMT-FIAT (`jrc_vulnerability_curves`) if helpful.
- Convert EUR → BGN (fixed peg ≈ 1.95583 BGN/EUR).
- Used in: `src/roi/damage.py`.

**Cost context for the pitch (facts, not inputs):** about 10% of homes in Bulgaria are insured, so damage falls on personal funds or state compensation; home insurance runs ~50–400 BGN/year; spring 2026 saw disaster declarations in several municipalities with BG-Alert activated. These strengthen the "prevention is cheaper" argument.

---

## Quick reference

| Source | Gives | Key needed | License |
|--------|-------|------------|---------|
| Open-Meteo | Precipitation forecast | No | CC BY 4.0 |
| OpenTopography (COP30) | Terrain / DEM | Free key | Copernicus / open |
| MOSV / BDDR PURN maps | Flood depth & extent | No | Public sector |
| Copernicus Data Space | Sentinel-2/1 imagery | Free account | Copernicus open |
| OpenStreetMap | Rivers, buildings, assets | No | ODbL |
| Sofiaplan API | City planning layers | No | Open |
| JRC depth-damage | Damage curves & values | No | EU, reuse w/ attribution |
| Mapbox (frontend) | Map tiles | Free token | Mapbox ToS |

> Attribution: keep credits for Open-Meteo (CC BY 4.0), OpenStreetMap (© OpenStreetMap contributors, ODbL), Copernicus, and JRC in the app footer and the final slide.
