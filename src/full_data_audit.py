import argparse
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COVERAGE_FILE = (
    PROJECT_ROOT
    / "data"
    / "audits"
    / "premier_league_coverage.json"
)

DEFAULT_OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "audits"
    / "full_data_audit.json"
)

DEFAULT_LEAGUE_ID = 39

COMPLETED_STATUSES = (
    "FT",
    "AET",
    "PEN",
)

DETAIL_TABLES = {
    "fixture_events",
    "fixture_lineups",
    "fixture_statistics",
    "fixture_player_statistics",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Audit the complete historical "
            "Premier League database."
        )
    )

    parser.add_argument(
        "--league-id",
        type=int,
        default=DEFAULT_LEAGUE_ID,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
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


def load_coverage():
    if not COVERAGE_FILE.exists():
        raise RuntimeError(
            "coverage audit not found: "
            f"{COVERAGE_FILE}"
        )

    with COVERAGE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


def scalar(
    conn,
    query,
    params=(),
):
    row = conn.execute(
        query,
        params,
    ).fetchone()

    if not row:
        return 0

    return next(
        iter(
            row.values()
        )
    )


def season_label(year):
    return (
        f"{year}/"
        f"{str(year + 1)[-2:]}"
    )


def make_check(
    name,
    status,
    value,
):
    return {
        "name": name,
        "status": status,
        "value": value,
        "accepted": (
            status
            in {
                "PASS",
                "PROVIDER",
            }
        ),
    }


def get_team_count(
    conn,
    league_id,
    season,
):
    return scalar(
        conn,
        """
        SELECT COUNT(*)

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

        WHERE team_id IS NOT NULL
        """,
        (
            league_id,
            season,
            league_id,
            season,
        ),
    )


def get_fixture_counts(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            COUNT(*) AS total,

            COUNT(*) FILTER (
                WHERE status = ANY(%s)
            ) AS completed,

            COUNT(*) FILTER (
                WHERE status = 'NS'
            ) AS not_started,

            COUNT(*) FILTER (
                WHERE venue_id IS NULL
            ) AS missing_venue,

            COUNT(*) FILTER (
                WHERE referee IS NULL
            ) AS missing_referee,

            COUNT(*) FILTER (
                WHERE
                    status = ANY(%s)
                    AND (
                        home_goals IS NULL
                        OR away_goals IS NULL
                    )
            ) AS completed_missing_score

        FROM fixtures

        WHERE
            league_id = %s
            AND season = %s
        """,
        (
            list(
                COMPLETED_STATUSES
            ),
            list(
                COMPLETED_STATUSES
            ),
            league_id,
            season,
        ),
    ).fetchone()


def get_raw_fixture_counts(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            COUNT(
                DISTINCT frd.fixture_id
            ) FILTER (
                WHERE
                    frd.data_type = 'fixture_base'
            ) AS base_payloads,

            COUNT(
                DISTINCT frd.fixture_id
            ) FILTER (
                WHERE
                    frd.data_type = 'fixture_complete'
            ) AS complete_payloads

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


def get_match_detail_counts(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            (
                SELECT COUNT(
                    DISTINCT fe.fixture_id
                )

                FROM fixture_events fe

                JOIN fixtures f
                    ON f.fixture_id = fe.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS event_fixtures,

            (
                SELECT COUNT(
                    DISTINCT fl.fixture_id
                )

                FROM fixture_lineups fl

                JOIN fixtures f
                    ON f.fixture_id = fl.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS lineup_fixtures,

            (
                SELECT COUNT(
                    DISTINCT fs.fixture_id
                )

                FROM fixture_statistics fs

                JOIN fixtures f
                    ON f.fixture_id = fs.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS team_stat_fixtures,

            (
                SELECT COUNT(
                    DISTINCT fps.fixture_id
                )

                FROM fixture_player_statistics fps

                JOIN fixtures f
                    ON f.fixture_id = fps.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS player_stat_fixtures
        """,
        (
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
        ),
    ).fetchone()


def get_match_row_counts(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            (
                SELECT COUNT(*)

                FROM fixture_events fe

                JOIN fixtures f
                    ON f.fixture_id = fe.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS events,

            (
                SELECT COUNT(*)

                FROM fixture_lineup_players flp

                JOIN fixtures f
                    ON f.fixture_id = flp.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS lineup_players,

            (
                SELECT COUNT(*)

                FROM fixture_statistics fs

                JOIN fixtures f
                    ON f.fixture_id = fs.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS team_stats,

            (
                SELECT COUNT(*)

                FROM fixture_player_statistics fps

                JOIN fixtures f
                    ON f.fixture_id = fps.fixture_id

                WHERE
                    f.league_id = %s
                    AND f.season = %s
            ) AS player_stats
        """,
        (
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
        ),
    ).fetchone()


def get_season_data_counts(
    conn,
    league_id,
    season,
):
    return conn.execute(
        """
        SELECT
            (
                SELECT COUNT(*)

                FROM season_standings

                WHERE
                    league_id = %s
                    AND season = %s
            ) AS standings,

            (
                SELECT COUNT(*)

                FROM team_season_api_statistics

                WHERE
                    league_id = %s
                    AND season = %s
            ) AS team_season_stats,

            (
                SELECT COUNT(*)

                FROM player_season_statistics

                WHERE
                    league_id = %s
                    AND season = %s
            ) AS player_season_stats,

            (
                SELECT COUNT(*)

                FROM squad_memberships

                WHERE
                    league_id = %s
                    AND season = %s
            ) AS squad_memberships,

            (
                SELECT COUNT(*)

                FROM season_injuries

                WHERE
                    league_id = %s
                    AND season = %s
            ) AS injuries
        """,
        (
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
            league_id,
            season,
        ),
    ).fetchone()


def successful_import_exists(
    conn,
    import_type,
    league_id,
    season,
):
    row = conn.execute(
        """
        SELECT 1

        FROM import_runs

        WHERE
            import_type = %s
            AND league_id = %s
            AND season = %s
            AND status IN (
                'success',
                'completed'
            )

        LIMIT 1
        """,
        (
            import_type,
            league_id,
            season,
        ),
    ).fetchone()

    return row is not None


def get_negative_event_count(
    conn,
    league_id,
    season,
):
    return scalar(
        conn,
        """
        SELECT COUNT(*)

        FROM fixture_events fe

        JOIN fixtures f
            ON f.fixture_id = fe.fixture_id

        WHERE
            f.league_id = %s
            AND f.season = %s
            AND fe.elapsed_minute < 0
        """,
        (
            league_id,
            season,
        ),
    )


def get_missing_fixture_count(
    conn,
    league_id,
    season,
    table_name,
):
    if table_name not in DETAIL_TABLES:
        raise ValueError(
            f"invalid detail table: "
            f"{table_name}"
        )

    query = f"""
        SELECT COUNT(*)

        FROM fixtures f

        WHERE
            f.league_id = %s
            AND f.season = %s
            AND f.status = ANY(%s)

            AND NOT EXISTS (
                SELECT 1

                FROM {table_name} d

                WHERE
                    d.fixture_id
                    = f.fixture_id
            )
    """

    return scalar(
        conn,
        query,
        (
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
        ),
    )


def get_provider_checked_gap_count(
    conn,
    league_id,
    season,
    table_name,
    raw_type,
):
    if table_name not in DETAIL_TABLES:
        raise ValueError(
            f"invalid detail table: "
            f"{table_name}"
        )

    query = f"""
        SELECT COUNT(*)

        FROM fixtures f

        WHERE
            f.league_id = %s
            AND f.season = %s
            AND f.status = ANY(%s)

            AND NOT EXISTS (
                SELECT 1

                FROM {table_name} d

                WHERE
                    d.fixture_id
                    = f.fixture_id
            )

            AND EXISTS (
                SELECT 1

                FROM fixture_raw_data frd

                WHERE
                    frd.fixture_id
                    = f.fixture_id

                    AND frd.data_type = %s

                    AND frd.source
                    = 'api-football'
            )
    """

    return scalar(
        conn,
        query,
        (
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
            raw_type,
        ),
    )


def fixture_detail_check(
    conn,
    league_id,
    season,
    table_name,
    raw_type,
    check_name,
    actual_count,
    expected_count,
):
    if actual_count == expected_count:
        return make_check(
            check_name,
            "PASS",
            (
                f"{actual_count}/"
                f"{expected_count}"
            ),
        )

    missing_count = (
        get_missing_fixture_count(
            conn,
            league_id,
            season,
            table_name,
        )
    )

    provider_checked = (
        get_provider_checked_gap_count(
            conn,
            league_id,
            season,
            table_name,
            raw_type,
        )
    )

    if (
        missing_count > 0
        and provider_checked
        == missing_count
    ):
        return make_check(
            check_name,
            "PROVIDER",
            (
                f"{actual_count}/"
                f"{expected_count} "
                f"({missing_count} unavailable)"
            ),
        )

    return make_check(
        check_name,
        "WARN",
        (
            f"{actual_count}/"
            f"{expected_count}; "
            f"missing={missing_count}; "
            f"provider_checked="
            f"{provider_checked}"
        ),
    )


def audit_season(
    conn,
    league_id,
    season_info,
):
    season = season_info[
        "year"
    ]

    coverage = (
        season_info.get(
            "coverage"
        )
        or {}
    )

    team_count = get_team_count(
        conn,
        league_id,
        season,
    )

    fixtures = get_fixture_counts(
        conn,
        league_id,
        season,
    )

    raw = get_raw_fixture_counts(
        conn,
        league_id,
        season,
    )

    detail = get_match_detail_counts(
        conn,
        league_id,
        season,
    )

    rows = get_match_row_counts(
        conn,
        league_id,
        season,
    )

    season_data = get_season_data_counts(
        conn,
        league_id,
        season,
    )

    negative_events = (
        get_negative_event_count(
            conn,
            league_id,
            season,
        )
    )

    expected_fixtures = (
        team_count
        * (
            team_count - 1
        )
        if team_count
        else 0
    )

    checks = []

    checks.append(
        make_check(
            "fixture_count",
            (
                "PASS"
                if (
                    fixtures[
                        "total"
                    ]
                    == expected_fixtures
                )
                else "WARN"
            ),
            (
                f"{fixtures['total']}"
                f"/{expected_fixtures}"
            ),
        )
    )

    checks.append(
        make_check(
            "base_payloads",
            (
                "PASS"
                if (
                    raw[
                        "base_payloads"
                    ]
                    == fixtures[
                        "total"
                    ]
                )
                else "WARN"
            ),
            (
                f"{raw['base_payloads']}"
                f"/{fixtures['total']}"
            ),
        )
    )

    checks.append(
        make_check(
            "complete_payloads",
            (
                "PASS"
                if (
                    raw[
                        "complete_payloads"
                    ]
                    == fixtures[
                        "completed"
                    ]
                )
                else "WARN"
            ),
            (
                f"{raw['complete_payloads']}"
                f"/{fixtures['completed']}"
            ),
        )
    )

    checks.append(
        make_check(
            "completed_scores",
            (
                "PASS"
                if (
                    fixtures[
                        "completed_missing_score"
                    ]
                    == 0
                )
                else "WARN"
            ),
            fixtures[
                "completed_missing_score"
            ],
        )
    )

    if coverage.get(
        "fixture_events"
    ):
        checks.append(
            fixture_detail_check(
                conn,
                league_id,
                season,
                "fixture_events",
                "events_direct",
                "events",
                detail[
                    "event_fixtures"
                ],
                fixtures[
                    "completed"
                ],
            )
        )

    if coverage.get(
        "fixture_lineups"
    ):
        checks.append(
            fixture_detail_check(
                conn,
                league_id,
                season,
                "fixture_lineups",
                "lineups_direct",
                "lineups",
                detail[
                    "lineup_fixtures"
                ],
                fixtures[
                    "completed"
                ],
            )
        )

    if coverage.get(
        "fixture_team_statistics"
    ):
        checks.append(
            fixture_detail_check(
                conn,
                league_id,
                season,
                "fixture_statistics",
                "team_statistics_direct",
                "team_fixture_stats",
                detail[
                    "team_stat_fixtures"
                ],
                fixtures[
                    "completed"
                ],
            )
        )

    if coverage.get(
        "fixture_player_statistics"
    ):
        checks.append(
            fixture_detail_check(
                conn,
                league_id,
                season,
                "fixture_player_statistics",
                "player_statistics_direct",
                "player_fixture_stats",
                detail[
                    "player_stat_fixtures"
                ],
                fixtures[
                    "completed"
                ],
            )
        )

    if coverage.get(
        "standings"
    ):
        checks.append(
            make_check(
                "standings",
                (
                    "PASS"
                    if (
                        season_data[
                            "standings"
                        ]
                        == team_count
                    )
                    else "WARN"
                ),
                (
                    f"{season_data['standings']}"
                    f"/{team_count}"
                ),
            )
        )

    if coverage.get(
        "players"
    ):
        checks.append(
            make_check(
                "player_season_stats",
                (
                    "PASS"
                    if (
                        season_data[
                            "player_season_stats"
                        ]
                        > 0
                    )
                    else "WARN"
                ),
                season_data[
                    "player_season_stats"
                ],
            )
        )

        checks.append(
            make_check(
                "squad_memberships",
                (
                    "PASS"
                    if (
                        season_data[
                            "squad_memberships"
                        ]
                        > 0
                    )
                    else "WARN"
                ),
                season_data[
                    "squad_memberships"
                ],
            )
        )

    checks.append(
        make_check(
            "team_season_stats",
            (
                "PASS"
                if (
                    season_data[
                        "team_season_stats"
                    ]
                    == team_count
                )
                else "WARN"
            ),
            (
                f"{season_data['team_season_stats']}"
                f"/{team_count}"
            ),
        )
    )

    season_history_success = (
        successful_import_exists(
            conn,
            "season_history",
            league_id,
            season,
        )
    )

    checks.append(
        make_check(
            "season_history_import",
            (
                "PASS"
                if season_history_success
                else "WARN"
            ),
            season_history_success,
        )
    )

    if coverage.get(
        "injuries"
    ):
        injury_success = (
            successful_import_exists(
                conn,
                "injuries_history",
                league_id,
                season,
            )
        )

        checks.append(
            make_check(
                "injuries_import",
                (
                    "PASS"
                    if injury_success
                    else "WARN"
                ),
                injury_success,
            )
        )

    has_warn = any(
        check[
            "status"
        ]
        == "WARN"
        for check
        in checks
    )

    has_provider_limit = any(
        check[
            "status"
        ]
        == "PROVIDER"
        for check
        in checks
    )

    if has_warn:
        season_status = "WARN"

    elif has_provider_limit:
        season_status = "PROVIDER"

    else:
        season_status = "PASS"

    return {
        "season": season,
        "label": season_label(
            season
        ),
        "status": season_status,
        "accepted": (
            season_status
            in {
                "PASS",
                "PROVIDER",
            }
        ),
        "coverage": coverage,
        "teams": team_count,
        "expected_fixtures": (
            expected_fixtures
        ),
        "fixtures": dict(
            fixtures
        ),
        "raw_payloads": dict(
            raw
        ),
        "match_detail": dict(
            detail
        ),
        "row_counts": dict(
            rows
        ),
        "season_data": dict(
            season_data
        ),
        "negative_event_minutes": (
            negative_events
        ),
        "checks": checks,
    }


def get_relevant_player_count(
    conn,
    league_id,
):
    return scalar(
        conn,
        """
        SELECT COUNT(*)

        FROM (
            SELECT DISTINCT
                fps.player_id

            FROM fixture_player_statistics fps

            JOIN fixtures f
                ON f.fixture_id
                = fps.fixture_id

            WHERE
                f.league_id = %s
                AND fps.player_id
                IS NOT NULL

            UNION

            SELECT DISTINCT
                pss.player_id

            FROM player_season_statistics pss

            WHERE
                pss.league_id = %s
                AND pss.player_id
                IS NOT NULL
        ) players
        """,
        (
            league_id,
            league_id,
        ),
    )


def get_relevant_coach_count(
    conn,
    league_id,
):
    return scalar(
        conn,
        """
        SELECT COUNT(
            DISTINCT fl.coach_id
        )

        FROM fixture_lineups fl

        JOIN fixtures f
            ON f.fixture_id
            = fl.fixture_id

        WHERE
            f.league_id = %s
            AND fl.coach_id
            IS NOT NULL
        """,
        (
            league_id,
        ),
    )


def get_entity_status_count(
    conn,
    entity_type,
    data_type,
    status,
):
    return scalar(
        conn,
        """
        SELECT COUNT(*)

        FROM entity_import_status

        WHERE
            entity_type = %s
            AND data_type = %s
            AND source = 'api-football'
            AND status = %s
        """,
        (
            entity_type,
            data_type,
            status,
        ),
    )


def audit_entities(
    conn,
    league_id,
):
    relevant_players = (
        get_relevant_player_count(
            conn,
            league_id,
        )
    )

    relevant_coaches = (
        get_relevant_coach_count(
            conn,
            league_id,
        )
    )

    transfer_success = (
        get_entity_status_count(
            conn,
            "player",
            "transfers",
            "success",
        )
    )

    transfer_failed = (
        get_entity_status_count(
            conn,
            "player",
            "transfers",
            "failed",
        )
    )

    sidelined_success = (
        get_entity_status_count(
            conn,
            "player",
            "sidelined",
            "success",
        )
    )

    sidelined_failed = (
        get_entity_status_count(
            conn,
            "player",
            "sidelined",
            "failed",
        )
    )

    coach_success = (
        get_entity_status_count(
            conn,
            "coach",
            "profile",
            "success",
        )
    )

    coach_failed = (
        get_entity_status_count(
            conn,
            "coach",
            "profile",
            "failed",
        )
    )

    transfer_rows = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM player_transfers
        """,
    )

    sidelined_rows = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM player_sidelined
        """,
    )

    coach_rows = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM coaches
        """,
    )

    coach_career_rows = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM coach_careers
        """,
    )

    checks = []

    checks.append(
        make_check(
            "transfers_import",
            (
                "PASS"
                if (
                    transfer_success
                    >= relevant_players
                    and transfer_failed == 0
                )
                else "WARN"
            ),
            (
                f"{transfer_success}/"
                f"{relevant_players}"
            ),
        )
    )

    checks.append(
        make_check(
            "sidelined_import",
            (
                "PASS"
                if (
                    sidelined_success
                    >= relevant_players
                    and sidelined_failed == 0
                )
                else "WARN"
            ),
            (
                f"{sidelined_success}/"
                f"{relevant_players}"
            ),
        )
    )

    checks.append(
        make_check(
            "coaches_import",
            (
                "PASS"
                if (
                    coach_success
                    >= relevant_coaches
                    and coach_failed == 0
                )
                else "WARN"
            ),
            (
                f"{coach_success}/"
                f"{relevant_coaches}"
            ),
        )
    )

    passed = all(
        check[
            "status"
        ]
        == "PASS"
        for check
        in checks
    )

    return {
        "passed": passed,
        "relevant_players": relevant_players,
        "relevant_coaches": relevant_coaches,
        "transfer_success": transfer_success,
        "transfer_failed": transfer_failed,
        "sidelined_success": sidelined_success,
        "sidelined_failed": sidelined_failed,
        "coach_success": coach_success,
        "coach_failed": coach_failed,
        "transfer_rows": transfer_rows,
        "sidelined_rows": sidelined_rows,
        "coach_rows": coach_rows,
        "coach_career_rows": (
            coach_career_rows
        ),
        "checks": checks,
    }


def audit_orphans(
    conn,
    league_id,
):
    fixture_player_orphans = scalar(
        conn,
        """
        SELECT COUNT(
            DISTINCT fps.player_id
        )

        FROM fixture_player_statistics fps

        JOIN fixtures f
            ON f.fixture_id
            = fps.fixture_id

        LEFT JOIN players p
            ON p.player_id
            = fps.player_id

        WHERE
            f.league_id = %s
            AND fps.player_id
            IS NOT NULL
            AND p.player_id
            IS NULL
        """,
        (
            league_id,
        ),
    )

    season_player_orphans = scalar(
        conn,
        """
        SELECT COUNT(
            DISTINCT pss.player_id
        )

        FROM player_season_statistics pss

        LEFT JOIN players p
            ON p.player_id
            = pss.player_id

        WHERE
            pss.league_id = %s
            AND p.player_id IS NULL
        """,
        (
            league_id,
        ),
    )

    injury_player_orphans = scalar(
        conn,
        """
        SELECT COUNT(
            DISTINCT si.player_id
        )

        FROM season_injuries si

        LEFT JOIN players p
            ON p.player_id
            = si.player_id

        WHERE
            si.league_id = %s
            AND si.player_id
            IS NOT NULL
            AND p.player_id
            IS NULL
        """,
        (
            league_id,
        ),
    )

    return {
        "fixture_player_orphans": (
            fixture_player_orphans
        ),
        "season_player_orphans": (
            season_player_orphans
        ),
        "injury_player_orphans": (
            injury_player_orphans
        ),
    }


def print_check(
    check,
):
    print(
        f"[{check['status']}] "
        f"{check['name']}: "
        f"{check['value']}"
    )


def print_season_table(
    season_results,
):
    print()

    print(
        "Season coverage"
    )

    header = (
        f"{'Season':<10}"
        f"{'Fixtures':>10}"
        f"{'Done':>8}"
        f"{'Events':>9}"
        f"{'Lineups':>10}"
        f"{'TStats':>9}"
        f"{'PStats':>9}"
        f"{'Stand':>8}"
        f"{'Status':>11}"
    )

    print(
        header
    )

    print(
        "-" * len(
            header
        )
    )

    for item in season_results:
        fixtures = item[
            "fixtures"
        ]

        detail = item[
            "match_detail"
        ]

        season_data = item[
            "season_data"
        ]

        print(
            f"{item['label']:<10}"
            f"{fixtures['total']:>10}"
            f"{fixtures['completed']:>8}"
            f"{detail['event_fixtures']:>9}"
            f"{detail['lineup_fixtures']:>10}"
            f"{detail['team_stat_fixtures']:>9}"
            f"{detail['player_stat_fixtures']:>9}"
            f"{season_data['standings']:>8}"
            f"{item['status']:>11}"
        )


def print_entity_summary(
    entity_result,
):
    print()

    print(
        "Entity history"
    )

    print(
        "Relevant Premier League players: "
        f"{entity_result['relevant_players']}"
    )

    print(
        "Relevant historical coaches: "
        f"{entity_result['relevant_coaches']}"
    )

    print()

    for check in entity_result[
        "checks"
    ]:
        print_check(
            check
        )

    print()

    print(
        "Transfer rows: "
        f"{entity_result['transfer_rows']}"
    )

    print(
        "Sidelined rows: "
        f"{entity_result['sidelined_rows']}"
    )

    print(
        "Coach profiles: "
        f"{entity_result['coach_rows']}"
    )

    print(
        "Coach career rows: "
        f"{entity_result['coach_career_rows']}"
    )


def print_orphans(
    orphans,
):
    print()

    print(
        "Reference integrity"
    )

    print(
        "Fixture-stat player IDs "
        "missing from players: "
        f"{orphans['fixture_player_orphans']}"
    )

    print(
        "Season-stat player IDs "
        "missing from players: "
        f"{orphans['season_player_orphans']}"
    )

    print(
        "Injury player IDs "
        "missing from players: "
        f"{orphans['injury_player_orphans']}"
    )


def main():
    args = parse_args()

    load_environment()

    audit = load_coverage()

    seasons = list(
        audit.get(
            "seasons",
            [],
        )
    )

    seasons.sort(
        key=lambda item: (
            item[
                "year"
            ]
        )
    )

    with get_connection() as conn:
        season_results = [
            audit_season(
                conn,
                args.league_id,
                season_info,
            )
            for season_info
            in seasons
        ]

        entity_result = (
            audit_entities(
                conn,
                args.league_id,
            )
        )

        orphans = audit_orphans(
            conn,
            args.league_id,
        )

    accepted_seasons = sum(
        1
        for item
        in season_results
        if item[
            "accepted"
        ]
    )

    clean_seasons = sum(
        1
        for item
        in season_results
        if item[
            "status"
        ]
        == "PASS"
    )

    provider_limited_seasons = sum(
        1
        for item
        in season_results
        if item[
            "status"
        ]
        == "PROVIDER"
    )

    warning_seasons = sum(
        1
        for item
        in season_results
        if item[
            "status"
        ]
        == "WARN"
    )

    overall_passed = (
        accepted_seasons
        == len(
            season_results
        )
        and entity_result[
            "passed"
        ]
        and orphans[
            "fixture_player_orphans"
        ] == 0
        and orphans[
            "season_player_orphans"
        ] == 0
    )

    result = {
        "league_id": args.league_id,
        "overall_status": (
            "PASS"
            if overall_passed
            else "WARN"
        ),
        "seasons_accepted": (
            accepted_seasons
        ),
        "seasons_clean": (
            clean_seasons
        ),
        "seasons_provider_limited": (
            provider_limited_seasons
        ),
        "seasons_warning": (
            warning_seasons
        ),
        "seasons_total": len(
            season_results
        ),
        "seasons": season_results,
        "entities": entity_result,
        "orphans": orphans,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    print()

    print(
        "Premier League full data audit"
    )

    print(
        "League ID: "
        f"{args.league_id}"
    )

    print_season_table(
        season_results
    )

    print()

    print(
        "Provider-limited data"
    )

    provider_found = False

    for item in season_results:
        for check in item[
            "checks"
        ]:
            if (
                check[
                    "status"
                ]
                != "PROVIDER"
            ):
                continue

            provider_found = True

            print(
                f"{item['label']} "
                f"{check['name']}: "
                f"{check['value']}"
            )

    if not provider_found:
        print(
            "None"
        )

    print()

    print(
        "Warnings"
    )

    warnings_found = False

    for item in season_results:
        for check in item[
            "checks"
        ]:
            if (
                check[
                    "status"
                ]
                != "WARN"
            ):
                continue

            warnings_found = True

            print(
                f"{item['label']} "
                f"{check['name']}: "
                f"{check['value']}"
            )

    if not warnings_found:
        print(
            "None"
        )

    print_entity_summary(
        entity_result
    )

    print_orphans(
        orphans
    )

    print()

    print(
        "Summary"
    )

    print(
        "Accepted seasons: "
        f"{accepted_seasons}/"
        f"{len(season_results)}"
    )

    print(
        "Fully complete seasons: "
        f"{clean_seasons}"
    )

    print(
        "Provider-limited seasons: "
        f"{provider_limited_seasons}"
    )

    print(
        "Seasons with unresolved warnings: "
        f"{warning_seasons}"
    )

    print(
        "Entity history: "
        + (
            "PASS"
            if entity_result[
                "passed"
            ]
            else "WARN"
        )
    )

    print(
        "Overall database status: "
        + (
            "PASS"
            if overall_passed
            else "WARN"
        )
    )

    print()

    print(
        "Audit saved to:"
    )

    print(
        args.output
    )

    print()


if __name__ == "__main__":
    main()