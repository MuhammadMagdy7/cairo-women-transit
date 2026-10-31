# Analysis findings (synthetic data — read the caveats)

Full output: `docs/analysis_output.txt` · method: `python/05_analysis.py` · data: `docs/synthetic_data.md`

## Headline results
- **426 routes** have enough rides (≥ 200) to rank; 571 are marked low confidence.
- **Peak hours are riskiest:** AM peak ≈ 40 and PM peak ≈ 37 reports per 1,000 rides,
  versus ≈ 27 at midday.
- **Interchange stops are hotspots:** the top-5 stops by reports are all major
  interchanges (e.g. Ramses, Ahmed Oraby Metro, Al Salam Tunnel exit).
- The **top-10 priority routes** form the proposed launch set for a women-only service.

## What is a finding and what is an assumption
| result | real network structure | assumption I set | can you claim it? |
|---|---|---|---|
| CTA buses have the highest risk per ride | — | CTA crowding factor 1.45 (highest) | **No** — it comes straight from the assumption |
| Peak hours are riskier | — | peak risk factor 1.5–1.6 | **No** — assumption |
| Which specific stops are hotspots | yes: stops served by many routes | hotspot factor rises with routes served | Partly — the network decides *which* stops |
| Which specific routes rank top 10 | yes: frequencies, stops, capacity | weights 40/30/20/10 | Method only — re-run with real reports |

**How to present it:** the project delivers a working pipeline and a ranking method.
Swap `app.safety_reports` for real survey / HarassMap rows (`source` column) and the
same SQL views, Python script and Power BI report produce real conclusions.

## Sensitivity
Ranks depend on `WEIGHTS` and `MIN_RIDES` in `05_analysis.py`. Showing the top 10 under
2–3 weight settings in the report is a strong addition.
