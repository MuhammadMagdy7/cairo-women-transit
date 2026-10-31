"""Profile the Cairo GTFS feed: row counts, nulls, keys, FK orphans, value ranges.
Usage: python 01_profile_gtfs.py <gtfs_dir> <out_md>
"""
import sys
from pathlib import Path
import pandas as pd

src, out = Path(sys.argv[1]), Path(sys.argv[2])
t = {f.stem: pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
     for f in sorted(src.glob("*.txt"))}

lines = ["# GTFS Data Profile — Greater Cairo 2025\n"]
lines.append("| table | rows | columns | columns with nulls |")
lines.append("|---|---:|---|---|")
for name, df in t.items():
    nulls = ", ".join(f"{c} ({n})" for c, n in df.isna().sum().items() if n) or "—"
    lines.append(f"| {name} | {len(df):,} | {', '.join(df.columns)} | {nulls} |")

def dup(df, cols):
    return int(df.duplicated(cols).sum())

lines.append("\n## Primary-key duplicates")
for name, cols in {"agency": ["agency_id"], "routes": ["route_id"], "stops": ["stop_id"],
                   "trips": ["trip_id"], "calendar": ["service_id"],
                   "stop_times": ["trip_id", "stop_sequence"],
                   "frequencies": ["trip_id", "start_time"],
                   "shapes": ["shape_id", "shape_pt_sequence"]}.items():
    lines.append(f"- {name} {cols}: {dup(t[name], cols)}")

def orphans(child, ccol, parent, pcol):
    c = t[child][ccol].dropna()
    return int((~c.isin(set(t[parent][pcol]))).sum())

lines.append("\n## Foreign-key orphans (child rows with no parent)")
for child, ccol, parent, pcol in [
    ("routes", "agency_id", "agency", "agency_id"),
    ("trips", "route_id", "routes", "route_id"),
    ("trips", "service_id", "calendar", "service_id"),
    ("trips", "shape_id", "shapes", "shape_id"),
    ("stop_times", "trip_id", "trips", "trip_id"),
    ("stop_times", "stop_id", "stops", "stop_id"),
    ("frequencies", "trip_id", "trips", "trip_id")]:
    lines.append(f"- {child}.{ccol} → {parent}.{pcol}: {orphans(child, ccol, parent, pcol)}")

lines.append("\n## Coverage")
lines.append(f"- routes without trips: {int((~t['routes'].route_id.isin(t['trips'].route_id)).sum())}")
lines.append(f"- trips without stop_times: {int((~t['trips'].trip_id.isin(t['stop_times'].trip_id)).sum())}")
lines.append(f"- trips without frequencies: {int((~t['trips'].trip_id.isin(t['frequencies'].trip_id)).sum())}")
lines.append(f"- stops never served: {int((~t['stops'].stop_id.isin(t['stop_times'].stop_id)).sum())}")

lines.append("\n## Agencies (routes per operator)")
rc = t["routes"].merge(t["agency"], on="agency_id", how="left").groupby("agency_name").size()
for k, v in rc.sort_values(ascending=False).items():
    lines.append(f"- {k}: {v}")

lines.append("\n## Value checks")
s = t["stops"].astype({"stop_lat": float, "stop_lon": float})
lines.append(f"- stop_lat range: {s.stop_lat.min():.4f} – {s.stop_lat.max():.4f}")
lines.append(f"- stop_lon range: {s.stop_lon.min():.4f} – {s.stop_lon.max():.4f}")
lines.append(f"- route_type values: {sorted(t['routes'].route_type.unique())}")
h = t["frequencies"].headway_secs.astype(int) / 60
lines.append(f"- headway (min): min {h.min():.1f}, median {h.median():.1f}, max {h.max():.1f}")
lines.append(f"- frequency windows: {sorted(t['frequencies'].start_time.unique())}")
over24 = (t["stop_times"].arrival_time.str[:2].astype(int) >= 24).sum()
lines.append(f"- stop_times with hour ≥ 24: {int(over24)}")
lines.append(f"- max stop_name length: {t['stops'].stop_name.str.len().max()}")
lines.append(f"- max route_long_name length: {t['routes'].route_long_name.str.len().max()}")
lines.append(f"- translation tables/fields: "
             f"{t['translations'].groupby(['table_name','field_name']).size().to_dict()}")
lines.append(f"- translations languages: {sorted(t['translations'].language.unique())}")

out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
