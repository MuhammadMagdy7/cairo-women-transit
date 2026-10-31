"""Analysis: which routes and stops should a women-only service cover first?

Builds the GOLD layer from silver GTFS + synthetic app data:
  gold/route_priority.parquet  - one row per route, Priority Score 0-100 + rank
  gold/stop_hotspots.parquet   - one row per stop with reports, boardings, rate
  gold/period_stage.parquet    - reports by period x journey stage (heatmap)
and prints the headline findings.

Priority Score (routes with >= MIN_RIDES rides; others are 'low confidence'):
  40%  risk rate      reports per 1,000 rides        (how unsafe a ride is)
  30%  exposure       rides on the route             (how many women are affected)
  20%  severity       mean report severity 1-5       (how serious incidents are)
  10%  perception     5 - mean felt-safe score       (how unsafe it feels)
Each component is converted to a 0-1 percentile rank before weighting, so units
don't dominate. Weights are a stated design choice - change WEIGHTS to test them.

Usage: python 05_analysis.py <silver_dir> <synthetic_dir> <gold_dir>
"""
import sys
from pathlib import Path
import pandas as pd

silver, synth, gold = (Path(p) for p in sys.argv[1:4])
gold.mkdir(parents=True, exist_ok=True)
MIN_RIDES = 200
WEIGHTS = {"risk_rate": 0.40, "exposure": 0.30, "severity": 0.20, "perception": 0.10}

routes = pd.read_parquet(silver / "routes.parquet")
agency = pd.read_parquet(silver / "agency.parquet")
stops = pd.read_parquet(silver / "stops.parquet")
rides = pd.read_parquet(synth / "rides.parquet")
reps = pd.read_parquet(synth / "safety_reports.parquet")

# ---------------- route priority ----------------
r = rides.groupby("route_id").agg(rides=("ride_id", "size"),
                                  avg_felt_safe=("felt_safe_score", "mean"),
                                  avg_wait_min=("wait_minutes", "mean"),
                                  peak_share=("period", lambda s: s.isin(["AM peak", "PM peak"]).mean()))
p = reps.groupby("route_id").agg(reports=("report_id", "size"),
                                 avg_severity=("severity", "mean"),
                                 serious_share=("incident_type", lambda s: s.isin(["physical", "following"]).mean()))
rp = r.join(p, how="left").fillna({"reports": 0, "avg_severity": 0, "serious_share": 0})
rp["reports_per_1k"] = rp.reports * 1000 / rp.rides
rp["confidence"] = (rp.rides >= MIN_RIDES).map({True: "ok", False: "low"})

ok = rp.confidence == "ok"
comp = pd.DataFrame({
    "risk_rate": rp.loc[ok, "reports_per_1k"].rank(pct=True),
    "exposure": rp.loc[ok, "rides"].rank(pct=True),
    "severity": rp.loc[ok, "avg_severity"].rank(pct=True),
    "perception": (5 - rp.loc[ok, "avg_felt_safe"]).rank(pct=True),
})
rp["priority_score"] = (sum(comp[k] * w for k, w in WEIGHTS.items()) * 100).round(1)
rp["priority_rank"] = rp.priority_score.rank(ascending=False, method="first").astype("Int64")
rp["priority_tier"] = pd.cut(rp.priority_rank, [0, 10, 50, 150, 10_000],
                             labels=["1 Launch (top 10)", "2 Phase 2 (11-50)", "3 Phase 3 (51-150)", "4 Later"])
rp["priority_tier"] = rp.priority_tier.astype(object).where(rp.priority_tier.notna(), "5 Low confidence")

rp = (rp.reset_index()
        .merge(routes[["route_id", "agency_id", "route_short_name", "route_long_name",
                       "route_short_name_ar", "route_long_name_ar"]], on="route_id")
        .merge(agency[["agency_id", "agency_name", "agency_name_ar"]], on="agency_id")
        .sort_values("priority_rank"))
num = ["avg_felt_safe", "avg_wait_min", "peak_share", "avg_severity", "serious_share", "reports_per_1k"]
rp[num] = rp[num].round(3)
rp["reports"] = rp.reports.astype(int)
rp.to_parquet(gold / "route_priority.parquet", index=False)

# ---------------- stop hotspots ----------------
b = rides.groupby("board_stop_id").size().rename("boardings")
s = reps.groupby("nearest_stop_id").agg(reports=("report_id", "size"), avg_severity=("severity", "mean"))
hs = (stops.set_index("stop_id")[["stop_name", "stop_name_ar", "stop_lat", "stop_lon"]]
           .join(b).join(s).fillna({"boardings": 0, "reports": 0}))
hs = hs[(hs.boardings > 0) | (hs.reports > 0)]
hs["reports_per_1k_boardings"] = (hs.reports * 1000 / hs.boardings.where(hs.boardings > 0)).round(1)
hs[["boardings", "reports"]] = hs[["boardings", "reports"]].astype(int)
hs["avg_severity"] = hs.avg_severity.round(2)
hs = hs.reset_index().rename(columns={"index": "stop_id"}).sort_values("reports", ascending=False)
hs.to_parquet(gold / "stop_hotspots.parquet", index=False)

# ---------------- period x stage ----------------
ps = (reps.merge(rides[["ride_id", "period"]], on="ride_id")
          .groupby(["period", "journey_stage"]).size().rename("reports").reset_index())
ps["rides_in_period"] = ps.period.map(rides.period.value_counts())
ps["reports_per_1k"] = (ps.reports * 1000 / ps.rides_in_period).round(2)
ps.to_parquet(gold / "period_stage.parquet", index=False)

# ---------------- findings ----------------
top = rp[rp.confidence == "ok"].head(10)
cov = top.rides.sum() / rides.shape[0]
print(f"routes ranked: {ok.sum()} (>= {MIN_RIDES} rides), low confidence: {(~ok).sum()}")
print(f"\nTOP 10 routes for the women-only launch (cover {cov:.1%} of all rides, "
      f"{top.reports.sum() / len(reps):.1%} of all reports):")
print(top[["priority_rank", "route_long_name", "agency_id", "rides", "reports_per_1k",
           "avg_severity", "priority_score"]].to_string(index=False))
print("\nreports per 1k rides by operator (routes with enough data):")
print(rp[rp.confidence == "ok"].groupby("agency_name")
        .apply(lambda g: 1000 * g.reports.sum() / g.rides.sum(), include_groups=False)
        .sort_values(ascending=False).round(1).to_string())
print("\ntop 5 hotspot stops (by reports):")
print(hs.head(5)[["stop_name", "boardings", "reports", "reports_per_1k_boardings"]].to_string(index=False))
print("\nreports per 1k rides by period:")
print(ps.groupby("period").reports_per_1k.sum().round(1).sort_values(ascending=False).to_string())
