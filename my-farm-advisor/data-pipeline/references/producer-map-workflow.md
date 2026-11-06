# Producer Maps (data-pipeline subskill)

Per-producer interactive field maps as lightweight, self-contained HTML files.

## Purpose

Emit **one HTML per producer (grower)** that shows every real field boundary under
that producer's farms on an online satellite basemap. The output is deliberately
lightweight:

- It embeds only each field's **real polygon** plus light metadata (producer, farm,
  field name, county/state, crop, acres), so the downloaded file still works offline.
- It does **not** embed rasters, DEMs, or large datasets. The satellite background
  is streamed live from **ESRI World Imagery** tiles in the browser.

Click interactions are embedded in the HTML itself:

- click a field → its real polygon
- click shows a **popup** with producer, farm, and field name (plus useful extras)
- the map auto-fits to the producer's fields (`fitBounds`)
- a **side panel lists every field**; clicking a field flies to it and opens its popup

## Sources (real polygons)

Field boundaries come from the canonical runtime tree already produced by the
Farm data pipeline (USDA CSB/FIBOA; EPSG:4326 Polygon):

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson
```

Producers used for assignment-1 (Phase 3):

| Grower (producer) | Farm (display_name) | Fields (real polygons) | State |
|---|---|---|---|
| `il-dekalb-grower` | DeKalb Demo Farm | il-r1, il-r2, il-r3 | IL |
| `ia-story-grower` | Story Demo Farm | ia-r1, ia-r2, ia-r3 | IA |

## Runtime contract

Run from the runtime script copy (not the checkout `src/`), with the data root set:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  ./render_producer_maps.py --grower il-dekalb-grower
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  ./render_producer_maps.py --grower ia-story-grower
```

Or render both in one run (default target when no `--grower`/`--all`):

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" ./render_producer_maps.py
```

### Output locations (kept out of Git)

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/il-dekalb-grower/farms/dekalb-demo-farm/maps/producer_il-dekalb-grower_map.html
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/ia-story-grower/farms/story-demo-farm/maps/producer_ia-story-grower_map.html
```

## Testing / verification

1. The generated HTML should be small (target ≪ 1 MB) and should contain no base64
   raster payloads.
2. Open each HTML in a browser (or via `python -m http.server`) and confirm:
   - satellite basemap renders,
   - all three real field polygons are drawn,
   - clicking a field opens the info popup (producer / farm / field),
   - the side list shows all fields and clicking one flies to it,
   - the map is auto-fitted to the producer's fields on load.
3. `git status` in the worktree must show only the new **source/docs** files; generated
   HTML stays under `${DATA_PIPELINE_DATA_ROOT}` and is excluded from Git.

## Editing

- The generator lives in `src/scripts/render_producer_maps.py`. Keep it dependency-free
  beyond the standard library for reading GeoJSON so it runs in the pipeline venv.
- After editing, re-copy to the runtime `src/scripts/` (pattern: `rsync -r --no-times
  --ignore-existing`) so the runtime uses the updated script.