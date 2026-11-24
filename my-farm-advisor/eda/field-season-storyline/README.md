# Field-season weather and NDVI storylines

The five [dashboard images](figures/) cover Story County field ia-r1, April 1 through September 30 of 2021–2025. The [2024 corn dashboard](figures/ia-r1-2024.png) is the prototype. The six satellite dates in that season are plotted individually. The 50-day interval from June 9 to July 29 limits when we can locate the increase in greenness.

## Reproduce the figures

From the assignment-3 checkout on Coder, run the following command. Point D to the existing data-pipeline directory on other systems. Add --year 2024 for a single image.

~~~bash
D="$HOME/my-farm-advisor-runtime-a2/data-pipeline"
"$D/.venv/bin/python" my-farm-advisor/eda/field-season-storyline/storyline.py \
  --pipeline "$D" --grower ia-story-grower --farm story-demo-farm --field ia-r1
~~~

Output relative to data-pipeline is growers/<grower>/farms/<farm>/fields/<field>/derived/field-season-storyline/<field>-<year>.png. The figures directory contains the five reviewed submission copies. Runtime dependencies are pandas, NumPy, Rasterio and Matplotlib.

## Read the four panels

- **Vegetation.** The field boundary GeoJSON and satellite/sentinel/manifest.json select the parcel, scene date, NDVI GeoTIFF and Sentinel classification layer. Nearest-neighbor alignment preserves SCL labels. The statistic is the median of finite NDVI in [-1, 1] within the polygon, retaining vegetation and bare-soil pixels (SCL 4 and 5). Each dot represents one usable acquisition. Clouds and the sampling interval affect the observed maximum. The dotted line aligns this date across all four panels.
- **Rain.** Daily PRECTOTCORR in mm from the field's weather/daily_weather.csv, with the wettest day and seasonal sum.
- **Temperature.** Daily NASA POWER T2M_MIN and T2M_MAX in degrees Celsius, with the hottest day and count of days reaching 30 °C. Weather represents the model grid containing the field.
- **Accumulated heat.** Sum of max(0, (Tmax + Tmin)/2 − 10 °C), starting April 1. This uses the pipeline's uncapped mean method for consistent seasonal comparisons. The fixed window is independent of actual planting dates.

The crop is the largest classified category by area in the farm's annual derived/tables/*_<year>_cdl.csv. The displayed percent uses the full mapped field area. The workflow checks for duplicate dates, incomplete daily weather, ambiguous CDL dominance and sparse NDVI. Coincident events provide descriptive context only.
