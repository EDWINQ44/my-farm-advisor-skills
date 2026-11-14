# Assignment 2 demo producer: Nebraska / York County

Demonstration identifiers (not real farm or grower names):

| Item | Value |
| --- | --- |
| Grower slug | `ne-york-grower` |
| Farm slug | `york-demo-farm` |
| Farm display name | York Demo Farm |
| State / county | Nebraska (FIPS 31) / York County (FIPS 31185) |
| Fields | `ne-r1` … `ne-r10` |
| Runtime root | `/home/coder/my-farm-advisor-runtime-a2` |

The grower, farm and field slugs are synthetic demo identifiers. The field
polygons themselves are real USDA CSB polygons (see below), not rectangles.

## Why York County for corn/soy + center-pivot irrigation

County-level evidence (2022 Census of Agriculture):

| Indicator | Value | Source |
| --- | --- | --- |
| Irrigated acres | 254,793 (73 % of land in farms) | NASS 2022 County Profile, York County |
| Irrigated harvested cropland | 254,491 ac (348 farms) | NASS 2022, Table 10 "Irrigation: 2022 and 2017" |
| Corn for grain | 199,819 ac (6th in Nebraska) | NASS 2022 County Profile |
| Soybeans for beans | 114,236 ac (7th in Nebraska) | NASS 2022 County Profile |
| Center pivot share of Nebraska irrigation | ~85 % (2012 Farm and Ranch Irrigation Survey analysis); up to ~97 % in recent reporting | UNL Extension EC3017; UNL CropWatch |

Verifiable sources:

- https://www.nass.usda.gov/sites/default/files/publications/agcensus/2022/Online_Resources/County_Profiles/Nebraska/cp31185.pdf
- https://www.nass.usda.gov/Publications/AgCensus/2022/Full_Report/Volume_1,_Chapter_2_County_Level/Nebraska/st31_2_010_010.pdf
- https://cropwatch.unl.edu/2024/center-pivots-innovation-grew-crops-and-acres-nebraska/
- https://extensionpubs.unl.edu/publication/ec3017/2018/pdf/view/ec3017-2018.pdf

**Claim boundary:** the irrigation evidence is county-level. Nothing in this
dataset proves that any individual `ne-r*` polygon is irrigated, or that it is
served by a center pivot. Do not state field-level irrigation without
field-specific evidence (pivot records, irrigation permits, or imagery).

## Field selection method

Source: USDA NASS Crop Sequence Boundaries (CSB) through the FIBOA GeoParquet
`us_usda_cropland.parquet`, ingested by
`src/scripts/ingest/download_csb_fields.py`.

- Geometry snapshot: `NationalCSB_2016-2023_rev23`, downloaded 2024-11-25,
  adjacent polygons dissolved by their **2023** crop. Single vintage — this is
  not annual boundary history, and the boundary `year` property stays empty.
- Search window: York County bbox `S W N E = 40.6985 -97.8263 41.0470 -97.3681`
  (bbox only prunes the parquet scan).
- County containment: candidate representative point inside the TIGER 2025
  county polygon and ≥ 99.9 % of polygon area inside the county.
- Crop filter: `Corn,Soybeans` on the CSB 2023 crop label.
- Area: 40 ha ≤ polygon ≤ 300 ha, measured in the file's equal-area CRS
  (EPSG:5070 Albers).
- Ranking and cap: largest fields first, 10 selected. No duplicate `csb_id`,
  no duplicate geometry, no overlap above 1 m² among selected fields.
- Accessed: 2026-11-14 (`csb_fields_provenance.json`).

Selected fields:

| Field | Area (ha) | CSB 2023 crop | CSB id |
| --- | --- | --- | --- |
| ne-r1 | 221.8 | Soybeans | 311623006871594 |
| ne-r2 | 211.3 | Corn | 311623006871918 |
| ne-r3 | 210.4 | Corn | 311623004009311 |
| ne-r4 | 209.7 | Soybeans | 311623006871599 |
| ne-r5 | 208.2 | Soybeans | 311623004008878 |
| ne-r6 | 207.5 | Corn | 311623001127773 |
| ne-r7 | 203.8 | Soybeans | 311623006875690 |
| ne-r8 | 189.1 | Soybeans | 311623004011033 |
| ne-r9 | 185.4 | Corn | 311623001127082 |
| ne-r10 | 184.3 | Corn | 311623001127270 |

These 10 polygons are the largest qualifying corn/soy fields inside the
county. They are **not** a representative sample of York County agriculture
and must not be presented as one.

## Data periods used for assignment 2

| Variable | Period | Provider |
| --- | --- | --- |
| Field weather | 2021-01-01 … 2025-12-31, local solar time | NASA POWER S3 Zarr (MERRA-2 + SYN1DEG) |
| CDL tables | 2019 … 2025 | USDA NASS CDL, state tile 31 |
| CDL-derived rotation | 2021 … 2025 (last five years) | `summarize_crop_history` window |

2026 is excluded because it is partial. CDL state tiles for Nebraska
(`CDL_2019_31.tif` … `CDL_2025_31.tif`) were downloaded to
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/cdl/rasters/`.

## Reproduce

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime-a2
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
export AG_GROWER_SLUG=ne-york-grower AG_FARM_SLUG=york-demo-farm

"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_csb_fields.py \
  --bbox 40.6985 -97.8263 41.0470 -97.3681 \
  --min-area-ha 40 --max-area-ha 300 --max-fields 10 \
  --field-prefix ne-r --field-start-index 1 --skip-existing \
  --county-fips 31185 --state-fips 31 --state NE \
  --crop-names Corn,Soybeans --dry-run   # drop --dry-run to write

"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_weather.py \
  --grower-slug ne-york-grower --farm-slug york-demo-farm \
  --weather-backend zarr --weather-start-year 2021 --weather-end-year 2025 \
  --weather-time-standard lst

AG_GROWER_SLUG=ne-york-grower AG_FARM_SLUG=york-demo-farm \
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_cdl.py --cdl-years 2019,2020,2021,2022,2023,2024,2025
```

## Outputs

```
growers/ne-york-grower/grower.json
growers/ne-york-grower/farms/york-demo-farm/farm.json
growers/ne-york-grower/farms/york-demo-farm/boundary/field_boundaries.geojson
growers/ne-york-grower/farms/york-demo-farm/fields/ne-r*/boundary/field_boundary.geojson
growers/ne-york-grower/farms/york-demo-farm/manifests/field-inventory.csv
growers/ne-york-grower/farms/york-demo-farm/manifests/csb_fields_provenance.json
growers/ne-york-grower/farms/york-demo-farm/derived/tables/york_demo_weather_2021_2025.csv
growers/ne-york-grower/farms/york-demo-farm/derived/tables/york_demo_2019_cdl.csv … york_demo_2025_cdl.csv
growers/ne-york-grower/farms/york-demo-farm/derived/tables/york_demo_cdl_2019_2025_full_composition.csv
growers/ne-york-grower/farms/york-demo-farm/derived/tables/york_demo_crop_rotation.csv
```

Not generated in this step (out of scope): soil, DEM/terrain, satellite
imagery, NDVI products, reports, posters, producer maps.
