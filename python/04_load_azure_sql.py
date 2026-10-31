r"""Load silver GTFS + synthetic app data into Azure SQL, in foreign-key order.

Prereqs:
  pip install pyodbc pandas pyarrow
  Microsoft ODBC Driver 17 (17.2+) or 18 for SQL Server
  Run sql/01_schema.sql on the database first.

The server uses Microsoft Entra-only sign-in (no SQL password). By default the script
opens a Microsoft sign-in window (ActiveDirectoryInteractive) — sign in with your
student account. Override with the AZURE_SQL_CONN environment variable if needed.

  PowerShell (from the project folder, with the venv active):
    python python\04_load_azure_sql.py data\silver data\synthetic data\gold --init=sql\01_schema.sql,sql\02_gold.sql

  --init runs the listed SQL files first (drops and re-creates those objects).
  The gold dir is optional. To refresh only gold after re-running the analysis:
    python python\04_load_azure_sql.py data\silver data\synthetic data\gold --init=sql\02_gold.sql --only=rpt

Re-runnable: it empties the tables (children first) before loading.
Only real (non-computed) columns that exist in both the table and the file are loaded.
"""
import os
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pyodbc

import re
args = [a for a in sys.argv[1:] if not a.startswith("--")]
only = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--only=")), None)
init = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--init=")), None)
silver, synth = Path(args[0]), Path(args[1])
gold = Path(args[2]) if len(args) > 2 else None
SERVER = "sql-cairo-transit-mm.database.windows.net"
DATABASE = "cairo_transit"
# use the newest installed "ODBC Driver 1x for SQL Server" (17.2+ supports Entra sign-in)
_drivers = sorted(d for d in pyodbc.drivers() if re.fullmatch(r"ODBC Driver 1[78] for SQL Server", d))
if not _drivers and not os.environ.get("AZURE_SQL_CONN"):
    sys.exit(f"No ODBC Driver 17/18 for SQL Server found. Installed: {pyodbc.drivers()}")
DRIVER = _drivers[-1] if _drivers else ""
print(f"using driver: {DRIVER}")
conn_str = os.environ.get("AZURE_SQL_CONN") or (
    f"Driver={{{DRIVER}}};"
    f"Server=tcp:{SERVER},1433;Database={DATABASE};"
    "Authentication=ActiveDirectoryInteractive;"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=90;")

ORDER = [  # (schema.table, source file)
    ("gtfs.agency", silver / "agency.parquet"),
    ("gtfs.routes", silver / "routes.parquet"),
    ("gtfs.stops", silver / "stops.parquet"),
    ("gtfs.calendar", silver / "calendar.parquet"),
    ("gtfs.shapes", silver / "shapes.parquet"),
    ("gtfs.trips", silver / "trips.parquet"),
    ("gtfs.stop_times", silver / "stop_times.parquet"),
    ("gtfs.frequencies", silver / "frequencies.parquet"),
    ("gtfs.translations", silver / "translations.parquet"),
    ("gtfs.feed_info", silver / "feed_info.parquet"),
    ("app.riders", synth / "riders.parquet"),
    ("app.rides", synth / "rides.parquet"),
    ("app.safety_reports", synth / "safety_reports.parquet"),
]
if gold:
    ORDER += [("rpt.route_priority", gold / "route_priority.parquet"),
              ("rpt.stop_hotspots", gold / "stop_hotspots.parquet"),
              ("rpt.period_stage", gold / "period_stage.parquet")]
if only:
    ORDER = [(t, f) for t, f in ORDER if t.split(".")[0] == only]
BATCH = 20_000


def connect(retries=3):
    # serverless databases may be paused: the first connection wakes them (~1 min)
    for i in range(retries):
        try:
            return pyodbc.connect(conn_str, autocommit=False)
        except pyodbc.Error as e:
            msg = e.args[1] if len(e.args) > 1 else str(e)
            print(f"\nconnect attempt {i + 1} failed [{e.args[0]}]:\n  {msg}\n")
            if i < retries - 1:
                print("retrying in 20 s ...")
                time.sleep(20)
    sys.exit("could not connect - send the error text above.")


def table_columns(cur, full):
    schema, table = full.split(".")
    cur.execute("""SELECT c.name FROM sys.columns c
                   JOIN sys.tables t ON t.object_id = c.object_id
                   JOIN sys.schemas s ON s.schema_id = t.schema_id
                   WHERE s.name = ? AND t.name = ? AND c.is_computed = 0
                   ORDER BY c.column_id""", schema, table)
    return [r[0] for r in cur.fetchall()]


def py(v):
    if v is None or v is pd.NA or v is pd.NaT or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, np.generic):
        return v.item()
    return v


def to_rows(df):
    return [tuple(py(v) for v in row) for row in df.astype(object).itertuples(index=False, name=None)]


cn = connect()
cur = cn.cursor()
cur.fast_executemany = True

for sql_file in (init.split(",") if init else []):  # create / re-create tables and views
    batches = [b.strip() for b in re.split(r"^\s*GO\s*$", Path(sql_file).read_text(encoding="utf-8"),
                                            flags=re.M | re.I) if b.strip()]
    print(f"running {sql_file}: {len(batches)} batches ...")
    for b in batches:
        cur.execute(b)
        cn.commit()
if init:
    print("schema ready.")

print("emptying tables (children first) ...")
for full, _ in reversed(ORDER):
    cur.execute(f"DELETE FROM {full}")
cn.commit()

for full, path in ORDER:
    df = pd.read_parquet(path)
    cols = [c for c in table_columns(cur, full) if c in df.columns]
    skipped = sorted(set(df.columns) - set(cols))
    rows = to_rows(df[cols])
    sql = f"INSERT INTO {full} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    t0 = time.time()
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
        cn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {full}")
    n = cur.fetchone()[0]
    status = "OK" if n == len(df) else f"MISMATCH (file {len(df):,})"
    print(f"{full:22s} {n:>9,} rows  {time.time() - t0:6.1f}s  {status}"
          + (f"  | not loaded: {', '.join(skipped)}" if skipped else ""))

cn.close()
print("done.")
