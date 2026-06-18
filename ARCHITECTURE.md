# Architecture

RiverGuard has two halves connected by a single file. The **engine** (Python) does all the work offline and produces `scenario.json`. The **frontend** (Vercel) only reads `scenario.json`. This document defines the data flow and, most importantly, the exact shape of `scenario.json` — the contract that lets the engine team and the frontend team work in parallel.

---

## Data flow

```
config.py  (area of interest, rain thresholds, cost norms)
    │
    ▼
INGEST                         what it produces
  weather.py    Open-Meteo  →  forecast: hourly precipitation, storm event
  dem.py        OpenTopo    →  Sofia elevation raster (GeoTIFF) + flow grid
  osm.py        OSM/Overpass→  rivers, buildings, roads, critical assets (GeoJSON)
  satellite.py  Copernicus  →  before/after image tiles for hero points
  flood_maps.py PURN/MOSV   →  flood depth per location (or scenario depths)
    │
    ▼
DETECT
  change_detection.py        →  obstruction points (type, narrowing %, before/after)
    │
    ▼
RISK
  flow.py                    →  downstream water path from each point
  exposure.py                →  which assets that path floods
  score.py                   →  risk score 0–100 and level per point
    │
    ▼
ROI
  damage.py   (JRC curves)   →  cost of inaction (BGN) per point
  roi.py                     →  clearing cost, ratio, priority ranking
    │
    ▼
DISPATCH
  ticket.py   (LLM)          →  work-order text per point
    │
    ▼
pipeline.py  →  data/processed/scenario.json  →  copied to web/public/scenario.json
```

Run order is bottom-of-value-first: build `weather → osm → dem → risk → roi` so the killer ROI number exists early, then add detection, dispatch, and the map.

---

## Key handling

- Secrets live **only** in `.env` on the engine machine (`OPENTOPO_API_KEY`, `ANTHROPIC_API_KEY`). Never committed.
- All API calls happen in the engine, at build time. The result is static.
- The deployed frontend contains **no keys and makes no API calls** — only a Mapbox display token (public, restricted) if Mapbox tiles are used. Leaflet + OSM tiles need none.

---

## The `scenario.json` contract

One scenario = one forecast event for one area of interest, with a ranked list of obstruction points. The frontend renders entirely from this object.

### Example

```json
{
  "meta": {
    "schema_version": "1.0",
    "generated_at": "2026-06-18T22:10:00Z",
    "city": "Sofia",
    "scenario_name": "Perlovska center — storm scenario",
    "aoi_bbox": [23.30, 42.66, 23.40, 42.71]
  },

  "forecast": {
    "source": "open-meteo",
    "issued_at": "2026-06-18T18:00:00Z",
    "event": {
      "start": "2026-06-20T08:00:00Z",
      "lead_time_h": 38,
      "peak_mm_h": 18,
      "total_mm": 42
    },
    "severity": "high"
  },

  "rivers": [
    {
      "id": "perlovska",
      "name": "Perlovska",
      "geometry": { "type": "LineString",
        "coordinates": [[23.31,42.70],[23.33,42.69],[23.35,42.685]] }
    }
  ],

  "points": [
    {
      "id": "P1",
      "river_id": "perlovska",
      "river_name": "Perlovska",
      "lat": 42.685,
      "lon": 23.345,

      "obstruction": {
        "type": "construction_debris",
        "label": "Construction debris narrowing the channel",
        "channel_narrowing_pct": 60,
        "detected_by": "vision",
        "image_before": "tiles/p1_before.jpg",
        "image_after": "tiles/p1_after.jpg"
      },

      "risk": {
        "score": 92,
        "level": "critical",
        "flood_depth_m": 1.2
      },

      "exposure": {
        "buildings": 18,
        "road_m": 240,
        "critical_assets": [
          { "type": "metro_station", "name": "Stadion" },
          { "type": "road", "name": "Blvd Evlogi Georgiev", "length_m": 240 }
        ]
      },

      "roi": {
        "damage_bgn": 187000,
        "clearing_cost_bgn": 600,
        "ratio": 311,
        "net_saving_bgn": 186400
      },

      "dispatch": {
        "crew": "Crew 4",
        "coords": [42.685, 23.345],
        "deadline": "2026-06-20T18:00:00Z",
        "reason": "Prevent estimated 187,000 BGN of flood damage downstream",
        "ticket_text": "Crew 4 → 42.685, 23.345. Clear construction debris by Fri 18:00 (before rain). Reason: prevents ~187,000 BGN damage to metro Stadion, 240 m of Blvd Evlogi Georgiev, 18 buildings."
      }
    }
  ],

  "summary": {
    "points_total": 3,
    "critical_count": 1,
    "damage_at_risk_bgn": 250000,
    "clearing_cost_total_bgn": 1700
  }
}
```

### Field reference

**meta**
| field | type | meaning |
|-------|------|---------|
| schema_version | string | bump if the shape changes |
| generated_at | ISO datetime | when the engine produced this |
| city | string | always "Sofia" for now |
| scenario_name | string | human label shown in the UI header |
| aoi_bbox | [minLon, minLat, maxLon, maxLat] | map fit bounds |

**forecast**
| field | type | meaning |
|-------|------|---------|
| source | string | "open-meteo" |
| issued_at | ISO datetime | forecast issue time |
| event.start | ISO datetime | when the rain starts |
| event.lead_time_h | number | hours until the event (banner countdown) |
| event.peak_mm_h | number | peak intensity, mm/hour |
| event.total_mm | number | total expected rainfall |
| severity | "low"\|"medium"\|"high" | drives banner colour |

**rivers[]** — drawn as lines on the map.
| field | type | meaning |
|-------|------|---------|
| id | string | stable id, referenced by points |
| name | string | display name |
| geometry | GeoJSON LineString | `[lon, lat]` pairs |

**points[]** — the markers and the side panel. Sorted by `roi.ratio` descending.
| field | type | meaning |
|-------|------|---------|
| id | string | "P1", "P2", … |
| river_id / river_name | string | which river |
| lat, lon | number | marker position |
| obstruction.type | string | machine type, e.g. construction_debris, dumping, narrowing, vegetation |
| obstruction.label | string | human description |
| obstruction.channel_narrowing_pct | number | 0–100 |
| obstruction.detected_by | "vision"\|"manual"\|"sensor" | provenance (be honest) |
| obstruction.image_before / image_after | string | path under `web/public/` |
| risk.score | number | 0–100 |
| risk.level | "critical"\|"medium"\|"low" | marker colour |
| risk.flood_depth_m | number | depth used for the damage curve |
| exposure.buildings | number | buildings flooded downstream |
| exposure.road_m | number | metres of road flooded |
| exposure.critical_assets[] | objects | named assets (metro, hospital, school, road) |
| roi.damage_bgn | number | cost of inaction |
| roi.clearing_cost_bgn | number | cost to clear now |
| roi.ratio | number | damage / clearing, rounded |
| roi.net_saving_bgn | number | damage − clearing |
| dispatch.crew | string | assigned crew label |
| dispatch.coords | [lat, lon] | for navigation |
| dispatch.deadline | ISO datetime | before the storm |
| dispatch.reason | string | one-line justification |
| dispatch.ticket_text | string | full work order shown / downloaded |

**summary** — header stat cards.
| field | type | meaning |
|-------|------|---------|
| points_total | number | total obstruction points |
| critical_count | number | how many are critical |
| damage_at_risk_bgn | number | sum of all `damage_bgn` |
| clearing_cost_total_bgn | number | sum of all `clearing_cost_bgn` |

### Rules

- Currency is **BGN**, integers (round before writing).
- Coordinates: GeoJSON geometry uses `[lon, lat]`; the convenience `lat`/`lon`/`coords` fields use plain decimals — don't mix them up.
- Datetimes are ISO 8601 UTC (`Z`).
- `points` arrive **already sorted** by `roi.ratio` descending, so the frontend can render the priority list as-is.
- If a value is genuinely unknown, omit the field rather than inventing a number; the frontend treats missing fields gracefully.

---

## How the ROI number is defended

`roi.damage_bgn` is **not** a guess. It is computed as:

```
for each asset flooded downstream:
    damage_fraction = JRC_depth_damage_curve(asset_class, flood_depth_m)
    asset_damage    = damage_fraction × JRC_max_value(asset_class)
damage_bgn = Σ asset_damage
```

- `JRC_depth_damage_curve` and `JRC_max_value` come from the EU Joint Research Centre Global Flood Depth-Damage Functions (Europe), converted EUR→BGN.
- `flood_depth_m` comes from the official EU Floods Directive hazard maps (or scenario depths when the map isn't machine-readable).
- `clearing_cost_bgn` comes from a transparent crew-cost norm in `config.py` (crew + equipment × hours).

This is the methodology a flood-risk consultancy would use, which is exactly why it survives a sceptical question from the jury.
