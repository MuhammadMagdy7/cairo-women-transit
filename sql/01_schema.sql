/* =====================================================================
   Cairo Women-Only Transit — Graduation Project Schema
   Target : Azure SQL Database (T-SQL)
   Source : Transport for Cairo GTFS feed (Greater Cairo, 2025)
            Profiled: 11 agencies, 1,011 routes, 2,997 stops, 1,784 trips,
            44,743 stop_times, 6,432 frequencies, 531,958 shape points.
            Road-based only (route_type = 3) — no metro in this feed.
            + project tables (riders / rides / safety reports)
   Layers :
     gtfs.*  → raw GTFS tables, 1:1 with the .txt files
     app.*   → your own data (synthetic or survey) for the women-only use case
     rpt.*   → dimension + views that Power BI connects to
   NOTE    : Columns match the real feed headers (checked 2026-10-29).
             Extra spec columns are kept NULL-able for future feeds.
   ===================================================================== */

/* ---------- 0. Schemas ---------- */
IF SCHEMA_ID('gtfs') IS NULL EXEC('CREATE SCHEMA gtfs');
IF SCHEMA_ID('app')  IS NULL EXEC('CREATE SCHEMA app');
IF SCHEMA_ID('rpt')  IS NULL EXEC('CREATE SCHEMA rpt');
GO

/* ---------- Clean re-run (children first) ---------- */
DROP VIEW  IF EXISTS rpt.vw_route_safety, rpt.vw_stop_activity, rpt.vw_route_frequency;
DROP TABLE IF EXISTS app.safety_reports, app.rides, app.riders;
DROP TABLE IF EXISTS rpt.dim_date;
DROP TABLE IF EXISTS gtfs.translations,
                     gtfs.feed_info, gtfs.frequencies, gtfs.stop_times,
                     gtfs.trips, gtfs.shapes, gtfs.calendar, gtfs.stops,
                     gtfs.routes, gtfs.agency;
GO

/* =====================================================================
   1. GTFS LAYER
   ===================================================================== */

CREATE TABLE gtfs.agency (
    agency_id        NVARCHAR(100)  NOT NULL PRIMARY KEY,
    agency_name      NVARCHAR(255)  NOT NULL,   -- CTA, Microbus 14-seater, ...
    agency_name_ar   NVARCHAR(255)  NULL,
    agency_url       NVARCHAR(500)  NULL,
    agency_timezone  NVARCHAR(50)   NOT NULL,   -- Africa/Cairo
    agency_lang      NVARCHAR(10)   NULL,
    agency_phone     NVARCHAR(50)   NULL
);

CREATE TABLE gtfs.routes (
    route_id           NVARCHAR(100) NOT NULL PRIMARY KEY,
    agency_id          NVARCHAR(100) NULL
        REFERENCES gtfs.agency(agency_id),
    route_short_name   NVARCHAR(100) NULL,
    route_long_name    NVARCHAR(500) NULL,
    route_short_name_ar NVARCHAR(100) NULL,
    route_long_name_ar NVARCHAR(500) NULL,
    route_desc         NVARCHAR(1000) NULL,
    route_type         SMALLINT      NOT NULL,  -- 3 = bus (only value in feed)
    route_color        CHAR(6)       NULL,
    route_text_color   CHAR(6)       NULL,
    continuous_pickup  TINYINT       NULL,      -- feed uses Continuous Stops
    continuous_drop_off TINYINT      NULL
);

CREATE TABLE gtfs.stops (
    stop_id        NVARCHAR(100) NOT NULL PRIMARY KEY,
    stop_code      NVARCHAR(50)  NULL,
    stop_name      NVARCHAR(255) NULL,
    stop_name_ar   NVARCHAR(255) NULL,
    stop_desc      NVARCHAR(1000) NULL,
    stop_lat       DECIMAL(9,6)  NOT NULL,
    stop_lon       DECIMAL(9,6)  NOT NULL,
    zone_id        NVARCHAR(100) NULL,
    location_type  TINYINT       NULL,          -- 0 stop, 1 station
    parent_station NVARCHAR(100) NULL
        REFERENCES gtfs.stops(stop_id),
    geo AS geography::Point(stop_lat, stop_lon, 4326)  -- for spatial queries
);

CREATE TABLE gtfs.calendar (
    service_id  NVARCHAR(100) NOT NULL PRIMARY KEY,
    monday      BIT NOT NULL, tuesday  BIT NOT NULL, wednesday BIT NOT NULL,
    thursday    BIT NOT NULL, friday   BIT NOT NULL, saturday  BIT NOT NULL,
    sunday      BIT NOT NULL,
    start_date  DATE NOT NULL,   -- GTFS gives YYYYMMDD → convert in loader
    end_date    DATE NOT NULL
);

/* shapes has a composite key (shape_id + sequence), so trips.shape_id
   cannot hold a real FK to it — join on shape_id in queries instead. */
CREATE TABLE gtfs.shapes (
    shape_id            NVARCHAR(100) NOT NULL,
    shape_pt_sequence   INT           NOT NULL,
    shape_pt_lat        DECIMAL(9,6)  NOT NULL,
    shape_pt_lon        DECIMAL(9,6)  NOT NULL,
    shape_dist_traveled FLOAT         NULL,
    CONSTRAINT pk_shapes PRIMARY KEY (shape_id, shape_pt_sequence)
);

CREATE TABLE gtfs.trips (
    trip_id        NVARCHAR(100) NOT NULL PRIMARY KEY,
    route_id       NVARCHAR(100) NOT NULL
        REFERENCES gtfs.routes(route_id),
    service_id     NVARCHAR(100) NOT NULL
        REFERENCES gtfs.calendar(service_id),
    trip_headsign  NVARCHAR(255) NULL,
    trip_headsign_ar NVARCHAR(255) NULL,
    direction_id   TINYINT       NULL,
    shape_id       NVARCHAR(100) NULL
);
CREATE INDEX ix_trips_route   ON gtfs.trips(route_id);
CREATE INDEX ix_trips_service ON gtfs.trips(service_id);
CREATE INDEX ix_trips_shape   ON gtfs.trips(shape_id);

/* GTFS times can exceed 24:00:00 (after-midnight trips), so they are kept
   as text and exposed as seconds-after-midnight for maths. */
CREATE TABLE gtfs.stop_times (
    trip_id        NVARCHAR(100) NOT NULL
        REFERENCES gtfs.trips(trip_id),
    stop_sequence  INT           NOT NULL,
    stop_id        NVARCHAR(100) NOT NULL
        REFERENCES gtfs.stops(stop_id),
    arrival_time   VARCHAR(8)    NULL,
    departure_time VARCHAR(8)    NULL,
    departure_secs INT           NULL,
    timepoint      TINYINT       NULL,
    continuous_pickup   TINYINT  NULL,
    continuous_drop_off TINYINT  NULL,
    arrival_secs AS (
        CAST(PARSENAME(REPLACE(arrival_time, ':', '.'), 3) AS INT) * 3600
      + CAST(PARSENAME(REPLACE(arrival_time, ':', '.'), 2) AS INT) * 60
      + CAST(PARSENAME(REPLACE(arrival_time, ':', '.'), 1) AS INT)),
    CONSTRAINT pk_stop_times PRIMARY KEY (trip_id, stop_sequence)
);
CREATE INDEX ix_stop_times_stop ON gtfs.stop_times(stop_id);

/* Paratransit in Cairo is frequency-based (a microbus every N minutes),
   so this table — not trip counts — is the real measure of service. */
CREATE TABLE gtfs.frequencies (
    trip_id      NVARCHAR(100) NOT NULL
        REFERENCES gtfs.trips(trip_id),
    start_time   VARCHAR(8)    NOT NULL,
    end_time     VARCHAR(8)    NOT NULL,
    headway_secs INT           NOT NULL CHECK (headway_secs > 0),
    exact_times  TINYINT       NULL,
    start_secs AS (
        CAST(PARSENAME(REPLACE(start_time, ':', '.'), 3) AS INT) * 3600
      + CAST(PARSENAME(REPLACE(start_time, ':', '.'), 2) AS INT) * 60
      + CAST(PARSENAME(REPLACE(start_time, ':', '.'), 1) AS INT)),
    end_secs AS (
        CAST(PARSENAME(REPLACE(end_time, ':', '.'), 3) AS INT) * 3600
      + CAST(PARSENAME(REPLACE(end_time, ':', '.'), 2) AS INT) * 60
      + CAST(PARSENAME(REPLACE(end_time, ':', '.'), 1) AS INT)),
    CONSTRAINT pk_frequencies PRIMARY KEY (trip_id, start_time)
);

/* Arabic names: matched by field_value (feed has no record_id) */
CREATE TABLE gtfs.translations (
    table_name    NVARCHAR(50)   NOT NULL,
    field_name    NVARCHAR(50)   NOT NULL,
    language      NVARCHAR(10)   NOT NULL,
    translation   NVARCHAR(1000) NOT NULL,
    record_id     NVARCHAR(100)  NULL,
    record_sub_id NVARCHAR(100)  NULL,
    field_value   NVARCHAR(1000) NULL
);
CREATE INDEX ix_translations_lookup
    ON gtfs.translations(table_name, field_name, language);

CREATE TABLE gtfs.feed_info (
    feed_publisher_name NVARCHAR(255) NOT NULL,
    feed_publisher_url  NVARCHAR(500) NULL,
    feed_lang           NVARCHAR(10)  NULL,
    feed_start_date     DATE          NULL,
    feed_end_date       DATE          NULL,
    feed_version        NVARCHAR(100) NULL
);

GO

/* =====================================================================
   2. APP LAYER — women-only transit use case
      Not in the GTFS feed. Fill with synthetic data (Python/Faker) or a
      small survey, and say so clearly in the project report.
      Keep personal data minimal: no names, phones or exact addresses.
   ===================================================================== */

CREATE TABLE app.riders (
    rider_id       INT NOT NULL PRIMARY KEY,      -- ids come from the generator
    age_group      VARCHAR(10)  NOT NULL
        CHECK (age_group IN ('18-24','25-34','35-44','45-54','55+')),
    home_stop_id   NVARCHAR(100) NULL REFERENCES gtfs.stops(stop_id),
    occupation     NVARCHAR(50)  NULL,           -- student, employee, ...
    signup_date    DATE          NOT NULL
);

CREATE TABLE app.rides (
    ride_id         BIGINT NOT NULL PRIMARY KEY,
    rider_id        INT           NOT NULL REFERENCES app.riders(rider_id),
    route_id        NVARCHAR(100) NOT NULL REFERENCES gtfs.routes(route_id),
    board_stop_id   NVARCHAR(100) NOT NULL REFERENCES gtfs.stops(stop_id),
    alight_stop_id  NVARCHAR(100) NOT NULL REFERENCES gtfs.stops(stop_id),
    period          VARCHAR(10)   NOT NULL,     -- AM peak / Midday / PM peak / Evening
    board_datetime  DATETIME2(0)  NOT NULL,
    wait_minutes    SMALLINT      NULL CHECK (wait_minutes >= 0),
    fare_egp        DECIMAL(8,2)  NULL,
    felt_safe_score TINYINT       NULL CHECK (felt_safe_score BETWEEN 1 AND 5),
    ride_date AS CAST(board_datetime AS DATE) PERSISTED
);
CREATE INDEX ix_rides_route ON app.rides(route_id, ride_date);
CREATE INDEX ix_rides_board ON app.rides(board_stop_id);

CREATE TABLE app.safety_reports (
    report_id        BIGINT NOT NULL PRIMARY KEY,
    report_datetime  DATETIME2(0)  NOT NULL,
    rider_id         INT           NULL REFERENCES app.riders(rider_id),
    ride_id          BIGINT        NULL REFERENCES app.rides(ride_id),
    route_id         NVARCHAR(100) NULL REFERENCES gtfs.routes(route_id),
    nearest_stop_id  NVARCHAR(100) NULL REFERENCES gtfs.stops(stop_id),
    journey_stage    VARCHAR(20)   NOT NULL
        CHECK (journey_stage IN ('walk_to_stop','waiting','boarding','on_board','alighting')),
    incident_type    VARCHAR(30)   NOT NULL
        CHECK (incident_type IN ('verbal','staring','following','physical','overcrowding','other')),
    severity         TINYINT       NOT NULL CHECK (severity BETWEEN 1 AND 5),
    source           VARCHAR(20)   NOT NULL
        CHECK (source IN ('synthetic','survey','harassmap')),
    lat              DECIMAL(9,6)  NULL,
    lon              DECIMAL(9,6)  NULL,
    report_date AS CAST(report_datetime AS DATE) PERSISTED
);
CREATE INDEX ix_reports_route ON app.safety_reports(route_id, report_date);
CREATE INDEX ix_reports_stop  ON app.safety_reports(nearest_stop_id);
CREATE INDEX ix_reports_ride  ON app.safety_reports(ride_id);
CREATE INDEX ix_rides_rider   ON app.rides(rider_id);
GO

/* =====================================================================
   3. REPORTING LAYER — what Power BI reads
   ===================================================================== */

CREATE TABLE rpt.dim_date (
    date_key      INT  NOT NULL PRIMARY KEY,    -- 20250101
    [date]        DATE NOT NULL UNIQUE,
    [year]        SMALLINT NOT NULL,
    [month]       TINYINT  NOT NULL,
    month_name    NVARCHAR(20) NOT NULL,
    day_of_week   TINYINT  NOT NULL,            -- 1 = Saturday (Egypt week)
    day_name      NVARCHAR(20) NOT NULL,
    is_weekend    BIT NOT NULL                  -- Friday + Saturday
);

/* Fill Dec 2024 – 2026 (signups start Dec 2024). Uses DATEFIRST-independent weekday maths. */
WITH n AS (
    SELECT TOP (DATEDIFF(DAY, '2024-12-01', '2026-12-31') + 1)
           ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS i
    FROM sys.all_objects a CROSS JOIN sys.all_objects b
), d AS (
    SELECT DATEADD(DAY, i, CAST('2024-12-01' AS DATE)) AS dt FROM n
)
INSERT INTO rpt.dim_date
SELECT  CONVERT(INT, FORMAT(dt, 'yyyyMMdd')),
        dt,
        YEAR(dt),
        MONTH(dt),
        DATENAME(MONTH, dt),
        (DATEDIFF(DAY, '1900-01-06', dt) % 7) + 1,   -- 1900-01-06 was a Saturday
        DATENAME(WEEKDAY, dt),
        CASE WHEN DATEDIFF(DAY, '1900-01-06', dt) % 7 IN (0, 6) THEN 1 ELSE 0 END
FROM d;
GO

/* Service level per route & time window.
   vehicles_in_window = window length / headway */
CREATE VIEW rpt.vw_route_frequency AS
SELECT  r.route_id,
        r.route_short_name,
        r.route_long_name,
        a.agency_name,
        f.start_time,
        f.end_time,
        f.headway_secs / 60.0                         AS headway_min,
        (f.end_secs - f.start_secs) / f.headway_secs  AS vehicles_in_window,
        -- feed uses 4 fixed windows: 06-10, 10-15, 15-19, 19-23
        CASE f.start_time
            WHEN '06:00:00' THEN '1 AM peak'
            WHEN '10:00:00' THEN '2 Midday'
            WHEN '15:00:00' THEN '3 PM peak'
            WHEN '19:00:00' THEN '4 Evening'
            ELSE '5 Other'
        END                                           AS period
FROM gtfs.frequencies f
JOIN gtfs.trips  t ON t.trip_id  = f.trip_id
JOIN gtfs.routes r ON r.route_id = t.route_id
LEFT JOIN gtfs.agency a ON a.agency_id = r.agency_id;
GO

/* How busy each stop is as a network node */
CREATE VIEW rpt.vw_stop_activity AS
SELECT  s.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        COUNT(DISTINCT t.route_id) AS routes_serving,
        COUNT(*)                   AS trip_stop_events
FROM gtfs.stops s
JOIN gtfs.stop_times st ON st.stop_id = s.stop_id
JOIN gtfs.trips      t  ON t.trip_id  = st.trip_id
GROUP BY s.stop_id, s.stop_name, s.stop_lat, s.stop_lon;
GO

/* Core question of the project: which routes need a women-only service first?
   reports_per_1k_rides normalises for how busy a route is. */
CREATE VIEW rpt.vw_route_safety AS
WITH rides AS (
    SELECT route_id,
           COUNT(*)              AS rides,
           AVG(felt_safe_score*1.0) AS avg_felt_safe
    FROM app.rides GROUP BY route_id
), reps AS (
    SELECT route_id,
           COUNT(*)              AS reports,
           AVG(severity*1.0)     AS avg_severity
    FROM app.safety_reports WHERE route_id IS NOT NULL GROUP BY route_id
)
SELECT  r.route_id,
        r.route_short_name,
        r.route_long_name,
        ISNULL(rd.rides, 0)    AS rides,
        ISNULL(rp.reports, 0)  AS reports,
        rp.avg_severity,
        rd.avg_felt_safe,
        CASE WHEN rd.rides > 0
             THEN rp.reports * 1000.0 / rd.rides END AS reports_per_1k_rides
FROM gtfs.routes r
LEFT JOIN rides rd ON rd.route_id = r.route_id
LEFT JOIN reps  rp ON rp.route_id = r.route_id;
GO

/* =====================================================================
   LOAD ORDER (parents before children, or the FKs will reject rows):
     agency → routes → stops → calendar → shapes → trips
     → stop_times → frequencies → translations / feed_info
     → app.riders → app.rides → app.safety_reports
   stop_times is by far the largest file — load it with bulk insert
   (pandas + fast_executemany, or BULK INSERT from Blob Storage).
   ===================================================================== */
