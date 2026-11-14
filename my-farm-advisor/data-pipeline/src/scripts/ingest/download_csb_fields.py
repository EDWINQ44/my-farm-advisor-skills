"""Ingest real farm-field polygons from USDA CSB via FIBOA's hosted GeoParquet.

Reads the FIBOA "us-usda-cropland" collection (16.19M field polygons, derived
from USDA NASS Crop Sequence Boundaries) hosted on Source Cooperative and
extracts the largest fields inside a lon/lat window WITHOUT downloading the
whole file: row-group statistics on the flattened bbox columns prune the scan
(648 row groups), then only candidate groups are read.

The parquet stores geometry + bbox in the file's projected CRS (NAD83 Albers
Conic Equal Area, read live from the GeoParquet key/value metadata). The
window is transformed degrees -> file CRS with pyproj before pruning, which
is required: comparing degrees against meters silently matches nothing.

Why pyarrow and not DuckDB: this file dictionary-encodes the bbox struct,
which triggers a DuckDB filter-pushdown internal error (Vector::Reference
type mismatch). Row-group stats via pyarrow avoid the bug and are explicit.

OSM license note: FIBOA collection CC-BY-4.0; underlying CSB is USDA public
data. Provenance (URL, row groups touched, accessed_at) is journalled.

The FIBOA snapshot is a single CSB vintage (USDA NationalCSB_2016-2023_rev23,
adjacent polygons dissolved by their 2023 crop). It is not a per-year boundary
history; the `year` boundary property is intentionally left empty.

Usage:
  export DATA_PIPELINE_DATA_ROOT=... AG_GROWER_SLUG=... AG_FARM_SLUG=...
  python download_csb_fields.py --bbox S W N E --min-area-ha 40 \
      --field-prefix ia-r --max-fields 3

Expanding an existing farm without replacing its fields:
  python download_csb_fields.py --bbox S W N E --field-prefix ia-r \
      --field-start-index 4 --max-fields 7 --skip-existing \
      --county-fips 19169 --state-fips 19 --crop-names Corn,Soybeans \
      --max-area-ha 300 --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from paths import DATA_ROOT, shared_geoadmin_counties_dir  # pyright: ignore[reportMissingImports]

import fsspec  # pyright: ignore[reportMissingImports]
import geopandas as gpd  # pyright: ignore[reportMissingImports]
import pandas as pd  # pyright: ignore[reportMissingImports]
import pyarrow.parquet as pq  # pyright: ignore[reportMissingImports]
from pyproj import CRS, Transformer
from shapely import wkb  # pyright: ignore[reportMissingImports]

URL = "https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet"
# Physical leaf columns for the bbox struct (verified against live stats 2026-11-03)
LEAF = {"bbox.xmin": 7, "bbox.ymin": 8, "bbox.xmax": 9, "bbox.ymax": 10}
CSB_SNAPSHOT = {
    "dataset": "USDA NASS Crop Sequence Boundaries (CSB), FIBOA GeoParquet",
    "lineage": "NationalCSB_2016-2023_rev23 (downloaded 2024-11-25)",
    "geometry_vintage": 2023,
    "note": (
        "Single snapshot: adjacent polygons dissolved by their 2023 crop. "
        "Not a year-by-year boundary history; crop property is the 2023 crop."
    ),
}


def file_crs(pf: pq.ParquetFile) -> CRS:
    kv = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in pf.metadata.metadata.items()
    }
    geo = json.loads(kv["geo"])
    return CRS.from_json_dict(geo["columns"]["geometry"]["crs"])


def _crop_filter(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _county_geometry(county_fips: str, crs: CRS):
    path = shared_geoadmin_counties_dir() / "counties_usa.geojson"
    counties = gpd.read_file(path)
    target = counties[counties["fips"].astype(str).str.zfill(5) == county_fips.zfill(5)]
    if target.empty:
        sys.exit(f"county fips not found in {path}: {county_fips}")
    return target.to_crs(crs).geometry.iloc[0]


def _existing_fields(farm_bounds: Path, crs: CRS, field_start_index: int):
    """Existing fields to protect: only slugs numbered below the new start index."""
    if not farm_bounds.exists():
        return set(), None
    old = gpd.read_file(farm_bounds)
    if "field_id" in old.columns:
        keep = old[
            old["field_id"]
            .astype(str)
            .str.extract(r"(\d+)$")[0]
            .astype(float)
            .lt(field_start_index)
            .fillna(False)
        ]
    else:
        keep = old.iloc[0:0]
    ids = set(keep["csb_id"].astype(str)) if "csb_id" in keep.columns else set()
    geom = keep.to_crs(crs).geometry.union_all() if not keep.empty else None
    return ids, geom


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Real US field boundaries from USDA CSB (FIBOA geoparquet).")
    ap.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("S", "W", "N", "E"))
    ap.add_argument("--min-area-ha", type=float, default=40.0)
    ap.add_argument(
        "--max-area-ha",
        type=float,
        default=0.0,
        help="Optional upper area bound in hectares; 0 or less disables the cap.",
    )
    ap.add_argument("--max-fields", type=int, default=3)
    ap.add_argument(
        "--field-start-index",
        type=int,
        default=1,
        help="First numeric suffix used for new field slugs (default 1).",
    )
    ap.add_argument("--field-prefix", required=True)
    ap.add_argument("--country", default="US")
    ap.add_argument("--state", default="")
    ap.add_argument(
        "--state-fips",
        default="",
        help="Two-digit state FIPS written onto each boundary (e.g. 31 for Nebraska).",
    )
    ap.add_argument(
        "--county-fips",
        default="",
        help="Five-digit county FIPS; candidate polygons must lie inside this county.",
    )
    ap.add_argument(
        "--crop-names",
        default="",
        help="Comma-separated crop names to keep (case-insensitive), e.g. Corn,Soybeans.",
    )
    ap.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip CSB ids and polygons already present on this farm (append-only expansion).",
    )
    ap.add_argument("--year", default="")
    ap.add_argument("--dry-run", action="store_true", help="List candidates without writing files.")
    args = ap.parse_args(argv)

    grower = os.environ.get("AG_GROWER_SLUG") or sys.exit("AG_GROWER_SLUG required")
    farm = os.environ.get("AG_FARM_SLUG") or sys.exit("AG_FARM_SLUG required")
    farm_dir = DATA_ROOT / "growers" / grower / "farms" / farm
    if not farm_dir.exists():
        sys.exit(f"farm dir missing: {farm_dir} (create farm.json first)")
    if args.field_start_index < 1:
        sys.exit("--field-start-index must be >= 1")
    if args.max_fields < 1:
        sys.exit("--max-fields must be >= 1")

    s, w, n, e = args.bbox
    fo = fsspec.open(URL, block_size=2**26).open()
    pf = pq.ParquetFile(fo)
    crs = file_crs(pf)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x0, y0 = tr.transform(w, s)
    x1, y1 = tr.transform(e, n)
    xmin, xmax = sorted((x0, x1))
    ymin, ymax = sorted((y0, y1))

    county_geom = None
    if args.county_fips:
        county_geom = _county_geometry(args.county_fips, crs)

    sel = []
    for i in range(pf.metadata.num_row_groups):
        st = pf.metadata.row_group(i)
        stats = [st.column(LEAF[k]) for k in LEAF]
        if any(not (c.statistics and c.statistics.has_min_max) for c in stats):
            sel.append(i)
            continue
        x_min_lo, _x_min_hi = stats[0].statistics.min, stats[0].statistics.max
        y_min_lo, _y_min_hi = stats[1].statistics.min, stats[1].statistics.max
        _x_max_lo, x_max_hi = stats[2].statistics.min, stats[2].statistics.max
        _y_max_lo, y_max_hi = stats[3].statistics.min, stats[3].statistics.max
        if x_max_hi > xmin and x_min_lo < xmax and y_max_hi > ymin and y_min_lo < ymax:
            sel.append(i)

    farm_bounds = farm_dir / "boundary" / "field_boundaries.geojson"
    existing_ids, existing_geom = (
        _existing_fields(farm_bounds, crs, args.field_start_index)
        if args.skip_existing
        else (set(), None)
    )
    crop_filter = _crop_filter(args.crop_names)

    rows = []
    rejected = {"crop": 0, "area": 0, "county": 0, "duplicate": 0, "overlap": 0}
    for i in sel:
        d = pf.read_row_group(
            i, columns=["id", "crop:name", "administrative_area_level_2", "geometry"]
        ).to_pydict()
        for fid, crop, county, geom in zip(
            d["id"], d["crop:name"], d["administrative_area_level_2"], d["geometry"]
        ):
            if geom is None:
                continue
            poly = wkb.loads(geom)
            bb = poly.bounds
            if not (bb[2] > xmin and bb[0] < xmax and bb[3] > ymin and bb[1] < ymax):
                continue
            ha = poly.area / 10000.0  # projected CRS is equal-area
            if ha < args.min_area_ha:
                rejected["area"] += 1
                continue
            if args.max_area_ha and args.max_area_ha > 0 and ha > args.max_area_ha:
                rejected["area"] += 1
                continue
            if crop_filter and str(crop or "").strip().lower() not in crop_filter:
                rejected["crop"] += 1
                continue
            if county_geom is not None:
                inside = poly.representative_point().within(county_geom)
                share = poly.intersection(county_geom).area / poly.area if poly.area else 0.0
                if not inside or share < 0.999:
                    rejected["county"] += 1
                    continue
            if str(fid) in existing_ids:
                rejected["duplicate"] += 1
                continue
            if existing_geom is not None and poly.intersection(existing_geom).area > 1.0:
                rejected["overlap"] += 1
                continue
            rows.append((fid, crop, county, ha, poly))
    rows.sort(key=lambda r: (-r[3], str(r[0])))
    candidates = rows[: args.max_fields]
    if not candidates:
        print("no fields above threshold in this window")
        print(json.dumps({"rejected": rejected}, sort_keys=True))
        return 1

    print(
        f"candidates: {len(candidates)} of {len(rows)} matching polygons "
        f"(rejected {json.dumps(rejected, sort_keys=True)})"
    )
    if args.dry_run:
        for idx, (fid, crop, county, ha, _poly) in enumerate(candidates, start=args.field_start_index):
            print(
                f"DRY-RUN {args.field_prefix}{idx}  {ha:>8.1f} ha  crop={crop}  "
                f"county={county}  csb={fid}"
            )
        return 0

    inv_rows = []
    merged = None
    for idx, (fid, crop, county, ha, poly) in enumerate(candidates, start=args.field_start_index):
        slug = f"{args.field_prefix}{idx}"
        fdir = farm_dir / "fields" / slug
        (fdir / "boundary").mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame(
            [
                {
                    "field_id": slug,
                    "country": args.country,
                    "state": args.state,
                    "state_fips": args.state_fips.zfill(2) if args.state_fips else "",
                    "year": args.year,
                    "area_ha_est": round(ha, 1),
                    "crop": crop,
                    "area_acres": round(ha * 2.47105, 1),
                    "source": "usda_csb_fiboa",
                    "csb_id": str(fid),
                    "county": county,
                    "geometry": poly,
                }
            ],
            crs=crs,
        ).to_crs("EPSG:4326")
        gdf.to_file(fdir / "boundary" / "field_boundary.geojson", driver="GeoJSON")
        merged = gdf if merged is None else pd.concat([merged, gdf], ignore_index=True)
        inv_rows.append({"field_id": slug, "field_slug": slug})
        print(f"field {slug}  {ha:>8.1f} ha  crop={crop}  county={county}  csb={fid}")

    if farm_bounds.exists():
        old = gpd.read_file(farm_bounds)
        keep = old[~old["field_id"].isin([r["field_id"] for r in inv_rows])]
        merged = pd.concat([keep, merged], ignore_index=True)
    farm_bounds.parent.mkdir(exist_ok=True)
    assert merged is not None
    merged.to_file(farm_bounds, driver="GeoJSON")

    inv = farm_dir / "manifests" / "field-inventory.csv"
    inv.parent.mkdir(exist_ok=True)
    frame = pd.DataFrame(inv_rows)
    if inv.exists():
        frame = pd.concat([pd.read_csv(inv), frame]).drop_duplicates(subset="field_id", keep="last")
    frame.to_csv(inv, index=False)

    prov = {
        "source": "FIBOA us-usda-cropland (USDA NASS Crop Sequence Boundaries)",
        "url": URL,
        "license": "CC-BY-4.0 (FIBOA); USDA public (CSB)",
        "file_crs": crs.name,
        "bbox": args.bbox,
        "row_groups_read": len(sel),
        "total_row_groups": pf.metadata.num_row_groups,
        "min_area_ha": args.min_area_ha,
        "max_area_ha": args.max_area_ha or None,
        "county_fips": args.county_fips or None,
        "state_fips": args.state_fips or None,
        "crop_names": sorted(crop_filter) or None,
        "skip_existing": bool(args.skip_existing),
        "field_start_index": args.field_start_index,
        "accessed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "snapshot": CSB_SNAPSHOT,
        "fields": [r["field_id"] for r in inv_rows],
        "rejected": rejected,
    }
    mdir = farm_dir / "manifests"
    mdir.mkdir(exist_ok=True)
    prov_path = mdir / "csb_fields_provenance.json"
    if prov_path.exists():
        previous = json.loads(prov_path.read_text())
        runs = previous.get("runs", [])
        if not runs and previous.get("fields"):
            runs.append(
                {
                    "accessed_at": previous.get("accessed_at"),
                    "bbox": previous.get("bbox"),
                    "min_area_ha": previous.get("min_area_ha"),
                    "fields": previous.get("fields"),
                    "snapshot": previous.get("snapshot"),
                }
            )
        new_run = {
            "accessed_at": prov["accessed_at"],
            "bbox": prov["bbox"],
            "min_area_ha": prov["min_area_ha"],
            "max_area_ha": prov["max_area_ha"],
            "county_fips": prov["county_fips"],
            "crop_names": prov["crop_names"],
            "fields": prov["fields"],
            "snapshot": prov["snapshot"],
        }
        deduped = []
        seen = set()
        for run in runs + [new_run]:
            key = (run.get("accessed_at"), tuple(run.get("fields") or []))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(run)
        prov["runs"] = deduped
        prov["farm_fields"] = sorted(
            set(previous.get("farm_fields", []) + previous.get("fields", []) + prov["fields"])
        )
        prov["first_accessed_at"] = previous.get("first_accessed_at") or previous.get("accessed_at")
    else:
        prov["runs"] = [
            {
                "accessed_at": prov["accessed_at"],
                "bbox": prov["bbox"],
                "min_area_ha": prov["min_area_ha"],
                "max_area_ha": prov["max_area_ha"],
                "county_fips": prov["county_fips"],
                "crop_names": prov["crop_names"],
                "fields": prov["fields"],
                "snapshot": prov["snapshot"],
            }
        ]
        prov["farm_fields"] = prov["fields"]
        prov["first_accessed_at"] = prov["accessed_at"]
    prov_path.write_text(json.dumps(prov, indent=2, default=str))
    jdir = DATA_ROOT / "shared" / "osm" / "manifests"
    jdir.mkdir(parents=True, exist_ok=True)
    journal = jdir / "sha256_journal.json"
    log = json.loads(journal.read_text()) if journal.exists() else {}
    log[f"{grower}/{farm}/{args.field_prefix}@{prov['accessed_at']}"] = prov
    journal.write_text(json.dumps(log, indent=2, default=str))
    print(f"\n✓ {len(candidates)} real CSB fields -> {inv}")
    print(f"provenance -> {prov_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
