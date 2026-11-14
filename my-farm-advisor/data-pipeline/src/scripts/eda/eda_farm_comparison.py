#!/usr/bin/env python3
"""Assignment 2 cross-producer EDA: fields, climate, CDL, static map.

Reads the canonical assignment-2 runtime tree and writes seven static figures
and eight small CSV tables plus a run manifest. No soil, no dashboards, no
interactive maps, no final report assembly.

Design rules enforced here:
- NASA POWER values are cell values. Fields with identical daily series are
  grouped into one climate unit and never counted as independent replicates.
- Growing-season precipitation is summed per climate unit, never across
  fields. A naive field-level sum would multiply the same cell rainfall.
- CDL percentages are normalized to classified pixels per field-year; the
  unclassified share (NoData / edge pixels) is reported separately and is
  never silently redistributed.
- Producer-level CDL composition is weighted by classified field area.
- Dominance weaker than 10 percentage points is flagged as descriptive only.
- CSB crop labels are the 2023 boundary snapshot, not annual CDL results.

Usage:
  export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime-a2
  cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
    scripts/eda/eda_farm_comparison.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.paths import (  # noqa: E402
    DATA_ROOT,
    farm_boundary_path,
    farm_table_path,
    shared_geoadmin_counties_dir,
    shared_geoadmin_states_dir,
)

CLIMATE_YEARS = (2021, 2025)
CDL_YEARS = (2021, 2025)
GROWING_MONTHS = (4, 5, 6, 7, 8, 9)
EXPECTED_FIELDS = 10
WEAK_DOMINANCE_POINTS = 10.0

CORN = "Corn"
SOY = "Soybeans"
OTHER = "Other"

COLORS = {
    "Corn": "#D9A21B",
    "Soybeans": "#2E7D46",
    "Other": "#8C8C8C",
    "NoData": "#E6E6E6",
    "County": "#4D4D4D",
}


@dataclass(frozen=True)
class Producer:
    key: str
    grower: str
    farm: str
    prefix: str
    title: str
    state_name: str
    state_fips: str
    county_name: str
    county_fips: str


PRODUCERS = (
    Producer(
        key="IL",
        grower="il-dekalb-grower",
        farm="dekalb-demo-farm",
        prefix="dekalb_demo",
        title="Illinois - DeKalb County",
        state_name="Illinois",
        state_fips="17",
        county_name="DeKalb County",
        county_fips="17037",
    ),
    Producer(
        key="IA",
        grower="ia-story-grower",
        farm="story-demo-farm",
        prefix="story_demo",
        title="Iowa - Story County",
        state_name="Iowa",
        state_fips="19",
        county_name="Story County",
        county_fips="19169",
    ),
    Producer(
        key="NE",
        grower="ne-york-grower",
        farm="york-demo-farm",
        prefix="york_demo",
        title="Nebraska - York County",
        state_name="Nebraska",
        state_fips="31",
        county_name="York County",
        county_fips="31185",
    ),
)

PRODUCER_BY_KEY = {p.key: p for p in PRODUCERS}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _save_figure(fig: plt.Figure, path: Path, dpi: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _save_table(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


def load_fields() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    rows = []
    frames = []
    for producer in PRODUCERS:
        boundary = farm_boundary_path(producer.grower, producer.farm)
        gdf = gpd.read_file(boundary)
        if len(gdf) != EXPECTED_FIELDS:
            raise SystemExit(
                f"{producer.key}: expected {EXPECTED_FIELDS} fields, found {len(gdf)} in {boundary}"
            )
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        equal_area = gdf.to_crs("EPSG:5070")
        gdf["area_ha_calc"] = equal_area.area / 10000.0
        gdf["producer"] = producer.key
        gdf["state"] = producer.state_name
        gdf["county"] = producer.county_name
        frames.append(gdf)
    all_fields = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")

    for _, row in all_fields.iterrows():
        rows.append(
            {
                "producer": row["producer"],
                "state": row["state"],
                "county": row["county"],
                "field_id": row["field_id"],
                "area_ha": round(float(row["area_ha_calc"]), 2),
                "area_acres": round(float(row["area_ha_calc"]) * 2.4710538, 1),
                "csb_crop_2023": row.get("crop", ""),
                "csb_id": str(row.get("csb_id", "")),
                "geometry_valid": bool(row.geometry.is_valid),
                "source": row.get("source", ""),
            }
        )
    field_table = pd.DataFrame(rows).sort_values(["producer", "field_id"]).reset_index(drop=True)
    return all_fields, field_table


def area_summary(field_table: pd.DataFrame) -> pd.DataFrame:
    out = []
    for producer in PRODUCERS:
        sub = field_table[field_table["producer"] == producer.key]
        area = sub["area_ha"]
        out.append(
            {
                "producer": producer.key,
                "farm": producer.farm,
                "county": producer.county_name,
                "n_fields": int(len(sub)),
                "total_ha": round(float(area.sum()), 1),
                "total_acres": round(float(sub["area_acres"].sum()), 1),
                "mean_ha": round(float(area.mean()), 1),
                "median_ha": round(float(area.median()), 1),
                "min_ha": round(float(area.min()), 1),
                "max_ha": round(float(area.max()), 1),
                "range_ha": round(float(area.max() - area.min()), 1),
                "iqr_ha": round(float(area.quantile(0.75) - area.quantile(0.25)), 1),
            }
        )
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Climate
# ---------------------------------------------------------------------------


def load_weather(producer: Producer) -> pd.DataFrame:
    path = farm_table_path(
        producer.grower, producer.farm, f"{producer.prefix}_weather_2021_2025.csv"
    )
    frame = pd.read_csv(path, parse_dates=["date"])
    expected_days = (CLIMATE_YEARS[1] - CLIMATE_YEARS[0] + 1) * 365 + 1  # includes 2024-02-29
    if frame["field_id"].nunique() != EXPECTED_FIELDS:
        raise SystemExit(f"{producer.key}: weather file does not cover 10 fields: {path}")
    days = frame["date"].nunique()
    if days != expected_days:
        raise SystemExit(f"{producer.key}: expected {expected_days} dates, found {days}")
    variables = [
        "T2M",
        "T2M_MAX",
        "T2M_MIN",
        "PRECTOTCORR",
        "ALLSKY_SFC_SW_DWN",
        "RH2M",
        "WS10M",
    ]
    if frame[variables].isna().any().any():
        raise SystemExit(f"{producer.key}: weather file contains NaN values")
    if (frame[variables] <= -989).any().any():
        raise SystemExit(f"{producer.key}: weather file contains NASA POWER fill values")
    frame["producer"] = producer.key
    return frame


def assign_climate_units(weather: pd.DataFrame, producer: Producer) -> pd.DataFrame:
    """Group fields whose daily T2M series are identical into climate units."""
    wide = weather.pivot(index="date", columns="field_id", values="T2M").sort_index()
    signatures: dict[tuple, list[str]] = {}
    for column in wide.columns:
        signature = tuple(np.round(wide[column].to_numpy(dtype=float), 4))
        signatures.setdefault(signature, []).append(column)
    ordered = sorted(signatures.values(), key=lambda names: (-len(names), names[0]))
    unit_of: dict[str, str] = {}
    for index, names in enumerate(ordered, start=1):
        unit = f"{producer.key}-{index}"
        for name in names:
            unit_of[name] = unit
    weather = weather.copy()
    weather["climate_unit"] = weather["field_id"].map(unit_of)

    # Guard: fields in the same unit must share every climate series.
    for unit, group in weather.groupby("climate_unit"):
        for variable in ("T2M", "PRECTOTCORR", "T2M_MAX", "T2M_MIN"):
            pivot = group.pivot(index="date", columns="field_id", values=variable)
            if pivot.round(4).nunique(axis=1).max() != 1:
                raise SystemExit(f"{producer.key}/{unit}: fields do not share {variable}")
    return weather


def growing_season(weather: pd.DataFrame) -> pd.DataFrame:
    deduped = weather.drop_duplicates(["climate_unit", "date"]).copy()
    season = deduped[deduped["date"].dt.month.isin(GROWING_MONTHS)].copy()
    season["year"] = season["date"].dt.year
    counts = (
        weather.drop_duplicates(["climate_unit", "field_id"])
        .groupby("climate_unit")["field_id"]
        .nunique()
        .rename("n_fields_in_unit")
    )
    grouped = (
        season.groupby(["producer", "climate_unit", "year"])
        .agg(
            days=("date", "nunique"),
            precip_mm=("PRECTOTCORR", "sum"),
            tmean_c=("T2M", "mean"),
        )
        .reset_index()
    )
    grouped = grouped.merge(
        counts.reset_index(), on="climate_unit", how="left", validate="many_to_one"
    )
    grouped["precip_mm"] = grouped["precip_mm"].round(1)
    grouped["tmean_c"] = grouped["tmean_c"].round(2)
    return grouped.sort_values(["producer", "climate_unit", "year"]).reset_index(drop=True)


def climate_variability(season: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for producer in PRODUCERS:
        for year in range(CDL_YEARS[0], CDL_YEARS[1] + 1):
            sub = season[(season["producer"] == producer.key) & (season["year"] == year)]
            unit_count = sub["climate_unit"].nunique()
            field_count = int(
                units[units["producer"] == producer.key]["field_id"].nunique()
            )
            rows.append(
                {
                    "producer": producer.key,
                    "year": year,
                    "n_fields": field_count,
                    "n_climate_units": int(unit_count),
                    "precip_min_mm": round(float(sub["precip_mm"].min()), 1),
                    "precip_max_mm": round(float(sub["precip_mm"].max()), 1),
                    "precip_range_mm": round(
                        float(sub["precip_mm"].max() - sub["precip_mm"].min()), 1
                    ),
                    "tmean_min_c": round(float(sub["tmean_c"].min()), 2),
                    "tmean_max_c": round(float(sub["tmean_c"].max()), 2),
                    "tmean_range_c": round(
                        float(sub["tmean_c"].max() - sub["tmean_c"].min()), 2
                    ),
                    "independent_observations": "climate units, not fields",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CDL
# ---------------------------------------------------------------------------


def load_cdl(producer: Producer, field_table: pd.DataFrame) -> pd.DataFrame:
    area_by_field = dict(
        zip(
            field_table.loc[field_table["producer"] == producer.key, "field_id"],
            field_table.loc[field_table["producer"] == producer.key, "area_ha"],
        )
    )
    frames = []
    for year in range(CDL_YEARS[0], CDL_YEARS[1] + 1):
        path = farm_table_path(producer.grower, producer.farm, f"{producer.prefix}_{year}_cdl.csv")
        frame = pd.read_csv(path)
        if frame["field_id"].nunique() != EXPECTED_FIELDS:
            raise SystemExit(f"{producer.key} {year}: CDL table does not cover 10 fields")
        frame["producer"] = producer.key
        frames.append(frame)
    cdl = pd.concat(frames, ignore_index=True)
    cdl = cdl[cdl["crop_name"] != "No Data"].copy()
    cdl["area_ha"] = cdl["field_id"].map(area_by_field)
    if cdl["area_ha"].isna().any():
        raise SystemExit(f"{producer.key}: CDL field missing from boundary table")
    totals = cdl.groupby(["field_id", "year"])["pct"].transform("sum")
    if (totals <= 0).any():
        raise SystemExit(f"{producer.key}: CDL rows with no classified pixels")
    cdl["pct_norm"] = cdl["pct"] / totals * 100.0
    cdl["classified_ha"] = cdl["area_ha"] * totals / 100.0
    cdl["classified_ha_row"] = cdl["area_ha"] * cdl["pct"] / 100.0
    cdl["coverage_pct"] = totals
    cdl["category_group"] = np.where(
        cdl["crop_name"].isin([CORN, SOY]), cdl["crop_name"], OTHER
    )
    return cdl


def composition_tables(cdl: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    denominators = (
        cdl.drop_duplicates(["producer", "field_id", "year"])
        .groupby(["producer", "year"], as_index=False)
        .agg(classified_ha=("classified_ha", "sum"), total_field_ha=("area_ha", "sum"))
    )
    raw = (
        cdl.groupby(["producer", "year", "category_group", "crop_name"], as_index=False)[
            "classified_ha_row"
        ]
        .sum()
        .merge(denominators, on=["producer", "year"], how="left", validate="many_to_one")
    )
    raw["pct_of_classified"] = raw["classified_ha_row"] / raw["classified_ha"] * 100.0
    raw["coverage_pct"] = raw["classified_ha"] / raw["total_field_ha"] * 100.0

    composition = pd.DataFrame(
        {
            "producer": raw["producer"],
            "year": raw["year"].astype(int),
            "category_group": raw["category_group"],
            "crop_name": raw["crop_name"],
            "area_ha": raw["classified_ha_row"].round(2),
            "pct_of_classified": raw["pct_of_classified"].round(2),
            "classified_ha": raw["classified_ha"].round(2),
            "total_field_ha": raw["total_field_ha"].round(2),
            "coverage_pct": raw["coverage_pct"].round(2),
            "nodata_pct": (100.0 - raw["coverage_pct"]).round(2),
            "weighting": "classified field area",
        }
    ).sort_values(["producer", "year", "category_group", "crop_name"])

    grouped_raw = (
        raw.groupby(["producer", "year", "category_group"], as_index=False)[
            "classified_ha_row"
        ]
        .sum()
        .merge(denominators, on=["producer", "year"], how="left", validate="many_to_one")
    )
    grouped_raw["pct_of_classified"] = (
        grouped_raw["classified_ha_row"] / grouped_raw["classified_ha"] * 100.0
    )
    grouped = pd.DataFrame(
        {
            "producer": grouped_raw["producer"],
            "year": grouped_raw["year"].astype(int),
            "category_group": grouped_raw["category_group"],
            "area_ha": grouped_raw["classified_ha_row"].round(2),
            "pct_of_classified": grouped_raw["pct_of_classified"].round(2),
        }
    )
    return composition.reset_index(drop=True), grouped


def dominant_table(cdl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (producer, field_id, year), group in cdl.groupby(["producer", "field_id", "year"]):
        ordered = group.sort_values("pct_norm", ascending=False)
        first = ordered.iloc[0]
        second = ordered.iloc[1] if len(ordered) > 1 else None
        gap = float(first["pct_norm"] - (second["pct_norm"] if second is not None else 0.0))
        rows.append(
            {
                "producer": producer,
                "field_id": field_id,
                "year": int(year),
                "dominant_crop": first["crop_name"],
                "dominant_pct": round(float(first["pct_norm"]), 2),
                "second_crop": "" if second is None else second["crop_name"],
                "second_pct": "" if second is None else round(float(second["pct_norm"]), 2),
                "gap_pct": round(gap, 2),
                "weak_dominance_lt10pp": bool(gap < WEAK_DOMINANCE_POINTS),
                "exact_tie": bool(abs(gap) < 1e-9),
                "coverage_pct": round(float(first["coverage_pct"]), 2),
            }
        )
    return pd.DataFrame(rows).sort_values(["producer", "field_id", "year"]).reset_index(drop=True)


def transition_table(dominant: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for producer in PRODUCERS:
        sub = dominant[dominant["producer"] == producer.key].copy()
        sub["group"] = np.where(sub["dominant_crop"].isin([CORN, SOY]), sub["dominant_crop"], OTHER)
        pairs = []
        for field_id, group in sub.groupby("field_id"):
            group = group.sort_values("year")
            records = list(group.itertuples())
            for left, right in zip(records, records[1:]):
                pairs.append((left.year, right.year, left.group, right.group))
        frame = pd.DataFrame(pairs, columns=["year_from", "year_to", "from_crop", "to_crop"])
        denominator = int(len(frame))
        if denominator != EXPECTED_FIELDS * (CDL_YEARS[1] - CDL_YEARS[0]):
            raise SystemExit(
                f"{producer.key}: expected 40 year-pairs, found {denominator}"
            )
        grid = pd.MultiIndex.from_product(
            [[CORN, SOY, OTHER], [CORN, SOY, OTHER]], names=["from_crop", "to_crop"]
        )
        counts = frame.groupby(["from_crop", "to_crop"]).size()
        for from_crop, to_crop in grid:
            count = int(counts.loc[(from_crop, to_crop)]) if (from_crop, to_crop) in counts.index else 0
            rows.append(
                {
                    "producer": producer.key,
                    "from_crop": from_crop,
                    "to_crop": to_crop,
                    "count": count,
                    "denominator": denominator,
                    "share_pct": round(count / denominator * 100.0, 2),
                    "years_compared": f"{CDL_YEARS[0]}-{CDL_YEARS[1]} consecutive pairs",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def figure_field_distribution(field_table: pd.DataFrame, path: Path, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5.8))
    positions = np.arange(len(PRODUCERS))
    for index, producer in enumerate(PRODUCERS):
        values = (
            field_table.loc[field_table["producer"] == producer.key, "area_ha"]
            .sort_values()
            .to_numpy(dtype=float)
        )
        offsets = np.linspace(-0.16, 0.16, len(values))
        ax.scatter(
            np.full(len(values), index) + offsets,
            values,
            s=46,
            color="#1F4E79",
            edgecolor="white",
            linewidth=0.7,
            zorder=3,
        )
        box = ax.boxplot(
            [values],
            positions=[index],
            widths=0.36,
            showfliers=False,
            patch_artist=True,
            medianprops={"color": "#B03A2E", "linewidth": 2},
        )
        box["boxes"][0].set(facecolor="#D6E4F0", edgecolor="#1F4E79", alpha=0.7)
        for median in box["medians"]:
            median.set_zorder(4)
    ax.set_xticks(positions)
    ax.set_xticklabels([p.title for p in PRODUCERS])
    ax.set_ylabel("Field area (ha)")
    ax.set_title(
        "Field area distribution by producer - 10 fields per producer, individual values shown",
        fontsize=11.5,
        fontweight="bold",
    )
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.text(
        0.5,
        -0.01,
        "Top-10 largest corn/soybean CSB fields per county; 40-300 ha selection cap. "
        "Truncated sample, not representative of the county or state.",
        ha="center",
        va="top",
        fontsize=7.5,
        color="#555555",
    )
    ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color="#1F4E79", label="Field"),
            Patch(facecolor="#D6E4F0", edgecolor="#1F4E79", label="IQR / median"),
        ],
        loc="upper left",
        fontsize=8,
        frameon=False,
    )
    _save_figure(fig, path, dpi)


def figure_field_bars(field_table: pd.DataFrame, path: Path, dpi: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 6.2), sharex=True)
    for ax, producer in zip(axes, PRODUCERS):
        sub = (
            field_table[field_table["producer"] == producer.key]
            .sort_values("area_ha", ascending=True)
            .reset_index(drop=True)
        )
        colors = [
            COLORS["Corn"]
            if crop == "Corn"
            else COLORS["Soybeans"]
            if crop == "Soybeans"
            else COLORS["Other"]
            for crop in sub["csb_crop_2023"]
        ]
        ax.barh(sub["field_id"], sub["area_ha"], color=colors, edgecolor="#333333", linewidth=0.4)
        for y, value in enumerate(sub["area_ha"]):
            ax.text(value + 4, y, f"{value:.0f}", va="center", fontsize=7.5)
        ax.set_title(f"{producer.title}\nTotal {sub['area_ha'].sum():.0f} ha", fontsize=10)
        ax.set_xlabel("Field area (ha)")
        ax.set_xlim(0, 330)
        ax.grid(axis="x", color="#E3E3E3", linewidth=0.8)
        ax.set_axisbelow(True)
    handles = [
        Patch(facecolor=COLORS["Corn"], edgecolor="#333333", label="CSB 2023: Corn"),
        Patch(facecolor=COLORS["Soybeans"], edgecolor="#333333", label="CSB 2023: Soybeans"),
        Patch(facecolor=COLORS["Other"], edgecolor="#333333", label="CSB 2023: Other"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.suptitle(
        "Field area by field, grouped by producer - values in hectares",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    _save_figure(fig, path, dpi)


def figure_precip(season: pd.DataFrame, path: Path, dpi: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16.0, 6.0), sharey=True)
    for ax, producer in zip(axes, PRODUCERS):
        sub = season[season["producer"] == producer.key]
        units = sorted(sub["climate_unit"].unique())
        years = list(range(CLIMATE_YEARS[0], CLIMATE_YEARS[1] + 1))
        width = 0.8 / max(len(units), 1)
        palette = plt.get_cmap("tab10")
        for unit_index, unit in enumerate(units):
            values = []
            for year in years:
                match = sub[(sub["climate_unit"] == unit) & (sub["year"] == year)]
                values.append(float(match["precip_mm"].iloc[0]) if len(match) else np.nan)
            n_fields = int(sub[sub["climate_unit"] == unit]["n_fields_in_unit"].iloc[0])
            ax.bar(
                np.arange(len(years)) + (unit_index - (len(units) - 1) / 2) * width,
                values,
                width=width * 0.92,
                color=palette(unit_index),
                edgecolor="#333333",
                linewidth=0.4,
                label=f"{unit} ({n_fields} field{'s' if n_fields != 1 else ''})",
            )
        ax.set_xticks(np.arange(len(years)))
        ax.set_xticklabels([str(year) for year in years])
        ax.set_title(producer.title, fontsize=10)
        ax.set_xlabel("Year")
        ax.grid(axis="y", color="#E3E3E3", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.legend(title="NASA POWER climate unit", fontsize=7.5, title_fontsize=8, frameon=False)
    axes[0].set_ylabel("Apr-Sep precipitation (mm)")
    fig.suptitle(
        "Growing-season precipitation by NASA POWER climate unit, 2021-2025\n"
        "Bars are climate units (0.5-degree cells), not fields: fields sharing a cell are one value",
        fontsize=11.5,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    _save_figure(fig, path, dpi)


def figure_tmean(season: pd.DataFrame, units: pd.DataFrame, path: Path, dpi: int) -> None:
    selected = []
    for producer in PRODUCERS:
        sub = units[units["producer"] == producer.key].sort_values("area_ha", ascending=False)
        field_id = str(sub["field_id"].iloc[0])
        unit = str(sub[sub["field_id"] == field_id]["climate_unit"].iloc[0])
        selected.append((producer, field_id, unit))
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    palette = {"IL": "#1F4E79", "IA": "#2E7D46", "NE": "#B03A2E"}
    for producer, field_id, unit in selected:
        row = season[(season["producer"] == producer.key) & (season["climate_unit"] == unit)]
        row = row.sort_values("year")
        ax.plot(
            row["year"],
            row["tmean_c"],
            marker="o",
            linewidth=2,
            color=palette[producer.key],
            label=f"{producer.key} {field_id} ({unit}, {producer.county_name})",
        )
        for year, value in zip(row["year"], row["tmean_c"]):
            ax.annotate(
                f"{value:.1f}",
                (year, value),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=7.5,
                color=palette[producer.key],
            )
    ax.set_xticks(range(CLIMATE_YEARS[0], CLIMATE_YEARS[1] + 1))
    ax.set_xlabel("Year")
    ax.set_ylabel("Apr-Sep mean temperature (°C)")
    ax.set_title(
        "Growing-season mean temperature for one identified field per producer, 2021-2025",
        fontsize=11.5,
        fontweight="bold",
    )
    ax.grid(color="#E3E3E3", linewidth=0.8)
    ax.set_axisbelow(True)
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.065),
        ncol=3,
        fontsize=8,
        frameon=False,
    )
    fig.text(
        0.5,
        0.01,
        "NASA POWER cell values; each selected field shares its cell with other fields. "
        "The unit label identifies that shared cell.",
        ha="center",
        va="bottom",
        fontsize=7.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    _save_figure(fig, path, dpi)


def figure_composition(grouped: pd.DataFrame, composition: pd.DataFrame, path: Path, dpi: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16.0, 6.2), sharey=True)
    categories = [CORN, SOY, OTHER]
    for ax, producer in zip(axes, PRODUCERS):
        sub = grouped[grouped["producer"] == producer.key]
        years = list(range(CDL_YEARS[0], CDL_YEARS[1] + 1))
        bottom = np.zeros(len(years))
        for category in categories:
            values = []
            for year in years:
                match = sub[(sub["category_group"] == category) & (sub["year"] == year)]
                values.append(float(match["pct_of_classified"].iloc[0]) if len(match) else 0.0)
            ax.bar(
                np.arange(len(years)),
                values,
                bottom=bottom,
                color=COLORS[category],
                edgecolor="white",
                linewidth=0.6,
                label=category,
                width=0.72,
            )
            for index, value in enumerate(values):
                if value >= 6:
                    ax.text(
                        index,
                        bottom[index] + value / 2,
                        f"{value:.0f}%",
                        ha="center",
                        va="center",
                        fontsize=7.5,
                        color="black",
                    )
            bottom += np.array(values)
        coverage = (
            composition[composition["producer"] == producer.key]
            .groupby("year")["coverage_pct"]
            .first()
        )
        for index, year in enumerate(years):
            ax.text(
                index,
                -4,
                f"cover {coverage.get(year, float('nan')):.1f}%",
                ha="center",
                va="top",
                fontsize=7,
                color="#555555",
            )
        ax.set_xticks(np.arange(len(years)))
        ax.set_xticklabels([str(year) for year in years])
        ax.set_ylim(-8, 100)
        ax.set_title(producer.title, fontsize=10)
        ax.set_xlabel("CDL year")
        ax.grid(axis="y", color="#E3E3E3", linewidth=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Share of classified field area (%)")
    handles = [Patch(facecolor=COLORS[c], label=c) for c in categories]
    handles.append(Patch(facecolor="white", edgecolor="white", label="Cover = classified / field area; NoData excluded and reported"))
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=8)
    fig.suptitle(
        "CDL crop composition by producer and year, 2021-2025 - area-weighted, normalized to classified pixels\n"
        "Other groups Alfalfa, Forest, Grass/Pasture, Fallow/Idle and Winter Wheat",
        fontsize=11.5,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.90))
    _save_figure(fig, path, dpi)


def figure_dominant_matrix(dominant: pd.DataFrame, path: Path, dpi: int) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16.0, 7.2), sharey=False)
    for ax, producer in zip(axes, PRODUCERS):
        sub = dominant[dominant["producer"] == producer.key]
        fields = sorted(sub["field_id"].unique(), reverse=True)
        years = list(range(CDL_YEARS[0], CDL_YEARS[1] + 1))
        indexed = sub.set_index(["field_id", "year"])
        for row_index, field_id in enumerate(fields):
            for col_index, year in enumerate(years):
                if (field_id, year) not in indexed.index:
                    ax.add_patch(
                        plt.Rectangle((col_index - 0.5, row_index - 0.5), 1, 1, color=COLORS["NoData"])
                    )
                    continue
                record = indexed.loc[(field_id, year)]
                group = CORN if record["dominant_crop"] == CORN else SOY if record["dominant_crop"] == SOY else OTHER
                ax.add_patch(
                    plt.Rectangle(
                        (col_index - 0.5, row_index - 0.5),
                        1,
                        1,
                        facecolor=COLORS[group],
                        edgecolor="white",
                        linewidth=1.2,
                    )
                )
                suffix = "*" if record["weak_dominance_lt10pp"] else ""
                if record["exact_tie"]:
                    suffix = "="
                ax.text(
                    col_index,
                    row_index,
                    f"{record['dominant_pct']:.0f}{suffix}",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color="white" if group != OTHER else "black",
                )
        ax.set_xlim(-0.5, len(years) - 0.5)
        ax.set_ylim(-0.5, len(fields) - 0.5)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels([str(year) for year in years])
        ax.set_yticks(range(len(fields)))
        ax.set_yticklabels(fields, fontsize=8)
        ax.set_title(producer.title, fontsize=10)
        ax.set_xlabel("CDL year")
    axes[0].set_ylabel("Field")
    handles = [
        Patch(facecolor=COLORS[CORN], label="Corn"),
        Patch(facecolor=COLORS[SOY], label="Soybeans"),
        Patch(facecolor=COLORS[OTHER], label="Other"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.055),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    fig.suptitle(
        "CDL dominant crop by field and year - cell text is dominant class share (% of classified pixels)\n"
        "* weak dominance: top-two gap < 10 percentage points (descriptive, not statistical uncertainty); = exact tie",
        fontsize=11,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.005,
        f"Minimum top-two gap in this dataset: {dominant['gap_pct'].min():.1f} pp; "
        f"weak-dominance cells: {int(dominant['weak_dominance_lt10pp'].sum())}; "
        f"exact ties: {int(dominant['exact_tie'].sum())}.",
        ha="center",
        va="bottom",
        fontsize=7.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.10, 1, 0.90))
    _save_figure(fig, path, dpi)


def _utm_epsg(lon: float, lat: float) -> str:
    zone = int((lon + 180) / 6) + 1
    return f"EPSG:{32600 + zone}" if lat >= 0 else f"EPSG:{32700 + zone}"


def _north_arrow(ax) -> None:
    ax.annotate(
        "N",
        xy=(0.94, 0.94),
        xytext=(0.94, 0.82),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        arrowprops={"facecolor": "black", "width": 1.4, "headwidth": 7, "headlength": 8},
    )


def _scale_bar(ax, minx: float, miny: float, width: float, height: float) -> None:
    candidates = [1, 2, 5, 10, 20, 50, 100]
    length_km = candidates[0]
    for candidate in candidates:
        if candidate * 1000 <= width * 0.30:
            length_km = candidate
    length = length_km * 1000
    x0 = minx + width * 0.05
    y0 = miny + height * 0.06
    ax.plot([x0, x0 + length], [y0, y0], color="black", linewidth=2.2, solid_capstyle="butt", zorder=9)
    for offset in (0, length):
        ax.plot([x0 + offset, x0 + offset], [y0 - height * 0.012, y0 + height * 0.012], color="black", linewidth=1.4, zorder=9)
    ax.text(
        x0 + length / 2,
        y0 + height * 0.02,
        f"{length_km} km",
        ha="center",
        va="bottom",
        fontsize=8,
        zorder=9,
        path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
    )


def figure_map(
    all_fields: gpd.GeoDataFrame,
    counties: gpd.GeoDataFrame,
    states: gpd.GeoDataFrame,
    path: Path,
    dpi: int,
) -> None:
    fig = plt.figure(figsize=(20.0, 9.6))
    grid = fig.add_gridspec(
        2, 3, height_ratios=(4.3, 1.05), hspace=0.16, wspace=0.06
    )
    for column, producer in enumerate(PRODUCERS):
        ax = fig.add_subplot(grid[0, column])
        locator = fig.add_subplot(grid[1, column])
        fields = all_fields[all_fields["producer"] == producer.key].copy()
        county = counties[counties["fips"] == producer.county_fips].copy()
        state = states[states["state_fips"] == producer.state_fips].copy()
        bounds_wgs = fields.to_crs(4326).total_bounds
        epsg = _utm_epsg(
            (bounds_wgs[0] + bounds_wgs[2]) / 2.0,
            (bounds_wgs[1] + bounds_wgs[3]) / 2.0,
        )
        county_utm = county.to_crs(epsg)
        fields_utm = fields.to_crs(epsg)
        state_utm = state.to_crs(epsg)

        county_utm.plot(ax=ax, facecolor="#F4F1EA", edgecolor=COLORS["County"], linewidth=1.3, zorder=1)
        for crop, color in ((CORN, COLORS["Corn"]), (SOY, COLORS["Soybeans"]), (OTHER, COLORS["Other"])):
            sub = fields_utm[fields_utm["crop"] == crop]
            if not sub.empty:
                sub.plot(ax=ax, facecolor=color, edgecolor="#222222", linewidth=0.6, alpha=0.9, zorder=3)
        points = [(row.geometry.representative_point(), row["field_id"]) for _, row in fields_utm.iterrows()]
        span = max(fields_utm.total_bounds[2] - fields_utm.total_bounds[0], fields_utm.total_bounds[3] - fields_utm.total_bounds[1])
        step = min(max(span * 0.045, 600.0), 2500.0)
        candidates = [
            (0, 1), (1, 0), (-1, 0), (0, -1),
            (1, 1), (-1, 1), (1, -1), (-1, -1),
        ]
        placed: list[tuple[float, float]] = []
        for point, field_id in points:
            best = None
            for dx, dy in candidates:
                candidate = (point.x + dx * step, point.y + dy * step)
                if placed and min(
                    ((candidate[0] - px) ** 2 + (candidate[1] - py) ** 2) ** 0.5 for px, py in placed
                ) < step * 1.25:
                    continue
                if min(
                    ((candidate[0] - other.x) ** 2 + (candidate[1] - other.y) ** 2) ** 0.5
                    for other, other_id in points
                    if other_id != field_id
                ) < step * 0.55:
                    continue
                best = candidate
                break
            if best is None:
                best = (point.x, point.y + step)
            placed.append(best)
            if abs(best[0] - point.x) > step * 0.2 or abs(best[1] - point.y) > step * 0.2:
                ax.plot(
                    [point.x, best[0]],
                    [point.y, best[1]],
                    color="black",
                    linewidth=0.35,
                    zorder=4,
                )
            ax.annotate(
                str(field_id).split("-")[-1],
                best,
                ha="center",
                va="center",
                fontsize=7.0,
                color="black",
                path_effects=[pe.withStroke(linewidth=2.6, foreground="white")],
                zorder=6,
            )

        minx, miny, maxx, maxy = fields_utm.total_bounds
        pad_x = (maxx - minx) * 0.08
        pad_y = (maxy - miny) * 0.08
        ax.set_xlim(minx - pad_x, maxx + pad_x)
        ax.set_ylim(miny - pad_y, maxy + pad_y)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_title(
            f"{producer.title}\n10 fields, {fields['area_ha_calc'].sum():.0f} ha total",
            fontsize=10,
        )

        _scale_bar(ax, minx - pad_x, miny - pad_y, (maxx - minx) + 2 * pad_x, (maxy - miny) + 2 * pad_y)
        _north_arrow(ax)

        state_utm.plot(ax=locator, facecolor="#E8E8E8", edgecolor="#999999", linewidth=0.5)
        county_utm.plot(ax=locator, facecolor="#B03A2E", edgecolor="#B03A2E", linewidth=0.8)
        locator.set_xticks([])
        locator.set_yticks([])
        locator.set_xlabel("")
        locator.set_ylabel("")
        locator.set_aspect("equal")
        locator.set_title(f"{producer.state_name}: county in red", fontsize=7, pad=2)
        for spine in locator.spines.values():
            spine.set_linewidth(0.6)

    handles = [
        Patch(facecolor=COLORS[CORN], edgecolor="#222222", label="CSB 2023 crop: Corn"),
        Patch(facecolor=COLORS[SOY], edgecolor="#222222", label="CSB 2023 crop: Soybeans"),
        Patch(facecolor=COLORS[OTHER], edgecolor="#222222", label="CSB 2023 crop: Other"),
        Patch(facecolor="#F4F1EA", edgecolor=COLORS["County"], label="County boundary (TIGER 2025)"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.06),
        ncol=4,
        frameon=False,
        fontsize=9,
    )
    fig.text(
        0.5,
        0.008,
        "Panel labels are field suffixes (rN); full IDs and areas are in t_a_field_areas.csv. "
        "Boundaries are a 2023 CSB snapshot, not cadastral or historical limits.",
        ha="center",
        va="bottom",
        fontsize=7.5,
        color="#555555",
    )
    fig.suptitle(
        "Real field boundaries for the three assignment-2 demo producers (USDA CSB 2023 snapshot)\n"
        "Local UTM projection per panel; county background and state locator are offline geoadmin layers",
        fontsize=11.5,
        fontweight="bold",
    )
    fig.subplots_adjust(left=0.02, right=0.98, top=0.88, bottom=0.14, hspace=0.18, wspace=0.06)
    _save_figure(fig, path, dpi)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-root",
        default=str(DATA_ROOT / "eda" / "farm-comparison"),
        help="Output root (default: ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/farm-comparison)",
    )
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--years-start", type=int, default=2021)
    parser.add_argument("--years-end", type=int, default=2025)
    args = parser.parse_args(argv)

    if not os.environ.get("DATA_PIPELINE_DATA_ROOT"):
        raise SystemExit("DATA_PIPELINE_DATA_ROOT is required")
    if (args.years_start, args.years_end) != (CLIMATE_YEARS[0], CLIMATE_YEARS[1]):
        raise SystemExit(
            f"This analysis is defined for {CLIMATE_YEARS[0]}-{CLIMATE_YEARS[1]}; "
            "update the script constants and caveats before changing the window."
        )

    out_root = Path(args.out_root).expanduser().resolve()
    runtime_root = DATA_ROOT.resolve()
    if runtime_root not in out_root.parents and out_root != runtime_root:
        raise SystemExit(f"Output root must stay under the runtime root: {runtime_root}")
    fig_dir = out_root / "figures"
    table_dir = out_root / "tables"
    manifest_dir = out_root / "manifests"
    for directory in (fig_dir, table_dir, manifest_dir):
        directory.mkdir(parents=True, exist_ok=True)

    print(f"[eda] runtime root: {runtime_root}")
    print(f"[eda] output root:  {out_root}")

    all_fields, field_table = load_fields()
    summary = area_summary(field_table)
    _save_table(field_table, table_dir / "t_a_field_areas.csv")
    _save_table(summary, table_dir / "t_a_area_summary.csv")

    weather_frames = []
    unit_frames = []
    season_frames = []
    for producer in PRODUCERS:
        weather = assign_climate_units(load_weather(producer), producer)
        weather_frames.append(weather)
        units = (
            weather.drop_duplicates(["field_id"])
            .merge(
                field_table[["field_id", "area_ha"]],
                on="field_id",
                how="left",
                validate="one_to_one",
            )
            .assign(
                producer=producer.key,
                state=producer.state_name,
                county=producer.county_name,
            )
        )
        counts = units.groupby("climate_unit")["field_id"].nunique()
        units["n_fields_in_unit"] = units["climate_unit"].map(counts)
        units["is_largest_field"] = units["field_id"] == (
            units.sort_values("area_ha", ascending=False)["field_id"].iloc[0]
        )
        unit_frames.append(units[["producer", "state", "county", "climate_unit", "field_id", "area_ha", "n_fields_in_unit", "is_largest_field"]])
        season_frames.append(growing_season(weather))
    units_table = pd.concat(unit_frames, ignore_index=True).sort_values(
        ["producer", "climate_unit", "area_ha"], ascending=[True, True, False]
    )
    season = pd.concat(season_frames, ignore_index=True)
    variability = climate_variability(season, units_table)
    _save_table(units_table, table_dir / "t_b_climate_units.csv")
    _save_table(season, table_dir / "t_b_growing_season.csv")
    _save_table(variability, table_dir / "t_b_variability.csv")

    cdl_frames = []
    for producer in PRODUCERS:
        cdl_frames.append(load_cdl(producer, field_table))
    cdl = pd.concat(cdl_frames, ignore_index=True)
    composition, grouped = composition_tables(cdl)
    dominant = dominant_table(cdl)
    transitions = transition_table(dominant)
    _save_table(composition, table_dir / "t_c_cdl_composition.csv")
    _save_table(dominant, table_dir / "t_c_cdl_dominant.csv")
    _save_table(transitions, table_dir / "t_c_cdl_transitions.csv")

    counties = gpd.read_file(shared_geoadmin_counties_dir() / "counties_usa.geojson")
    states = gpd.read_file(shared_geoadmin_states_dir() / "states_usa.geojson")

    figure_field_distribution(field_table, fig_dir / "fig_a1_field_area_distribution.png", args.dpi)
    figure_field_bars(field_table, fig_dir / "fig_a2_field_area_by_field.png", args.dpi)
    figure_precip(season, fig_dir / "fig_b1_precip_apr_sep_by_unit.png", args.dpi)
    figure_tmean(season, units_table, fig_dir / "fig_b2_tmean_apr_sep_selected_fields.png", args.dpi)
    figure_composition(grouped, composition, fig_dir / "fig_c1_cdl_composition_by_producer_year.png", args.dpi)
    figure_dominant_matrix(dominant, fig_dir / "fig_c2_cdl_dominant_matrix.png", args.dpi)
    figure_map(all_fields, counties, states, fig_dir / "fig_d_field_map_three_panels.png", args.dpi)

    checks = {
        "fields_per_producer": {p.key: int((field_table["producer"] == p.key).sum()) for p in PRODUCERS},
        "fields_expected": EXPECTED_FIELDS,
        "weather_days": int(weather_frames[0]["date"].nunique()),
        "climate_units": {
            p.key: int(units_table[units_table["producer"] == p.key]["climate_unit"].nunique())
            for p in PRODUCERS
        },
        "fields_per_climate_unit": {
            f"{row['producer']}/{row['climate_unit']}": int(row["n_fields_in_unit"])
            for _, row in units_table.drop_duplicates(["producer", "climate_unit"]).iterrows()
        },
        "cdl_years": sorted(int(v) for v in cdl["year"].unique()),
        "cdl_fields_per_year": {
            f"{producer}/{year}": int(
                cdl[(cdl["producer"] == producer) & (cdl["year"] == year)]["field_id"].nunique()
            )
            for producer in [p.key for p in PRODUCERS]
            for year in range(CDL_YEARS[0], CDL_YEARS[1] + 1)
        },
        "min_classified_share_pct": round(
            float(cdl.drop_duplicates(["producer", "field_id", "year"])["coverage_pct"].min()), 2
        ),
        "transition_denominators": {
            p.key: int(
                transitions.loc[transitions["producer"] == p.key, "denominator"].iloc[0]
            )
            for p in PRODUCERS
        },
        "weak_dominance_cells": int(dominant["weak_dominance_lt10pp"].sum()),
        "exact_tie_cells": int(dominant["exact_tie"].sum()),
        "composition_totals_pct": {
            f"{producer}/{year}": round(float(group["pct_of_classified"].sum()), 2)
            for (producer, year), group in grouped.groupby(["producer", "year"])
        },
    }
    expected_weather_days = (CLIMATE_YEARS[1] - CLIMATE_YEARS[0] + 1) * 365 + 1
    failures = []
    if any(value != EXPECTED_FIELDS for value in checks["fields_per_producer"].values()):
        failures.append("field count")
    if checks["weather_days"] != expected_weather_days:
        failures.append("weather day count")
    if any(value != EXPECTED_FIELDS * (CDL_YEARS[1] - CDL_YEARS[0]) for value in checks["transition_denominators"].values()):
        failures.append("transition denominator")
    if any(abs(value - 100.0) > 0.05 for value in checks["composition_totals_pct"].values()):
        failures.append("composition totals")
    if any(value != EXPECTED_FIELDS for value in checks["cdl_fields_per_year"].values()):
        failures.append("cdl field coverage")
    if failures:
        raise SystemExit(f"EDA validation failed: {', '.join(failures)}")

    inputs = []
    for producer in PRODUCERS:
        paths = [
            farm_boundary_path(producer.grower, producer.farm),
            farm_table_path(producer.grower, producer.farm, f"{producer.prefix}_weather_2021_2025.csv"),
        ] + [
            farm_table_path(producer.grower, producer.farm, f"{producer.prefix}_{year}_cdl.csv")
            for year in range(CDL_YEARS[0], CDL_YEARS[1] + 1)
        ]
        for path in paths:
            inputs.append(
                {
                    "path": str(path),
                    "sha256": _sha256(path),
                    "bytes": path.stat().st_size,
                }
            )

    manifest = {
        "analysis": "assignment-2 cross-producer EDA",
        "script": str(Path(__file__).resolve()),
        "script_sha256": _sha256(Path(__file__).resolve()),
        "runtime_root": str(runtime_root),
        "output_root": str(out_root),
        "years": {"climate": list(CLIMATE_YEARS), "cdl": list(CDL_YEARS)},
        "parameters": {"dpi": args.dpi, "growing_months": list(GROWING_MONTHS)},
        "producers": [p.__dict__ for p in PRODUCERS],
        "checks": checks,
        "inputs": inputs,
        "software": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "geopandas": gpd.__version__,
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "notes": [
            "Fields sharing identical NASA POWER daily series are one climate unit; they are not independent observations.",
            "Growing-season precipitation is summed per climate unit, never across fields.",
            "CDL shares are normalized to classified pixels; coverage and NoData are reported separately and never redistributed.",
            "CSB crop labels are the 2023 boundary snapshot, not annual CDL results.",
            "Weak dominance is descriptive (<10 percentage-point top-two gap), not statistical uncertainty.",
            "Demo field selection is top-10 corn/soybean fields by area; it is not representative of the county or state.",
        ],
    }
    (manifest_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print("[eda] checks:", json.dumps(checks, indent=2))
    print(f"[eda] figures: {len(list(fig_dir.glob('*.png')))} -> {fig_dir}")
    print(f"[eda] tables:  {len(list(table_dir.glob('*.csv')))} -> {table_dir}")
    print(f"[eda] manifest: {manifest_dir / 'run_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
