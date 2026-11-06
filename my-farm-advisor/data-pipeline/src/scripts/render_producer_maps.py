#!/usr/bin/env python3
"""Render a lightweight, self-contained Leaflet HTML map per producer (grower).

Produces one HTML per producer showing every real field boundary under that
producer's farms on an online satellite basemap (ESRI World Imagery). The HTML is
deliberately lightweight: it embeds only the real field polygons plus light
metadata (the producer/farm/field names and a few attributes), so it works
offline once downloaded. No rasters and no large datasets are embedded.

Real polygons are read from the canonical runtime root:
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson

Each field draws its real polygon, shows a click popup with producer, farm, and
field name, auto-fits to the producer's fields, and a side panel lists every
field; clicking a field flies to it and opens its popup.

Nothing here writes outside DATA_PIPELINE_DATA_ROOT. Outputs go under
<farm>/maps/producer_<grower>_map.html, which stays out of Git.

Usage:
    python render_producer_maps.py --grower il-dekalb-grower
    python render_producer_maps.py --all                 # all growers with fields
    python render_producer_maps.py                       # default: IL + IA
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path


def _human_grower_label(grower_slug: str, state: str | None) -> str:
    base = grower_slug.replace("-grower", "").replace("-", " ").title()
    if state:
        return f"{base} ({state})"
    return base


def _load_feature(bpath: Path) -> tuple[dict, dict] | None:
    """Return (geometry, properties) of the first feature, or None."""
    try:
        data = json.loads(bpath.read_text(encoding="utf-8"))
        feats = data.get("features") or []
        if not feats:
            return None
        f = feats[0]
        geom = f.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            return None
        return (geom, f.get("properties", {}))
    except Exception:  # noqa: BLE001
        return None


def _field_entries(farm_dir: Path) -> list[dict]:
    fields_dir = farm_dir / "fields"
    entries: list[dict] = []
    if not fields_dir.is_dir():
        return entries
    for field_dir in sorted(fields_dir.iterdir()):
        if not field_dir.is_dir():
            continue
        bpath = field_dir / "boundary" / "field_boundary.geojson"
        loaded = _load_feature(bpath)
        if loaded is None:
            continue
        geom, props = loaded
        entries.append(
            {
                "field": field_dir.name,
                "geom": geom,
                "props": props,
            }
        )
    return entries


def _bounds(coords):
    """Approx lon/lat bounds of a field geometry, or None."""
    pts = []
    def walk(c):
        if isinstance(c, (list, tuple)):
            if c and isinstance(c[0], (int, float)) and len(c) >= 2:
                pts.append((float(c[0]), float(c[1])))
            else:
                for sub in c:
                    walk(sub)
    walk(coords)
    if not pts:
        return None
    minx = min(p[0] for p in pts)
    maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    maxy = max(p[1] for p in pts)
    return [minx, miny, maxx, maxy]


def _padded(b, f: float):
    if not b:
        return b
    dx = max((b[2] - b[0]) * f, 1e-4)
    dy = max((b[3] - b[1]) * f, 1e-4)
    return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy]


def render_producer(grower_slug: str, data_root: Path, out_root: Path) -> Path | None:
    growers = data_root / "growers"
    grower_dir = growers / grower_slug
    if not grower_dir.is_dir():
        raise FileNotFoundError(f"grower dir not found: {grower_dir}")

    farms = sorted(
        d for d in (grower_dir / "farms").iterdir()
        if d.is_dir() and (d / "fields").is_dir()
    )
    if not farms:
        print(f"  no farms with fields for {grower_slug}; skipping")
        return None

    layers: list[dict] = []
    for farm in farms:
        try:
            fm = json.loads((farm / "farm.json").read_text(encoding="utf-8"))
            farm_name = fm.get("display_name") or farm.name
            state = fm.get("state") or ""
        except Exception:  # noqa: BLE001
            farm_name, state = farm.name, ""
        for entry in _field_entries(farm):
            props = entry["props"]
            acres = props.get("area_acres")
            infos = {
                "producer": _human_grower_label(grower_slug, state or None),
                "farm": farm_name,
                "field": entry["field"],
                "county": props.get("county") or props.get("county_name") or "",
                "state": state,
                "crop": props.get("crop") or "",
                "acres": f"{float(acres):,.1f}" if acres else "",
            }
            color = "#1f77b4" if grower_slug.startswith("il") else "#d62728"
            layers.append(
                {
                    "field": entry["field"],
                    "display": entry["field"],
                    "geom": entry["geom"],
                    "infos": infos,
                    "bounds": _padded(_bounds(entry["geom"].get("coordinates", [])), 0.15),
                    "color": color,
                }
            )

    if not layers:
        print(f"  no usable field polygons for {grower_slug}; skipping")
        return None

    producer_label = _human_grower_label(grower_slug, layers[0]["infos"].get("state"))
    fit = None
    lonslats = [b for L in layers if (b := L["bounds"])]
    if lonslats:
        lons = [x for b in lonslats for x in (b[0], b[2])]
        lats = [y for b in lonslats for y in (b[1], b[3])]
        padx = 0.02 * (max(lons) - min(lons)) if max(lons) > min(lons) else 0.02
        pady = 0.02 * (max(lats) - min(lats)) if max(lats) > min(lats) else 0.02
        fit = [[min(lats) - pady, min(lons) - padx], [max(lats) + pady, max(lons) + padx]]

    html = _build_html(grower_slug, producer_label, layers, fit)
    first_farm = farms[0].name
    out_dir = out_root / grower_slug / "farms" / first_farm / "maps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"producer_{grower_slug}_map.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _build_html(grower_slug: str, producer_label: str, layers: list[dict], fit) -> str:
    payload = {
        "producer": producer_label,
        "grower": grower_slug,
        "fields": [
            {
                "field": L["field"],
                "geom": L["geom"],
                "infos": L["infos"],
                "bounds": L["bounds"],
                "color": L["color"],
            }
            for L in layers
        ],
        "fit": fit,
    }
    data_json = json.dumps(payload, separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Producer Map — {producer_label}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  html, body {{ margin:0; height:100%; font-family:-apple-system,Segoe UI,Roboto,sans-serif; }}
  #wrap {{ display:flex; height:100%; }}
  #map {{ flex:1; height:100%; }}
  #panel {{ width:260px; min-width:260px; overflow:auto; background:#1f2b36; color:#eaf2f8; padding:12px; box-sizing:border-box; }}
  #panel h3 {{ margin:0 0 4px; font-size:15px; }}
  #panel .sub {{ font-size:12px; color:#9fb3c3; margin-bottom:12px; }}
  #panel ul {{ list-style:none; margin:0; padding:0; }}
  #panel li {{ padding:8px 10px; margin:4px 0; border-radius:5px; cursor:pointer; background:#2c3e50; font-size:13px; border-left:3px solid #475; }}
  #panel li:hover {{ background:#34495e; }}
  .pmeta {{ font-size:11px; color:#b8c7d4; }}
  .popup-body {{ background:#ffffff; border-radius:4px; }}
  .popup-body .pi {{ color:#333333; }}
</style>
</head>
<body>
<div id="wrap">
  <div id="panel">
    <h3>{producer_label}</h3>
    <div class="sub">Grower: {grower_slug}</div>
    <ul id="plist"></ul>
  </div>
  <div id="map"></div>
</div>
<script>
  const DATA = {data_json};
  const map = L.map('map');
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
    maxZoom: 19, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics'
  }}).addTo(map);

  const polys = [];
  function popupHtml(i) {{
    return '<div class="popup-body"><b>' + i.field + '</b><br/>' +
      '<span class="pi">Productor: ' + i.producer + '<br/>Finca: ' + i.farm + '<br/>' +
      (i.county ? 'Condado: ' + i.county + '<br/>' : '') +
      (i.state ? 'Estado: ' + i.state + '<br/>' : '') +
      (i.crop ? 'Cultivo: ' + i.crop + '<br/>' : '') +
      (i.acres ? 'Área: ' + i.acres + ' ac' : '') +
      '</span></div>';
  }}

  for (const f of DATA.fields) {{
    const poly = L.geoJSON(f.geom, {{
      color: f.color || '#d62728', weight: 2, fillColor: f.color || '#d62728', fillOpacity: 0.18
    }});
    poly.bindPopup(popupHtml(f.infos));
    poly.addTo(map);
    polys.push({{ field: f.field, poly, bounds: f.bounds }});
  }}

  const list = document.getElementById('plist');
  for (const f of DATA.fields) {{
    const li = document.createElement('li');
    li.textContent = f.field;
    const meta = document.createElement('div');
    meta.className = 'pmeta';
    meta.textContent = (f.infos.crop ? f.infos.crop + ' · ' : '') + (f.infos.acres ? f.infos.acres + ' ac' : '');
    li.appendChild(meta);
    li.addEventListener('click', () => flyField(f));
    list.appendChild(li);
  }}

  function flyField(f) {{
    if (!f.bounds) return;
    const bb = [[f.bounds[1], f.bounds[0]], [f.bounds[3], f.bounds[2]]];
    map.flyToBounds(L.latLngBounds(bb), {{ maxZoom: 17 }});
    const m = polys.find(p => p.field === f.field);
    if (m) setTimeout(() => m.poly.openPopup(), 400);
  }}

  if (DATA.fit) map.fitBounds(DATA.fit, {{ padding: [40, 40] }});
  else if (polys.length) map.fitBounds(L.latLngBounds(polys.map(m => m.poly.getBounds())));
  else map.setView([41, -93], 4);
</script>
</body>
</html>"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grower", default=None, help="a single grower slug, e.g. il-dekalb-grower")
    ap.add_argument("--all", action="store_true", help="render all growers under the runtime root")
    ap.add_argument("--root", default=None, help="data root (default: DATA_PIPELINE_DATA_ROOT)")
    ap.add_argument("--out-root", default=None,
                    help="output root (default: DATA_PIPELINE_DATA_ROOT); HTML placed under grower/farm/maps")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    data_root = Path(args.root or os.environ["DATA_PIPELINE_DATA_ROOT"]).resolve()
    out_root = Path(args.out_root or data_root).resolve()
    render_root = data_root / "data-pipeline"
    growers_dir = render_root / "growers"
    output_root = out_root / "data-pipeline" / "growers"
    if args.all:
        targets = sorted(d.name for d in growers_dir.iterdir() if d.is_dir())
    elif args.grower:
        targets = [args.grower]
    else:
        targets = ["il-dekalb-grower", "ia-story-grower"]

    produced: list[str] = []
    for grower in targets:
        print(f"\n=== {grower} ===")
        try:
            out_path = render_producer(grower, render_root, output_root)
        except Exception as exc:  # noqa: BLE001 - per-grower failure must not stop the batch
            print(f"  ERROR: {exc}")
            continue
        if out_path:
            size_kb = out_path.stat().st_size / 1024
            print(f"✓ wrote {out_path} ({size_kb:.1f} KB)")
            produced.append(str(out_path.resolve()))

    print(f"\nCompleted {dt.date.today().isoformat()}: {len(produced)} producer map(s) rendered.")
    return 0 if produced else 1


if __name__ == "__main__":
    raise SystemExit(main())