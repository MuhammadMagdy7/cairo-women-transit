"""Bronze (raw GTFS .txt) -> Silver (typed, cleaned Parquet).
- casts types, converts YYYYMMDD -> date, HH:MM:SS -> seconds
- attaches Arabic names from translations.txt (matched by field_value)
Usage: python 02_build_silver.py <bronze_gtfs_dir> <silver_dir>
"""
import sys
from pathlib import Path
import pandas as pd

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
read = lambda n: pd.read_csv(src / f"{n}.txt", dtype=str, keep_default_na=False, na_values=[""])

def secs(s: pd.Series) -> pd.Series:
    p = s.str.split(":", expand=True).astype(int)
    return p[0] * 3600 + p[1] * 60 + p[2]

def ymd(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%Y%m%d").dt.date

tr = read("translations")
def ar(table, field):
    m = tr[(tr.table_name == table) & (tr.field_name == field) & (tr.language == "ar")]
    return dict(zip(m.field_value, m.translation))

out = {}

agency = read("agency")
agency["agency_name_ar"] = agency.agency_name.map(ar("agency", "agency_name"))
out["agency"] = agency

routes = read("routes")
routes["route_type"] = routes.route_type.astype("int16")
for c in ("continuous_pickup", "continuous_drop_off"):
    routes[c] = routes[c].astype("int8")
routes["route_long_name_ar"] = routes.route_long_name.map(ar("routes", "route_long_name"))
routes["route_short_name_ar"] = routes.route_short_name.map(ar("routes", "route_short_name"))
out["routes"] = routes

stops = read("stops")
stops[["stop_lat", "stop_lon"]] = stops[["stop_lat", "stop_lon"]].astype(float)
stops["stop_name_ar"] = stops.stop_name.map(ar("stops", "stop_name"))
out["stops"] = stops

cal = read("calendar")
for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
    cal[d] = cal[d].astype(int).astype(bool)
cal["start_date"], cal["end_date"] = ymd(cal.start_date), ymd(cal.end_date)
out["calendar"] = cal

trips = read("trips")
trips["direction_id"] = trips.direction_id.astype("int8")
trips["trip_headsign_ar"] = trips.trip_headsign.map(ar("trips", "trip_headsign"))
out["trips"] = trips

st = read("stop_times")
st["stop_sequence"] = st.stop_sequence.astype(int)
st["arrival_secs"], st["departure_secs"] = secs(st.arrival_time), secs(st.departure_time)
out["stop_times"] = st

fr = read("frequencies")
fr["headway_secs"] = fr.headway_secs.astype(int)
fr["start_secs"], fr["end_secs"] = secs(fr.start_time), secs(fr.end_time)
fr["vehicles_in_window"] = (fr.end_secs - fr.start_secs) // fr.headway_secs
out["frequencies"] = fr

sh = read("shapes")
sh["shape_pt_sequence"] = sh.shape_pt_sequence.astype(int)
sh[["shape_pt_lat", "shape_pt_lon"]] = sh[["shape_pt_lat", "shape_pt_lon"]].astype(float)
out["shapes"] = sh

fi = read("feed_info")
fi["feed_start_date"], fi["feed_end_date"] = ymd(fi.feed_start_date), ymd(fi.feed_end_date)
out["feed_info"] = fi
out["translations"] = tr

for name, df in out.items():
    df.to_parquet(dst / f"{name}.parquet", index=False)
    print(f"{name:12s} {len(df):>8,} rows -> {name}.parquet")

cov = lambda df, c: f"{df[c].notna().mean():.0%}"
print(f"\nArabic coverage: stops {cov(stops,'stop_name_ar')}, "
      f"routes long {cov(routes,'route_long_name_ar')}, short {cov(routes,'route_short_name_ar')}, "
      f"agency {cov(agency,'agency_name_ar')}")
