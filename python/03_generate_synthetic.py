"""Generate SYNTHETIC app data (riders, rides, safety_reports) on top of the real GTFS network.

Nothing here is observed data. Distributions are tied to the real network and
calibrated to published Cairo figures:
  - ITDP / UN-Habitat Cairo BRT gender study: >80% of women surveyed face harassment
    at some stage of the journey (walk to stop, waiting, boarding, on board).
  - Overcrowding raises risk; peak periods and crowded modes get higher risk factors.
Calibration target: share of riders with >= 1 incident over the year ~ 80%.

Usage: python 03_generate_synthetic.py <silver_dir> <out_dir> [n_riders=4000] [seed=42]
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

silver, out = Path(sys.argv[1]), Path(sys.argv[2])
N_RIDERS = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
rng = np.random.default_rng(int(sys.argv[4]) if len(sys.argv) > 4 else 42)
out.mkdir(parents=True, exist_ok=True)
rd = lambda n: pd.read_parquet(silver / f"{n}.parquet")
routes, trips, st, fr, stops = rd("routes"), rd("trips"), rd("stop_times"), rd("frequencies"), rd("stops")

# ---------- assumptions (documented in the report) ----------
SEATS = {"P_O_14": 14, "P_B_8": 8, "COOP": 29, "CTA": 60, "CTA_M": 30,
         "MM": 60, "BOX": 12, "GRN": 60, "LTRA_M": 30, "NAT": 60, "PGT": 7}               # capacity per vehicle
CROWD = {"P_O_14": 1.25, "P_B_8": 0.85, "COOP": 1.15, "CTA": 1.45, "CTA_M": 1.30,
         "MM": 0.90, "BOX": 1.00, "GRN": 0.80, "LTRA_M": 1.20, "NAT": 0.90, "PGT": 0.85}       # crowding risk factor
FARE = {"P_O_14": 9, "P_B_8": 7, "COOP": 10, "CTA": 8, "CTA_M": 9,
        "MM": 15, "BOX": 8, "GRN": 20, "LTRA_M": 9, "NAT": 10, "PGT": 15}                  # base fare EGP (assumed)
WINDOW = {21600: ("AM peak", 1.40, 1.60), 36000: ("Midday", 0.90, 1.00),
          54000: ("PM peak", 1.30, 1.50), 68400: ("Evening", 0.60, 1.35)}  # demand, risk
DOW_DEMAND = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.5, 5: 0.7, 6: 1.0}    # Mon..Sun (Fri=4)
BASE_P = 0.0125                        # base incident probability per ride (calibrated)
STAGES = (["walk_to_stop", "waiting", "boarding", "on_board", "alighting"],
          [0.15, 0.28, 0.17, 0.33, 0.07])
TYPES = (["verbal", "staring", "following", "physical", "overcrowding", "other"],
         [0.30, 0.22, 0.10, 0.13, 0.18, 0.07])

unknown = set(routes.agency_id) - set(SEATS)
assert not unknown, f"add assumptions for agencies: {unknown}"

# ---------- network supply per route & window ----------
fr = fr.merge(trips[["trip_id", "route_id"]], on="trip_id").merge(routes[["route_id", "agency_id"]], on="route_id")
fr["seats"] = fr.vehicles_in_window * fr.agency_id.map(SEATS)
fr["demand_w"] = fr.seats * fr.start_secs.map(lambda s: WINDOW[s][1])
supply = fr.groupby(["route_id", "start_secs"], as_index=False).agg(
    demand_w=("demand_w", "sum"), headway=("headway_secs", "median"))
route_w = supply.groupby("route_id").demand_w.sum()

# stop hotspot factor: busy interchange stops (many routes) are riskier
stop_routes = st.merge(trips[["trip_id", "route_id"]], on="trip_id").groupby("stop_id").route_id.nunique()
hot = (1 + 0.6 * (stop_routes.rank(pct=True) ** 3)).to_dict()      # 1.0 .. 1.6

# stop sequences per route (one representative trip per route & direction)
seq = st.merge(trips[["trip_id", "route_id"]], on="trip_id").sort_values(["trip_id", "stop_sequence"])
route_stops = {r: g.stop_id.to_numpy() for r, g in
               seq.groupby("route_id").apply(lambda g: g[g.trip_id == g.trip_id.iloc[0]], include_groups=False)
               .reset_index().groupby("route_id")}

# ---------- riders ----------
served = stop_routes.index.to_numpy()
home = rng.choice(served, N_RIDERS, p=(stop_routes / stop_routes.sum()).to_numpy())
riders = pd.DataFrame({
    "rider_id": np.arange(1, N_RIDERS + 1),
    "age_group": rng.choice(["18-24", "25-34", "35-44", "45-54", "55+"], N_RIDERS, p=[.30, .32, .19, .12, .07]),
    "home_stop_id": home,
    "occupation": rng.choice(["student", "employee", "self_employed", "homemaker", "other"], N_RIDERS,
                             p=[.30, .38, .10, .15, .07]),
})

# routes serving each home stop -> riders mostly ride "their" routes
# only routes with frequency data can carry rides (28 trips in the feed have none)
has_supply = set(route_w.index)
routes_at_stop = {s: [r for r in rs if r in has_supply]
                  for s, rs in seq.groupby("stop_id").route_id.unique().items()}
all_routes = route_w.index.to_numpy()
all_p = (route_w / route_w.sum()).to_numpy()

# ---------- rides ----------
days = pd.date_range("2025-01-01", "2025-12-31")
day_p = np.array([DOW_DEMAND[d.weekday()] for d in days]); day_p /= day_p.sum()
n_rides = rng.poisson(48, N_RIDERS)                                   # ~ 1 ride/week

rows = []
for rid, h, n in zip(riders.rider_id, riders.home_stop_id, n_rides):
    local = routes_at_stop.get(h, [])
    for _ in range(n):
        r = rng.choice(local) if len(local) and rng.random() < 0.65 else rng.choice(all_routes, p=all_p)
        rows.append((rid, r))
rides = pd.DataFrame(rows, columns=["rider_id", "route_id"])

# time window per ride, weighted by that route's supply x demand
sw = supply.set_index(["route_id", "start_secs"]).demand_w
win = np.empty(len(rides), dtype=int)
for r, idx in rides.groupby("route_id").groups.items():
    s = sw.loc[r]
    win[idx] = rng.choice(s.index.to_numpy(), len(idx), p=(s / s.sum()).to_numpy())
rides["window_start"] = win
day = rng.choice(len(days), len(rides), p=day_p)
offset = rides.window_start + rng.integers(0, 4 * 3600, len(rides))
rides["board_datetime"] = (pd.Series(days[day]) + pd.to_timedelta(offset.to_numpy(), "s")).dt.floor("min")

# board / alight stops in travel order
ba = np.array([(lambda s: (lambda i, j: (s[i], s[j]))(*sorted(rng.choice(len(s), 2, replace=False))))(route_stops[r])
               for r in rides.route_id])
rides["board_stop_id"], rides["alight_stop_id"] = ba[:, 0], ba[:, 1]

hw = supply.set_index(["route_id", "start_secs"]).headway
mean_wait = hw.loc[list(zip(rides.route_id, rides.window_start))].to_numpy() / 60 / 2
rides["wait_minutes"] = np.minimum(rng.exponential(mean_wait), 90).round().astype(int)

agency = rides.route_id.map(routes.set_index("route_id").agency_id)
rides["fare_egp"] = (agency.map(FARE) * rng.uniform(0.9, 1.4, len(rides))).round(0)

# incident risk
risk = (BASE_P * agency.map(CROWD).to_numpy()
        * rides.window_start.map(lambda s: WINDOW[s][2]).to_numpy()
        * rides.board_stop_id.map(hot).to_numpy()
        * np.where(rides.board_datetime.dt.weekday.isin([4, 5]), 0.8, 1.0)
        * (1 + rides.wait_minutes.to_numpy() / 60))                       # long waits add risk
incident = rng.random(len(rides)) < risk
# felt-safe score: lower on riskier rides, much lower if something happened
score = 4.4 - 25 * risk - 1.8 * incident + rng.normal(0, 0.6, len(rides))
rides["felt_safe_score"] = np.clip(np.round(score), 1, 5).astype(int)

rides["_incident"] = incident
rides = rides.sort_values("board_datetime").reset_index(drop=True)
rides.insert(0, "ride_id", np.arange(1, len(rides) + 1))

# ---------- safety reports (one per incident ride) ----------
inc = rides[rides._incident].copy()
n = len(inc)
stage = rng.choice(STAGES[0], n, p=STAGES[1])
itype = rng.choice(TYPES[0], n, p=TYPES[1])
# overcrowding mostly happens on board / boarding; physical skews to crowded stages
itype = np.where((itype == "overcrowding") & np.isin(stage, ["walk_to_stop"]), "following", itype)
sev_base = pd.Series(itype).map({"verbal": 2, "staring": 1.5, "following": 3, "physical": 4,
                                 "overcrowding": 2, "other": 2}).to_numpy()
severity = np.clip(np.round(sev_base + rng.normal(0, 0.7, n)), 1, 5).astype(int)
stop_for_stage = np.where(stage == "alighting", inc.alight_stop_id, inc.board_stop_id)
lag = {"walk_to_stop": -5, "waiting": 0, "boarding": 0, "on_board": 10, "alighting": 20}
report_dt = inc.board_datetime + pd.to_timedelta(
    pd.Series(stage).map(lag).to_numpy() + rng.integers(0, 6, n), "min")
geo = stops.set_index("stop_id")[["stop_lat", "stop_lon"]]
ll = geo.loc[stop_for_stage].to_numpy() + rng.normal(0, 0.0015, (n, 2))   # ~150 m jitter
reports = pd.DataFrame({
    "report_id": np.arange(1, n + 1),
    "report_datetime": report_dt.to_numpy(),
    "rider_id": inc.rider_id.to_numpy(),
    "ride_id": inc.ride_id.to_numpy(),
    "route_id": inc.route_id.to_numpy(),
    "nearest_stop_id": stop_for_stage,
    "journey_stage": stage,
    "incident_type": itype,
    "severity": severity,
    "source": "synthetic",
    "lat": ll[:, 0].round(6),
    "lon": ll[:, 1].round(6),
})
rides = rides.drop(columns="_incident")
rides["window_start"] = rides.window_start.map(lambda s: WINDOW[s][0])
rides = rides.rename(columns={"window_start": "period"})

# signup = a few days before each rider's first ride (no rides before signup)
first = rides.groupby("rider_id").board_datetime.min().dt.normalize()
riders["signup_date"] = (riders.rider_id.map(first)
                         - pd.to_timedelta(rng.integers(0, 15, N_RIDERS), "D")).dt.date
riders = riders[riders.rider_id.isin(first.index)]
riders.to_parquet(out / "riders.parquet", index=False)
rides.to_parquet(out / "rides.parquet", index=False)
reports.to_parquet(out / "safety_reports.parquet", index=False)

# ---------- calibration report ----------
hit = reports.rider_id.nunique() / N_RIDERS
print(f"riders {len(riders):,} | rides {len(rides):,} | reports {len(reports):,}")
print(f"riders with >=1 incident: {hit:.1%}  (target ~80%)")
print(f"incidents per 1k rides: {1000*len(reports)/len(rides):.1f}")
print("by period:\n", (reports.merge(rides[['ride_id','period']], on='ride_id').period.value_counts()
                       / rides.period.value_counts() * 1000).round(1).rename("reports_per_1k"))
print("by stage:\n", reports.journey_stage.value_counts(normalize=True).round(2))
print("avg felt_safe:", rides.felt_safe_score.mean().round(2),
      "| with incident:", rides[rides.ride_id.isin(reports.ride_id)].felt_safe_score.mean().round(2))
