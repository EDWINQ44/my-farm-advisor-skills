# Assignment 2 EDA - review log

Date: 2026-11-14
Runtime: `/home/coder/my-farm-advisor-runtime-a2`
Script: `data-pipeline/src/scripts/eda/eda_farm_comparison.py`
Outputs: `data-pipeline/eda/farm-comparison/`

## Run 1 - validation stop

- Composition totals failed the check because class areas were rounded to two
  decimals before producer aggregation (sums 99.99-100.01).
- Fix: aggregate from unrounded classified hectares, round only for CSV
  output, and allow 0.05 pp tolerance for display rounding.
- Re-run: all 15 producer-years 100.00 +/- 0.01.

## Run 2 - visual review of all seven figures

| Figure | Issue found | Fix | Re-check |
| --- | --- | --- | --- |
| A1 | Caveat text overlapped the lowest Iowa points | Moved caveat below the axes with figure-level text | No overlap; points and box fully visible |
| A2 | No issue | - | Bars match `t_a_field_areas.csv` values |
| B1 | Legend said "1 fields" | Singular/plural label fixed | "1 field" shown for IL-2, NE-2, NE-3 |
| B2 | Legend overlapped the title area; unit written "degC" | Legend moved below axes; unit changed to °C; note separated | Clean legend, no overlap |
| C1 | No issue | - | Stacked shares match composition table; coverage labels visible |
| C2 | `sharey=True` copied Nebraska field labels onto Illinois/Iowa panels | Disabled shared y-axis; each panel now lists its own 10 fields | IL/IA/NE rows correct |
| C2 | Footnote overlapped the legend | Legend moved up, footnote separated | Both readable |
| D | Inset covered fields and north arrow; inset axis labels leaked | Replaced in-panel inset with a state-locator row below each panel; removed axis labels | No overlap, county highlighted |
| D | Adjacent NE fields produced overlapping labels (`r1`/`r4`) | Added deterministic collision-aware label placement with leader lines | Labels separated and readable |

## Data checks at final run

- Fields: 10 per producer; 30 total; all geometries valid; no duplicate or
  overlapping polygons.
- Weather: 1826 dates per producer; 0 NaN; 0 NASA POWER `-999` fill values;
  183 days in every April-September window.
- Climate units: IL 2 (9 + 1 fields), IA 2 (6 + 4 fields), NE 3 (8 + 1 + 1
  fields). Values identical inside each unit by assertion.
- CDL: 5 years x 10 fields per producer; minimum classified share 97.07 %;
  composition totals 99.99-100.01 % after rounding.
- Dominance: minimum top-two gap 11.99 pp (ne-r10, 2025); weak-dominance cells
  0; exact ties 0.
- Transitions: denominator 40 per producer (10 fields x 4 consecutive pairs);
  counts sum to 40.
- Figure/table cross-check: area summary matches field table; climate
  variability matches season table; composition matches dominant and
  transition tables.

## Known limitations left in place (documented, not "fixed")

- Selection bias: top-10 largest corn/soybean fields, 40-300 ha; not a random
  sample; not representative of the county or state.
- NASA POWER cell values are shared by fields; effective climate n is 2/2/3.
- CSB 2023 is a single geometry snapshot, not annual boundaries.
- CDL has 30 m mixed pixels and 0-3 % unclassified area; "Other" is
  heterogeneous.
- No per-field irrigation evidence; no causal attribution.
- No soil, dashboards, interactive maps, or final report assembly.

## External review round - adjustments applied (2026-11-14)

- **Field order (tables + fig C2):** fields are now in natural order
  (r1, r2, ..., r10) instead of lexicographic (r1, r10, r2).
- **A1 caveat:** replaced "Top-10 largest" wording with the real selection:
  original assignment-1 fields retained (r1-r3 for IL, IA; NE from scratch)
  plus a corn/soybean expansion filtered by crop, 40-300 ha area, and county
  containment. No unverified ranking claim.
- **Terminology:** column and text now say **distinct climate units** instead
  of "independent observations" / "independent replicates". Sharing a cell
  means shared data; different cells do not guarantee statistical independence.
- **Resolution check (B1):** verified against NASA POWER metadata: the
  climate units are MERRA-2 grid cells (~0.5 deg lat x 0.625 deg lon), not
  square 0.5-degree cells; radiation comes from the 1-degree SYN1DEG product.
  Figure and docs updated to "MERRA-2 grid cells (~0.5 x 0.625 deg)".
- **Daily valid-data check:** confirmed every April-September unit-year has
  183 days each with valid precipitation and temperature (no NaN, no -999);
  the script now enforces valid values, not just row counts.
- Result verification vs tables: IL 2394.83 ha / 23 of 40 corn-soy transitions;
  IA 1792.21 ha / 33 of 40; NE 2031.41 ha / 23 of 40. All match.
- Clarified in the final report: demo producers, not representative samples;
  boundaries are a CSB 2023 snapshot; irrigation evidence is county-level;
  CDL normalized to classified area; no soil analysis.
