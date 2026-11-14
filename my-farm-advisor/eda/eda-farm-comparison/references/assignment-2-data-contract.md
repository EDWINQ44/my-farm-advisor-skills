# Assignment 2 data contract

What the comparison script reads, in what units, and which traps it guards
against. Source of truth is the assignment-2 runtime tree; the script never
downloads data.

## Producers

| Key | Grower | Farm | State / county | County FIPS |
| --- | --- | --- | --- | --- |
| IL | `il-dekalb-grower` | `dekalb-demo-farm` | Illinois / DeKalb | 17037 |
| IA | `ia-story-grower` | `story-demo-farm` | Iowa / Story | 19169 |
| NE | `ne-york-grower` | `york-demo-farm` | Nebraska / York | 31185 |

Grower, farm and field slugs are synthetic demo identifiers. Field polygons are
real USDA CSB polygons.

## Field boundaries

`growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`

| Property | Type | Meaning |
| --- | --- | --- |
| `field_id` | string | `il-r1` ... `il-r10`, etc. |
| `country` | string | `US` |
| `state`, `state_fips` | string | State code and two-digit FIPS |
| `county` | string | CSB county name |
| `area_ha_est`, `area_acres` | float | Source area; the script recomputes area in EPSG:5070 |
| `crop` | string | **CSB 2023 crop label**, not an annual result |
| `source` | string | `usda_csb_fiboa` |
| `csb_id` | string | CSB polygon id |
| `year` | string | Empty: CSB is a single snapshot |

Snapshot: `NationalCSB_2016-2023_rev23` (downloaded 2024-11-25), adjacent
polygons dissolved by their 2023 crop. Not annual boundary history.

Selection: top-10 largest corn/soybean polygons per county, 40-300 ha, at least
99.9 % of each polygon inside the TIGER county, no duplicate CSB id, no
overlap. This is a truncated, non-random sample.

## Weather

`growers/<grower>/farms/<farm>/derived/tables/<prefix>_weather_2021_2025.csv`

| Column | Unit | Notes |
| --- | --- | --- |
| `field_id` | - | 10 fields per farm |
| `lat`, `lon` | degrees | Field centroid, EPSG:4326 |
| `date` | ISO date | 2021-01-01 ... 2025-12-31, 1826 days |
| `T2M` | degC | Daily mean temperature at 2 m |
| `T2M_MAX`, `T2M_MIN` | degC | Daily extremes |
| `PRECTOTCORR` | mm/day | Bias-corrected precipitation |
| `ALLSKY_SFC_SW_DWN` | MJ/m2/day | Shortwave downward irradiance |
| `RH2M` | % | Relative humidity |
| `WS10M` | m/s | Wind speed at 10 m |

Source: NASA POWER S3 Zarr (MERRA-2 + SYN1DEG), local solar time. Model output
on a ~0.5-degree grid, sampled at field centroids.

Checks: no NaN, no `-999` fill values, exactly 1826 dates, 10 fields.

**Climate units:** fields whose daily `T2M` series are identical are one NASA
POWER cell. The script labels them `<producer>-1`, `-2`, ... and asserts that
all climate variables are also identical inside the unit. Effective sample
size: IL 2, IA 2, NE 3 units. Field counts per unit are reported in
`t_b_climate_units.csv`; fields are never treated as independent climate
replicates.

Growing season: April 1 - September 30 (183 days every year). Precipitation is
summed per unit-date after deduplication; temperature is the mean. Summing
field rows without deduplication multiplies the same rainfall.

## CDL

`growers/<grower>/farms/<farm>/derived/tables/<prefix>_YYYY_cdl.csv`,
2021-2025.

| Column | Unit | Notes |
| --- | --- | --- |
| `field_id` | - | 10 fields |
| `year` | year | 2021-2025 |
| `crop_code`, `crop_name` | CDL class | Classes include Corn, Soybeans, Alfalfa, Forest, Grass/Pasture, Fallow/Idle, Winter Wheat |
| `pixel_count` | count | 30 m pixels inside the polygon |
| `pct` | % | Share of **all rasterized pixels**, including unclassified/edge pixels |
| `crop_source` | string | `cdl` |

Source rasters: USDA NASS CDL, state tiles 17/19/31, 30 m, EPSG:5070.

Normalization: for each field-year, `pct_norm = pct / sum(pct) * 100` over
classified rows. `coverage = sum(pct)` (classified / all rasterized pixels);
NoData = `100 - coverage`. A field-year with zero classified pixels is an
error. Producer composition weights class area by **classified field area**,
so coverage differences do not silently redistribute NoData. Coverage and
NoData are reported in the tables and as text under the composition figure.

Observed coverage: 97.1-100.0 % per field-year before aggregation; area-weighted
producer-year coverage is about 98.4-99.7 %. Intermediate values are held
unrounded until the final CSV write.

Dominance: highest `pct_norm` per field-year. `gap_pct` is top minus second.
`weak_dominance_lt10pp` flags a gap below 10 percentage points; this is a
descriptive label, not statistical uncertainty. `exact_tie` flags a zero gap.
In this dataset the minimum gap is 12.0 pp, so no weak-dominance or tie cells
exist.

Transitions: consecutive year pairs (2021-22, ..., 2024-25) on the dominant
class. Denominator is 40 per producer (10 fields x 4 pairs), reported
explicitly in every transition row. CSB 2023 labels are not used for
transitions.

## Geoadmin layers for the map

- `shared/geoadmin/l2_counties/counties_usa.geojson` (TIGER 2025 county polygons)
- `shared/geoadmin/l1_states/states_usa.geojson` (TIGER 2025 state polygons)

Local UTM projection per panel: IL 16N, IA 15N, NE 14N. Areas in tables are
computed separately in EPSG:5070 (equal-area).

## Known interpretation limits

- No per-field irrigation data; irrigation cannot be attributed.
- No soil analysis in this workflow.
- The three producers are not representative samples of their states.
- CDL is a classification product with mixed pixels and class error; "Other"
  is heterogeneous.
- Weather is modelled cell data, not on-farm measurement.
