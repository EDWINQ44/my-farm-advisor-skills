---
name: eda-farm-comparison
description: Compare multiple demo producers on field area, growing-season climate, and CDL crop composition using static, reproducible figures and small tables from the canonical farm runtime.
version: 1.0.0
author: Boreal Bytes
tags: [eda, comparison, fields, climate, cdl, static-figures]
---

# Workflow: eda-farm-comparison

## Description

Cross-producer exploratory comparison for the assignment-2 demo farms. The
workflow builds seven static PNG figures and eight small CSV tables from the
canonical runtime tree, plus a run manifest with input hashes and checks. It
is deliberately narrow: no soil, no dashboards, no interactive maps, and no
final report assembly.

Questions answered:

1. **Field limits** - how large are the 10 selected fields per producer, and how
   do totals, medians and ranges compare?
2. **Climate 2021-2025** - how did April-September precipitation and mean
   temperature differ by place and year?
3. **CDL 2021-2025** - how did the crop mix change, which crop dominated each
   field-year, and how often did corn and soybean alternate?
4. **Location** - where are the real field polygons inside each county?

## When to use

- You need a reproducible multi-farm comparison rather than a single-farm EDA.
- You need static figures and compact tables for a report that is assembled
  elsewhere.
- You must show climate and CDL values without treating fields in the same
  NASA POWER cell as independent observations.

Do not use this workflow for soil analysis, interactive dashboards, or
producer map HTML output. Use `../eda-explore/GUIDE.md`,
`../eda-time-series/GUIDE.md`, or the data-pipeline producer map workflow for
those tasks.

## Inputs

Expected under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`:

| Input | Path |
| --- | --- |
| Field boundaries | `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson` |
| Farm weather 2021-2025 | `growers/<grower>/farms/<farm>/derived/tables/<prefix>_weather_2021_2025.csv` |
| CDL per year 2021-2025 | `growers/<grower>/farms/<farm>/derived/tables/<prefix>_YYYY_cdl.csv` |
| County polygons | `shared/geoadmin/l2_counties/counties_usa.geojson` |
| State polygons | `shared/geoadmin/l1_states/states_usa.geojson` |

The script is pinned to the three assignment-2 producers (`il-dekalb-grower`,
`ia-story-grower`, `ne-york-grower`) and to the 2021-2025 window. Changing the
window requires updating `CLIMATE_YEARS`, `CDL_YEARS`, and the caveats in the
figures and this guide.

## Run

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime-a2
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/eda/eda_farm_comparison.py
```

Outputs default to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/farm-comparison`:

```
eda/farm-comparison/
├── figures/   seven PNG files at 300 dpi
├── tables/    eight CSV files
└── manifests/ run_manifest.json and review_log.md
```

Refresh the runtime source after editing the script:

```bash
cd /home/coder/work/mfask-worktree/assignment-2/my-farm-advisor/data-pipeline
DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime-a2 \
  ./scripts/install.sh --non-interactive --force-refresh --persist none --no-install-deps
```

## Outputs and methods

### A. Field limits

| Output | Question | Method |
| --- | --- | --- |
| `fig_a1_field_area_distribution.png` | How are the 10 field areas distributed per producer? | Points for every field plus box (IQR) and median; hectares |
| `fig_a2_field_area_by_field.png` | Which field contributes which area? | Horizontal bars per field, coloured by CSB 2023 crop |
| `t_a_field_areas.csv` | Field-level table | Area recomputed in EPSG:5070, acres converted, CSB crop and id |
| `t_a_area_summary.csv` | How do producers compare? | n, total, mean, median, min, max, range, IQR |

### B. Climate 2021-2025

| Output | Question | Method |
| --- | --- | --- |
| `fig_b1_precip_apr_sep_by_unit.png` | How much growing-season rainfall per place and year? | Sum of daily `PRECTOTCORR`, April 1 - September 30, **per climate unit** |
| `fig_b2_tmean_apr_sep_selected_fields.png` | How does the thermal season compare? | Mean `T2M` for the largest field per producer (`il-r1`, `ia-r1`, `ne-r1`) |
| `t_b_climate_units.csv` | Which fields share a NASA POWER cell? | Fields with identical daily series are one unit; `n_fields_in_unit` |
| `t_b_growing_season.csv` | Unit-year summaries | 183 days, precipitation mm, mean temperature degC |
| `t_b_variability.csv` | Within- and between-producer variability | Min/max/range across **units**, with `n_fields` and `n_climate_units` |

Rules enforced by the script:

- Fields whose daily series are identical are grouped into one climate unit.
  They are **not** independent observations.
- Precipitation is summed per unit, never across fields. Summing field rows
  would multiply the same cell rainfall.
- Each April-September window must contain 183 days.

### C. CDL 2021-2025

| Output | Question | Method |
| --- | --- | --- |
| `fig_c1_cdl_composition_by_producer_year.png` | How did the crop mix change? | Classified-pixel percentages, area-weighted per producer-year; Other = all non-corn/soy classes |
| `fig_c2_cdl_dominant_matrix.png` | What dominated each field-year? | Highest normalized class share per field-year; asterisk if top-two gap < 10 pp; `=` for exact ties |
| `t_c_cdl_composition.csv` | Full composition, all classes | Area and share of classified area per class; coverage and NoData reported |
| `t_c_cdl_dominant.csv` | Dominant class per field-year | Dominant/second class, gap, weak-dominance flag, coverage |
| `t_c_cdl_transitions.csv` | How often do corn and soy alternate? | Consecutive-year transitions; denominator 40 per producer (10 fields x 4 pairs) |

Rules enforced by the script:

- `pct` in the CDL tables is a share of **all rasterized pixels**, including
  unclassified/edge pixels. It is normalized to 100 over classified pixels
  per field-year before composition or dominance.
- Producer composition is weighted by **classified field area**, not by field
  count. Coverage (`classified / total field area`) and NoData are reported
  separately and never redistributed.
- A field-year with no classified pixels is an error, not a zero.
- Dominance weaker than 10 percentage points is descriptive only, not
  statistical uncertainty. Exact ties are labelled `=`.

### D. Map

`fig_d_field_map_three_panels.png`: one panel per producer with the county
polygon (TIGER 2025), the 10 real CSB 2023 polygons, local UTM projection,
scale bar, north arrow, panel label, shared legend, and a state locator row
with the county in red. No basemap imagery is downloaded; all layers are local.

## Interpretation limits

- **Selection bias:** fields are the 10 largest corn/soybean CSB polygons per
  county, capped at 40-300 ha. The area distribution is truncated. These are
  not random samples of the county or state, and the three producers are not
  representative of Illinois, Iowa or Nebraska.
- **Boundary vintage:** CSB is a single 2023 snapshot, not annual or cadastral
  history. `csb_crop_2023` is a 2023 label; CDL results are annual.
- **Climate:** NASA POWER is a modelled ~0.5-degree product. Field values are
  cell values. Effective sample size is the number of climate units
  (2 for IL, 2 for IA, 3 for NE), not 10 fields.
- **CDL:** 30 m annual classification with mixed pixels and class error;
  0-3 % of each field-year is unclassified. "Other" is a heterogeneous bucket
  (alfalfa, forest, grass/pasture, fallow/idle, winter wheat).
- **Irrigation:** there is no per-field irrigation data. Do not attribute
  differences in crop mix or climate to irrigation.
- No soil analysis is included.

## Validation

The script fails fast on: field count != 10, missing weather days, NaN or
`-999` weather values, fields in a unit with non-identical series, CDL years
without 10 fields, zero classified pixels, transition denominators != 40, or
composition totals away from 100 by more than 0.05 pp. It writes
`run_manifest.json` with input SHA-256 values, row/field counts, parameters,
software versions and the check results.

Run the repository validator after documentation changes:

```bash
cd /home/coder/work/mfask-worktree/assignment-2
./scripts/validate.sh
```
