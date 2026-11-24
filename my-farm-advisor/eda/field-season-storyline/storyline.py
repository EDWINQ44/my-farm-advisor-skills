"""Render one field-season dashboard per requested year from the farm runtime."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom


def field_observations(root, scenes, boundary, days):
    observations = []
    for scene in scenes:
        day = pd.Timestamp(scene["scene_date"])
        if day not in days or scene.get("status") != "complete":
            continue
        with (
            rasterio.open(root / scene["ndvi_tif"]) as ndvi,
            rasterio.open(root / scene["raw_tiffs"]["scl"]) as scl,
        ):
            shapes = [
                transform_geom("OGC:CRS84", ndvi.crs, item["geometry"])
                for item in boundary["features"]
            ]
            inside = geometry_mask(
                shapes, out_shape=ndvi.shape, transform=ndvi.transform, invert=True
            )
            with WarpedVRT(
                scl,
                crs=ndvi.crs,
                transform=ndvi.transform,
                width=ndvi.width,
                height=ndvi.height,
            ) as aligned:
                land = np.isin(aligned.read(1), [4, 5])
            values = ndvi.read(1, masked=True).filled(np.nan)
            valid = inside & land & np.isfinite(values) & (abs(values) <= 1)
            count = int(valid.sum())
            observations.append(
                (
                    day,
                    np.median(values[valid]) if count else np.nan,
                    count,
                    int(inside.sum()),
                )
            )
    frame = (
        pd.DataFrame(observations, columns=["date", "ndvi", "pixels", "field_pixels"])
        .set_index("date")
        .sort_index()
    )
    if frame.index.has_duplicates:
        raise ValueError("Multiple observations per date; inspect the scene manifest")
    return frame


def crop_for_year(farm, field, year):
    paths = list((farm / "derived/tables").glob(f"*_{year}_cdl.csv"))
    if len(paths) != 1:
        raise ValueError(
            f"Expected one annual CDL table for {year}; found {len(paths)}"
        )
    cdl = pd.read_csv(paths[0])
    rows = cdl[(cdl.field_id == field) & (cdl.crop_name != "No Data")].dropna(
        subset=["pct"]
    )
    if rows.empty or rows.pct.max() <= 0 or (rows.pct == rows.pct.max()).sum() != 1:
        raise ValueError(f"No unique dominant CDL class for {field}, {year}")
    row = rows.loc[rows.pct.idxmax()]
    return row.crop_name, row.pct


def generate(root, field_dir, weather, boundary, entry, out):
    year = int(entry["year"])
    field = field_dir.name
    days = pd.date_range(f"{year}-04-01", f"{year}-09-30")
    crop, share = crop_for_year(field_dir.parents[1], field, year)
    w = weather.reindex(days)
    rain, low, high = w.PRECTOTCORR, w.T2M_MIN, w.T2M_MAX
    if (
        rain.isna().any()
        or low.isna().any()
        or high.isna().any()
        or (rain < 0).any()
        or (low > high).any()
    ):
        raise ValueError(
            f"Incomplete or invalid daily weather for {year}; inspect daily_weather.csv"
        )
    gdd = ((low + high) / 2 - 10).clip(lower=0).cumsum()
    obs = field_observations(root, entry["scenes"], boundary, days)
    points = obs.ndvi.dropna()
    if len(points) < 2:
        raise ValueError(f"Fewer than two usable Sentinel dates in {year}")
    peak, wet, hot = points.idxmax(), rain.idxmax(), high.idxmax()
    span = int(points.index.to_series().diff().dt.days.max())
    fig, ax = plt.subplots(4, 1, figsize=(11.2, 9.3), sharex=True)
    fig.subplots_adjust(left=0.115, right=0.965, top=0.853, bottom=0.10, hspace=0.71)
    fig.suptitle(
        f"{field}   /   {crop}   /   {year}",
        x=0.115,
        y=0.974,
        ha="left",
        fontsize=24,
        weight="bold",
        color="#20332b",
    )
    fig.text(
        0.115,
        0.91,
        f"Apr 1 – Sep 30   •   Dominant CDL class: {share:.1f}% of field area   •   {len(points)} usable Sentinel dates   •   {len(days)} weather days",
        fontsize=11,
    )

    def panel(index, heading, note, units):
        a = ax[index]
        a.set_title(heading, loc="left", fontsize=12, weight="bold", pad=9)
        a.set_title(note, loc="right", fontsize=9, color="#4b5451", pad=9)
        a.set_ylabel(units)
        a.grid(axis="y", color="#dde4df", linewidth=0.7)
        a.set_axisbelow(True)
        a.spines[["top", "right"]].set_visible(False)
        return a

    def fmt(d):
        return d.strftime("%b %d")

    a = panel(
        0,
        "Vegetation · Sentinel-2",
        f"Highest observed {points.max():.3f} on {fmt(peak)}  |  longest interval {span} days",
        "Median NDVI",
    )
    a.scatter(points.index, points, color="#267247", s=40, zorder=3)
    a.set_ylim(min(-0.05, points.min() - 0.05), max(1, points.max() + 0.05))
    a.scatter(
        [peak], [points.max()], facecolors="none", edgecolors="#224936", s=110, zorder=4
    )
    a = panel(
        1,
        "Daily precipitation",
        f"Wettest day {fmt(wet)}: {rain.max():.1f} mm  |  season {rain.sum():,.0f} mm",
        "mm / day",
    )
    a.bar(days, rain, color="#4183ac", width=1)
    a.bar(wet, rain.max(), color="#174a73", width=1.5)
    a = panel(
        2,
        "Daily temperature range",
        f"Hottest day {fmt(hot)}: {high.max():.1f} °C  |  {int((high >= 30).sum())} days ≥30 °C",
        "°C",
    )
    a.fill_between(days, low.to_numpy(), high.to_numpy(), color="#f6dfc7")
    a.plot(days, high, color="#a3441a", lw=1, label="Maximum")
    a.plot(days, low, color="#42748b", lw=1, label="Minimum")
    a.legend(loc="lower right", ncol=2, fontsize=8, frameon=False)
    a.scatter(hot, high.max(), s=23, color="#983512")
    a = panel(
        3,
        "Cumulative growing degree days",
        f"Sep 30 total: {gdd.iloc[-1]:,.0f} °C·d  |  base 10 °C",
        "°C·d",
    )
    a.fill_between(days, 0, gdd.to_numpy(), color="#e1ead8")
    a.plot(days, gdd, color="#597341", lw=2)
    a.set_ylim(bottom=0)
    a.set_xlim(days[0], days[-1])
    a.xaxis.set_major_locator(mdates.MonthLocator())
    a.xaxis.set_major_formatter(mdates.DateFormatter("%b 1"))
    a.tick_params(axis="x", pad=6)
    for a in ax:
        a.axvline(peak, color="#48745e", ls=":", lw=0.85, zorder=1)
    fig.text(
        0.115,
        0.036,
        "Dotted guide: highest observed NDVI. Dots show individual field medians. Weather: NASA POWER grid estimate.",
        fontsize=9,
        color="#4b5451",
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{field}-{year}.png"
    fig.savefig(path, dpi=145, facecolor="white")
    plt.close(fig)
    print(
        f"{year} | {crop} | {len(points)} dates | peak {peak.date()} {points.max():.3f} | wet {wet.date()} {rain.max():.1f} mm | total {rain.sum():.1f} mm | hot {hot.date()} {high.max():.1f} C | GDD {gdd.iloc[-1]:.1f} | {path.name}"
    )
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pipeline", type=Path, required=True, help="Runtime data-pipeline directory"
    )
    parser.add_argument("--grower", required=True)
    parser.add_argument("--farm", required=True)
    parser.add_argument("--field", required=True)
    parser.add_argument(
        "--year",
        type=int,
        action="append",
        help="Repeat to select years; default is all manifest years",
    )
    args = parser.parse_args()
    root = args.pipeline.resolve()
    f = root / "growers" / args.grower / "farms" / args.farm / "fields" / args.field
    manifest = json.loads((f / "satellite/sentinel/manifest.json").read_text())
    boundary = json.loads((f / "boundary/field_boundary.geojson").read_text())
    weather = pd.read_csv(
        f / "weather/daily_weather.csv", parse_dates=["date"], na_values=[-999]
    )
    weather = weather[weather.field_id == args.field].set_index("date").sort_index()
    if weather.index.has_duplicates:
        raise ValueError("Duplicate weather dates for selected field")
    years = {int(e["year"]): e for e in manifest["years"]}
    for year in sorted(set(args.year or years)):
        generate(
            root,
            f,
            weather,
            boundary,
            years[year],
            f / "derived/field-season-storyline",
        )


if __name__ == "__main__":
    main()
