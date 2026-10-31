/* =====================================================================
   GOLD layer — analysis outputs from python/05_analysis.py
   Power BI reads these directly. Re-runnable.
   ===================================================================== */
DROP TABLE IF EXISTS rpt.route_priority, rpt.stop_hotspots, rpt.period_stage;
GO

CREATE TABLE rpt.route_priority (
    route_id            NVARCHAR(100) NOT NULL PRIMARY KEY REFERENCES gtfs.routes(route_id),
    rides               INT           NOT NULL,
    reports             INT           NOT NULL,
    reports_per_1k      DECIMAL(8,3)  NULL,
    avg_severity        DECIMAL(5,3)  NULL,
    serious_share       DECIMAL(5,3)  NULL,   -- physical + following
    avg_felt_safe       DECIMAL(5,3)  NULL,
    avg_wait_min        DECIMAL(6,3)  NULL,
    peak_share          DECIMAL(5,3)  NULL,
    confidence          VARCHAR(10)   NOT NULL,  -- ok / low (< 200 rides)
    priority_score      DECIMAL(5,1)  NULL,
    priority_rank       INT           NULL,
    priority_tier       VARCHAR(30)   NOT NULL,
    agency_id           NVARCHAR(100) NULL,
    route_short_name    NVARCHAR(100) NULL,
    route_long_name     NVARCHAR(500) NULL,
    route_short_name_ar NVARCHAR(100) NULL,
    route_long_name_ar  NVARCHAR(500) NULL,
    agency_name         NVARCHAR(255) NULL,
    agency_name_ar      NVARCHAR(255) NULL
);

CREATE TABLE rpt.stop_hotspots (
    stop_id                  NVARCHAR(100) NOT NULL PRIMARY KEY REFERENCES gtfs.stops(stop_id),
    stop_name                NVARCHAR(255) NULL,
    stop_name_ar             NVARCHAR(255) NULL,
    stop_lat                 DECIMAL(9,6)  NOT NULL,
    stop_lon                 DECIMAL(9,6)  NOT NULL,
    boardings                INT           NOT NULL,
    reports                  INT           NOT NULL,
    avg_severity             DECIMAL(4,2)  NULL,
    reports_per_1k_boardings DECIMAL(8,1)  NULL
);

CREATE TABLE rpt.period_stage (
    period          VARCHAR(10) NOT NULL,
    journey_stage   VARCHAR(20) NOT NULL,
    reports         INT         NOT NULL,
    rides_in_period INT         NOT NULL,
    reports_per_1k  DECIMAL(8,2) NOT NULL,
    CONSTRAINT pk_period_stage PRIMARY KEY (period, journey_stage)
);
GO
