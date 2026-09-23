CREATE TABLE IF NOT EXISTS import_runs (
    import_run_id BIGSERIAL PRIMARY KEY,

    import_type VARCHAR(50) NOT NULL,

    league_id INT,
    season INT,

    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,

    status VARCHAR(20) NOT NULL DEFAULT 'running',

    rows_received INT NOT NULL DEFAULT 0,
    rows_inserted INT NOT NULL DEFAULT 0,

    api_requests INT NOT NULL DEFAULT 0,

    error_message TEXT,

    CONSTRAINT fk_import_runs_league
        FOREIGN KEY (league_id)
        REFERENCES leagues(league_id),

    CONSTRAINT chk_import_runs_status
        CHECK (
            status IN (
                'running',
                'success',
                'partial',
                'failed'
            )
        )
);


CREATE INDEX IF NOT EXISTS idx_import_runs_type
    ON import_runs(import_type);


CREATE INDEX IF NOT EXISTS idx_import_runs_season
    ON import_runs(league_id, season);


CREATE INDEX IF NOT EXISTS idx_import_runs_started_at
    ON import_runs(started_at);


CREATE OR REPLACE VIEW season_data_summary AS

WITH statistics_per_fixture AS (

    SELECT
        fixture_id,
        COUNT(DISTINCT team_id) AS statistics_rows

    FROM fixture_statistics

    GROUP BY fixture_id
),

season_team_rows AS (

    SELECT
        league_id,
        season,
        home_team_id AS team_id

    FROM fixtures

    UNION

    SELECT
        league_id,
        season,
        away_team_id AS team_id

    FROM fixtures
),

season_team_counts AS (

    SELECT
        league_id,
        season,
        COUNT(DISTINCT team_id) AS teams

    FROM season_team_rows

    GROUP BY
        league_id,
        season
)

SELECT
    f.league_id,

    l.league_name,

    f.season,

    stc.teams,

    COUNT(*) AS total_fixtures,

    COUNT(*) FILTER (
        WHERE f.status = 'FT'
    ) AS finished_fixtures,

    COUNT(*) FILTER (
        WHERE
            f.status = 'FT'
            AND COALESCE(
                spf.statistics_rows,
                0
            ) = 2
    ) AS fixtures_with_complete_stats,

    COUNT(*) FILTER (
        WHERE
            f.status = 'FT'
            AND COALESCE(
                spf.statistics_rows,
                0
            ) = 1
    ) AS fixtures_with_partial_stats,

    COUNT(*) FILTER (
        WHERE
            f.status = 'FT'
            AND COALESCE(
                spf.statistics_rows,
                0
            ) = 0
    ) AS fixtures_without_stats,

    ROUND(
        (
            100.0
            * COUNT(*) FILTER (
                WHERE
                    f.status = 'FT'
                    AND COALESCE(
                        spf.statistics_rows,
                        0
                    ) = 2
            )
            / NULLIF(
                COUNT(*) FILTER (
                    WHERE f.status = 'FT'
                ),
                0
            )
        ),
        2
    ) AS statistics_coverage_percentage,

    MIN(f.match_date) AS first_match_date,

    MAX(f.match_date) AS last_match_date

FROM fixtures f

JOIN leagues l
    ON f.league_id = l.league_id

LEFT JOIN statistics_per_fixture spf
    ON f.fixture_id = spf.fixture_id

LEFT JOIN season_team_counts stc
    ON f.league_id = stc.league_id
    AND f.season = stc.season

GROUP BY
    f.league_id,
    l.league_name,
    f.season,
    stc.teams;


CREATE OR REPLACE VIEW fixture_data_status AS

WITH statistics_per_fixture AS (

    SELECT
        fixture_id,
        COUNT(DISTINCT team_id) AS statistics_rows

    FROM fixture_statistics

    GROUP BY fixture_id
)

SELECT
    f.fixture_id,

    f.league_id,
    f.season,

    f.match_date,

    home.team_name AS home_team,
    away.team_name AS away_team,

    f.status,

    f.home_goals,
    f.away_goals,

    COALESCE(
        spf.statistics_rows,
        0
    ) AS statistics_rows,

    CASE
        WHEN f.status != 'FT'
            THEN 'not_finished'

        WHEN COALESCE(
            spf.statistics_rows,
            0
        ) = 2
            THEN 'complete'

        WHEN COALESCE(
            spf.statistics_rows,
            0
        ) = 1
            THEN 'partial'

        ELSE 'missing'
    END AS data_status

FROM fixtures f

JOIN teams home
    ON f.home_team_id = home.team_id

JOIN teams away
    ON f.away_team_id = away.team_id

LEFT JOIN statistics_per_fixture spf
    ON f.fixture_id = spf.fixture_id;