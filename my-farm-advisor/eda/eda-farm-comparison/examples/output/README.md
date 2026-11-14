# eda-farm-comparison example outputs

Static figures and small tables from the Assignment 2 cross-producer EDA
(`scripts/eda/eda_farm_comparison.py`), copied from the canonical Assignment 2
runtime. These are small, committed example assets; the canonical, fully
reproducible outputs and raw data live in the runtime under
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/farm-comparison/`.

## Figures

| File | Content |
| --- | --- |
| `fig_a1_field_area_distribution.png` | Field area distribution per producer (points + IQR box) |
| `fig_a2_field_area_by_field.png` | Field area bars, coloured by CSB 2023 crop |
| `fig_b1_precip_apr_sep_by_unit.png` | Growing-season precipitation by NASA POWER (MERRA-2) climate unit |
| `fig_b2_tmean_apr_sep_selected_fields.png` | Growing-season mean temperature for one field per producer |
| `fig_c1_cdl_composition_by_producer_year.png` | CDL crop composition by producer and year, normalized to classified pixels |
| `fig_c2_cdl_dominant_matrix.png` | Dominant CDL crop per field-year (fields in natural order r1, r2, ..., r10) |
| `fig_d_field_map_three_panels.png` | Real CSB 2023 field boundaries per producer with county + state locator |

## Tables

| File | Content |
| --- | --- |
| `t_a_field_areas.csv` | Field-level areas, CSB 2023 crop and id (natural field order) |
| `t_a_area_summary.csv` | Producer-level area summary |
| `t_b_climate_units.csv` | Which fields share a NASA POWER (MERRA-2) cell |
| `t_b_growing_season.csv` | Unit-year April-September climate summaries |
| `t_b_variability.csv` | Variability across **distinct climate units** per producer-year |
| `t_c_cdl_composition.csv` | Full CDL composition, all classes |
| `t_c_cdl_dominant.csv` | Dominant CDL class per field-year (natural field order) |
| `t_c_cdl_transitions.csv` | Consecutive-year corn/soybean transition counts (denominator 40) |

All figures are under 1 MB each and all tables are small text CSVs, so they are
committed as lightweight example assets without Git LFS.