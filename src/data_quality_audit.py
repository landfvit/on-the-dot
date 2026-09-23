import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_LEAGUE_ID = 39
DEFAULT_SEASON = 2024

COMPLETED_STATUSES = (
    "FT",
    "AET",
    "PEN",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Audit imported football data "
            "for one league season."
        )
    )

    parser.add_argument(
        "--league-id",
        type=int,
        default=DEFAULT_LEAGUE_ID,
    )

    parser.add_argument(
        "--season",
        type=int,
        default=DEFAULT_SEASON,
    )

    return parser.parse_args()


def load_environment():
    load_dotenv(
        PROJECT_ROOT / ".env"
    )


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


def scalar(
    conn,
    query,
    params,
    column="value",
):
    row = conn.execute(
        query,
        params,
    ).fetchone()

    if not row:
        return 0

    return row[
        column
    ]


def print_section(title):
    print()

    print(
        title
    )

    print(
        "=" * len(
            title
        )
    )


def print_metric(
    label,
    value,
):
    print(
        f"{label:<40} {value}"
    )


def print_check(
    label,
    passed,
    value=None,
):
    status = (
        "PASS"
        if passed
        else "WARN"
    )

    text = (
        f"[{status}] "
        f"{label}"
    )

    if value is not None:
        text += (
            f": {value}"
        )

    print(
        text
    )


def get_fixture_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            COUNT(*) AS fixtures_total,

            COUNT(*) FILTER (
                WHERE status = ANY(%s)
            ) AS fixtures_completed,

            COUNT(*) FILTER (
                WHERE status = 'NS'
            ) AS fixtures_not_started,

            COUNT(*) FILTER (
                WHERE status = 'PST'
            ) AS fixtures_postponed,

            COUNT(*) FILTER (
                WHERE home_goals IS NULL
                OR away_goals IS NULL
            ) AS fixtures_missing_score,

            COUNT(*) FILTER (
                WHERE venue_id IS NULL
            ) AS fixtures_missing_venue,

            COUNT(*) FILTER (
                WHERE referee IS NULL
            ) AS fixtures_missing_referee

        FROM fixtures

        WHERE
            league_id = %s
            AND season = %s
        """,
        (
            list(
                COMPLETED_STATUSES
            ),
            league_id,
            season,
        ),
    ).fetchone()


def get_team_count(
    conn,
    league_id,
    season,
):
    return scalar(
        conn,
        """
        SELECT COUNT(
            DISTINCT team_id
        ) AS value

        FROM (
            SELECT home_team_id AS team_id
            FROM fixtures
            WHERE
                league_id = %s
                AND season = %s

            UNION

            SELECT away_team_id AS team_id
            FROM fixtures
            WHERE
                league_id = %s
                AND season = %s
        ) teams
        """,
        (
            league_id,
            season,
            league_id,
            season,
        ),
    )


def get_raw_data_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            COUNT(
                DISTINCT f.fixture_id
            ) FILTER (
                WHERE frd.data_type = 'fixture_base'
            ) AS base_fixtures,

            COUNT(
                DISTINCT f.fixture_id
            ) FILTER (
                WHERE frd.data_type = 'fixture_complete'
            ) AS complete_fixtures

        FROM fixtures f

        LEFT JOIN fixture_raw_data frd
            ON frd.fixture_id = f.fixture_id
            AND frd.source = 'api-football'

        WHERE
            f.league_id = %s
            AND f.season = %s
        """,
        (
            league_id,
            season,
        ),
    ).fetchone()


def get_team_statistics_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        WITH per_fixture AS (
            SELECT
                f.fixture_id,
                COUNT(fs.team_id) AS stat_rows

            FROM fixtures f

            LEFT JOIN fixture_statistics fs
                ON fs.fixture_id = f.fixture_id

            WHERE
                f.league_id = %s
                AND f.season = %s
                AND f.status = ANY(%s)

            GROUP BY
                f.fixture_id
        )

        SELECT
            COUNT(*) AS completed_fixtures,

            COALESCE(
                SUM(stat_rows),
                0
            ) AS total_stat_rows,

            COUNT(*) FILTER (
                WHERE stat_rows = 2
            ) AS fixtures_with_two_rows,

            COUNT(*) FILTER (
                WHERE stat_rows = 0
            ) AS fixtures_without_stats,

            COUNT(*) FILTER (
                WHERE stat_rows <> 2
            ) AS fixtures_with_unexpected_count

        FROM per_fixture
        """,
        (
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
        ),
    ).fetchone()


def get_event_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            COUNT(fe.fixture_event_id) AS events_total,

            COUNT(
                DISTINCT fe.fixture_id
            ) AS fixtures_with_events,

            COUNT(*) FILTER (
                WHERE fe.elapsed_minute < 0
            ) AS negative_elapsed_minutes,

            COUNT(*) FILTER (
                WHERE fe.elapsed_minute IS NULL
            ) AS missing_elapsed_minutes

        FROM fixtures f

        LEFT JOIN fixture_events fe
            ON fe.fixture_id = f.fixture_id

        WHERE
            f.league_id = %s
            AND f.season = %s
        """,
        (
            league_id,
            season,
        ),
    ).fetchone()


def get_lineup_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        WITH lineup_counts AS (
            SELECT
                f.fixture_id,

                COUNT(
                    fl.team_id
                ) AS lineup_rows

            FROM fixtures f

            LEFT JOIN fixture_lineups fl
                ON fl.fixture_id = f.fixture_id

            WHERE
                f.league_id = %s
                AND f.season = %s
                AND f.status = ANY(%s)

            GROUP BY
                f.fixture_id
        ),

        starter_counts AS (
            SELECT
                f.fixture_id,

                COUNT(
                    flp.player_id
                ) FILTER (
                    WHERE
                        flp.lineup_type
                        = 'start_xi'
                ) AS starter_count

            FROM fixtures f

            LEFT JOIN fixture_lineup_players flp
                ON flp.fixture_id = f.fixture_id

            WHERE
                f.league_id = %s
                AND f.season = %s
                AND f.status = ANY(%s)

            GROUP BY
                f.fixture_id
        )

        SELECT
            COUNT(*) AS completed_fixtures,

            COUNT(*) FILTER (
                WHERE lc.lineup_rows = 2
            ) AS fixtures_with_two_lineups,

            COUNT(*) FILTER (
                WHERE lc.lineup_rows = 0
            ) AS fixtures_without_lineups,

            COUNT(*) FILTER (
                WHERE sc.starter_count = 22
            ) AS fixtures_with_22_starters,

            COUNT(*) FILTER (
                WHERE sc.starter_count = 0
            ) AS fixtures_without_starters,

            COUNT(*) FILTER (
                WHERE
                    sc.starter_count <> 22
                    AND sc.starter_count <> 0
            ) AS fixtures_with_unusual_starter_count

        FROM lineup_counts lc

        JOIN starter_counts sc
            ON sc.fixture_id = lc.fixture_id
        """,
        (
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
        ),
    ).fetchone()


def get_player_statistics_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        WITH per_fixture AS (
            SELECT
                f.fixture_id,

                COUNT(
                    fps.player_id
                ) AS player_rows

            FROM fixtures f

            LEFT JOIN fixture_player_statistics fps
                ON fps.fixture_id = f.fixture_id

            WHERE
                f.league_id = %s
                AND f.season = %s
                AND f.status = ANY(%s)

            GROUP BY
                f.fixture_id
        )

        SELECT
            COUNT(*) AS completed_fixtures,

            COALESCE(
                SUM(player_rows),
                0
            ) AS player_stat_rows,

            COUNT(*) FILTER (
                WHERE player_rows > 0
            ) AS fixtures_with_player_stats,

            COUNT(*) FILTER (
                WHERE player_rows = 0
            ) AS fixtures_without_player_stats,

            ROUND(
                AVG(
                    player_rows
                ),
                2
            ) AS avg_players_per_fixture,

            MIN(
                player_rows
            ) AS min_players_per_fixture,

            MAX(
                player_rows
            ) AS max_players_per_fixture

        FROM per_fixture
        """,
        (
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
        ),
    ).fetchone()


def get_venue_summary(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        WITH season_venues AS (
            SELECT DISTINCT
                f.venue_id

            FROM fixtures f

            WHERE
                f.league_id = %s
                AND f.season = %s
                AND f.venue_id IS NOT NULL
        )

        SELECT
            COUNT(
                sv.venue_id
            ) AS venue_count,

            COUNT(*) FILTER (
                WHERE v.capacity IS NULL
            ) AS venues_without_capacity,

            COUNT(*) FILTER (
                WHERE v.city IS NULL
            ) AS venues_without_city,

            COUNT(*) FILTER (
                WHERE v.surface IS NULL
            ) AS venues_without_surface

        FROM season_venues sv

        LEFT JOIN venues v
            ON v.venue_id = sv.venue_id
        """,
        (
            league_id,
            season,
        ),
    ).fetchone()


def get_score_consistency(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE
                    status = 'FT'
                    AND (
                        fulltime_home
                        IS DISTINCT FROM
                        home_goals

                        OR

                        fulltime_away
                        IS DISTINCT FROM
                        away_goals
                    )
            ) AS fulltime_score_mismatches,

            COUNT(*) FILTER (
                WHERE
                    status = ANY(%s)
                    AND (
                        home_goals IS NULL
                        OR away_goals IS NULL
                    )
            ) AS completed_missing_final_score

        FROM fixtures

        WHERE
            league_id = %s
            AND season = %s
        """,
        (
            list(
                COMPLETED_STATUSES
            ),
            league_id,
            season,
        ),
    ).fetchone()


def get_orphan_player_count(
    conn,
    league_id,
    season,
):
    return scalar(
        conn,
        """
        SELECT COUNT(
            DISTINCT fps.player_id
        ) AS value

        FROM fixture_player_statistics fps

        JOIN fixtures f
            ON f.fixture_id = fps.fixture_id

        LEFT JOIN players p
            ON p.player_id = fps.player_id

        WHERE
            f.league_id = %s
            AND f.season = %s
            AND p.player_id IS NULL
        """,
        (
            league_id,
            season,
        ),
    )


def get_import_run(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            import_run_id,
            status,
            started_at,
            finished_at,
            rows_received,
            rows_inserted,
            api_requests,
            error_message

        FROM import_runs

        WHERE
            import_type = 'history_match_bulk'
            AND league_id = %s
            AND season = %s

        ORDER BY
            import_run_id DESC

        LIMIT 1
        """,
        (
            league_id,
            season,
        ),
    ).fetchone()


def main():
    args = parse_args()

    load_environment()

    league_id = (
        args.league_id
    )

    season = (
        args.season
    )

    season_label = (
        f"{season}/"
        f"{str(season + 1)[-2:]}"
    )

    with get_connection() as conn:
        fixtures = get_fixture_summary(
            conn,
            league_id,
            season,
        )

        team_count = get_team_count(
            conn,
            league_id,
            season,
        )

        raw_data = get_raw_data_summary(
            conn,
            league_id,
            season,
        )

        team_stats = (
            get_team_statistics_summary(
                conn,
                league_id,
                season,
            )
        )

        events = get_event_summary(
            conn,
            league_id,
            season,
        )

        lineups = get_lineup_summary(
            conn,
            league_id,
            season,
        )

        player_stats = (
            get_player_statistics_summary(
                conn,
                league_id,
                season,
            )
        )

        venues = get_venue_summary(
            conn,
            league_id,
            season,
        )

        scores = get_score_consistency(
            conn,
            league_id,
            season,
        )

        orphan_players = (
            get_orphan_player_count(
                conn,
                league_id,
                season,
            )
        )

        import_run = get_import_run(
            conn,
            league_id,
            season,
        )

    print()

    print(
        "Premier League data quality audit"
    )

    print(
        f"Season: {season_label}"
    )

    print(
        f"League ID: {league_id}"
    )


    print_section(
        "Fixtures"
    )

    print_metric(
        "Total fixtures",
        fixtures[
            "fixtures_total"
        ],
    )

    print_metric(
        "Completed fixtures",
        fixtures[
            "fixtures_completed"
        ],
    )

    print_metric(
        "Not started",
        fixtures[
            "fixtures_not_started"
        ],
    )

    print_metric(
        "Postponed",
        fixtures[
            "fixtures_postponed"
        ],
    )

    print_metric(
        "Distinct teams",
        team_count,
    )

    expected_fixtures = (
        team_count
        * (
            team_count - 1
        )
        if team_count
        else 0
    )

    print_metric(
        "Expected double round-robin fixtures",
        expected_fixtures,
    )

    print_check(
        "Fixture count matches league format",
        (
            fixtures[
                "fixtures_total"
            ]
            == expected_fixtures
        ),
        (
            f"{fixtures['fixtures_total']}"
            f"/{expected_fixtures}"
        ),
    )

    print_check(
        "No completed fixtures missing score",
        (
            fixtures[
                "fixtures_missing_score"
            ]
            == 0
        ),
        fixtures[
            "fixtures_missing_score"
        ],
    )

    print_check(
        "Every fixture has a venue",
        (
            fixtures[
                "fixtures_missing_venue"
            ]
            == 0
        ),
        fixtures[
            "fixtures_missing_venue"
        ],
    )

    print_metric(
        "Fixtures without referee",
        fixtures[
            "fixtures_missing_referee"
        ],
    )


    print_section(
        "Raw API payloads"
    )

    print_metric(
        "Fixtures with fixture_base",
        raw_data[
            "base_fixtures"
        ],
    )

    print_metric(
        "Fixtures with fixture_complete",
        raw_data[
            "complete_fixtures"
        ],
    )

    print_check(
        "All fixtures have base payload",
        (
            raw_data[
                "base_fixtures"
            ]
            == fixtures[
                "fixtures_total"
            ]
        ),
        (
            f"{raw_data['base_fixtures']}"
            f"/{fixtures['fixtures_total']}"
        ),
    )

    print_check(
        "All completed fixtures have complete payload",
        (
            raw_data[
                "complete_fixtures"
            ]
            == fixtures[
                "fixtures_completed"
            ]
        ),
        (
            f"{raw_data['complete_fixtures']}"
            f"/{fixtures['fixtures_completed']}"
        ),
    )


    print_section(
        "Team fixture statistics"
    )

    expected_stat_rows = (
        team_stats[
            "completed_fixtures"
        ]
        * 2
    )

    print_metric(
        "Statistic rows",
        team_stats[
            "total_stat_rows"
        ],
    )

    print_metric(
        "Expected statistic rows",
        expected_stat_rows,
    )

    print_metric(
        "Fixtures with exactly 2 team rows",
        team_stats[
            "fixtures_with_two_rows"
        ],
    )

    print_metric(
        "Fixtures without team statistics",
        team_stats[
            "fixtures_without_stats"
        ],
    )

    print_check(
        "Every completed fixture has 2 team-stat rows",
        (
            team_stats[
                "fixtures_with_unexpected_count"
            ]
            == 0
        ),
        team_stats[
            "fixtures_with_unexpected_count"
        ],
    )


    print_section(
        "Events"
    )

    print_metric(
        "Total events",
        events[
            "events_total"
        ],
    )

    print_metric(
        "Fixtures with events",
        events[
            "fixtures_with_events"
        ],
    )

    print_metric(
        "Negative elapsed-minute values",
        events[
            "negative_elapsed_minutes"
        ],
    )

    print_metric(
        "Events without elapsed minute",
        events[
            "missing_elapsed_minutes"
        ],
    )

    if (
        events[
            "negative_elapsed_minutes"
        ]
        > 0
    ):
        print(
            "[INFO] Negative event times are "
            "preserved exactly from the provider."
        )


    print_section(
        "Lineups"
    )

    print_metric(
        "Completed fixtures",
        lineups[
            "completed_fixtures"
        ],
    )

    print_metric(
        "Fixtures with 2 team lineups",
        lineups[
            "fixtures_with_two_lineups"
        ],
    )

    print_metric(
        "Fixtures without lineups",
        lineups[
            "fixtures_without_lineups"
        ],
    )

    print_metric(
        "Fixtures with exactly 22 starters",
        lineups[
            "fixtures_with_22_starters"
        ],
    )

    print_metric(
        "Fixtures without starters",
        lineups[
            "fixtures_without_starters"
        ],
    )

    print_metric(
        "Fixtures with unusual starter count",
        lineups[
            "fixtures_with_unusual_starter_count"
        ],
    )

    print_check(
        "Every completed fixture has 2 lineups",
        (
            lineups[
                "fixtures_without_lineups"
            ]
            == 0
        ),
        lineups[
            "fixtures_without_lineups"
        ],
    )


    print_section(
        "Fixture player statistics"
    )

    print_metric(
        "Player-stat rows",
        player_stats[
            "player_stat_rows"
        ],
    )

    print_metric(
        "Fixtures with player statistics",
        player_stats[
            "fixtures_with_player_stats"
        ],
    )

    print_metric(
        "Fixtures without player statistics",
        player_stats[
            "fixtures_without_player_stats"
        ],
    )

    print_metric(
        "Average players per fixture",
        player_stats[
            "avg_players_per_fixture"
        ],
    )

    print_metric(
        "Minimum players in one fixture",
        player_stats[
            "min_players_per_fixture"
        ],
    )

    print_metric(
        "Maximum players in one fixture",
        player_stats[
            "max_players_per_fixture"
        ],
    )

    print_check(
        "Every completed fixture has player stats",
        (
            player_stats[
                "fixtures_without_player_stats"
            ]
            == 0
        ),
        player_stats[
            "fixtures_without_player_stats"
        ],
    )


    print_section(
        "Venues"
    )

    print_metric(
        "Distinct venues",
        venues[
            "venue_count"
        ],
    )

    print_metric(
        "Venues without capacity",
        venues[
            "venues_without_capacity"
        ],
    )

    print_metric(
        "Venues without city",
        venues[
            "venues_without_city"
        ],
    )

    print_metric(
        "Venues without surface",
        venues[
            "venues_without_surface"
        ],
    )


    print_section(
        "Score consistency"
    )

    print_check(
        "FT score equals final fixture goals",
        (
            scores[
                "fulltime_score_mismatches"
            ]
            == 0
        ),
        scores[
            "fulltime_score_mismatches"
        ],
    )

    print_check(
        "Completed fixtures have final score",
        (
            scores[
                "completed_missing_final_score"
            ]
            == 0
        ),
        scores[
            "completed_missing_final_score"
        ],
    )


    print_section(
        "Player references"
    )

    print_metric(
        "Fixture player IDs missing from players table",
        orphan_players,
    )

    if orphan_players > 0:
        print(
            "[INFO] These are not lost statistics. "
            "They only mean the player master table "
            "does not yet contain every historical player."
        )


    print_section(
        "Latest import run"
    )

    if import_run:
        print_metric(
            "Import run ID",
            import_run[
                "import_run_id"
            ],
        )

        print_metric(
            "Status",
            import_run[
                "status"
            ],
        )

        print_metric(
            "API requests",
            import_run[
                "api_requests"
            ],
        )

        print_metric(
            "Rows received",
            import_run[
                "rows_received"
            ],
        )

        print_metric(
            "Rows inserted",
            import_run[
                "rows_inserted"
            ],
        )

        print_metric(
            "Started",
            import_run[
                "started_at"
            ],
        )

        print_metric(
            "Finished",
            import_run[
                "finished_at"
            ],
        )

    else:
        print(
            "No historical import run found."
        )


    print_section(
        "Audit complete"
    )

    print(
        "Review WARN items before importing "
        "the full historical dataset."
    )

    print()


if __name__ == "__main__":
    main()