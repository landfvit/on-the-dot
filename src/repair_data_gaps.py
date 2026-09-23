import argparse
import json
from pathlib import Path

from history_import import (
    ApiClient,
    get_connection,
    insert_events,
    insert_fixture_players,
    insert_fixture_statistics,
    insert_lineups,
    load_environment,
    save_raw_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COVERAGE_FILE = (
    PROJECT_ROOT
    / "data"
    / "audits"
    / "premier_league_coverage.json"
)

DEFAULT_LEAGUE_ID = 39
DEFAULT_REQUEST_DELAY = 0.22

COMPLETED_STATUSES = (
    "FT",
    "AET",
    "PEN",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Repair missing fixture data "
            "using direct API-Football endpoints."
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
        action="append",
    )

    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Do not retry provider gaps "
            "that were already checked."
        ),
    )

    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
    )

    return parser.parse_args()


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


def choose_seasons(
    audit,
    selected_seasons,
):
    seasons = list(
        audit.get(
            "seasons",
            [],
        )
    )

    if selected_seasons:
        selected = set(
            selected_seasons
        )

        seasons = [
            item
            for item in seasons
            if item["year"] in selected
        ]

    seasons.sort(
        key=lambda item: item["year"]
    )

    return seasons


def season_label(season):
    return (
        f"{season}/"
        f"{str(season + 1)[-2:]}"
    )


def raw_attempt_exists(
    conn,
    fixture_id,
    data_type,
):
    row = conn.execute(
        """
        SELECT 1

        FROM fixture_raw_data

        WHERE
            fixture_id = %s
            AND data_type = %s
            AND source = 'api-football'

        LIMIT 1
        """,
        (
            fixture_id,
            data_type,
        ),
    ).fetchone()

    return row is not None


def get_missing_fixtures(
    conn,
    league_id,
    season,
    table_name,
):
    allowed_tables = {
        "fixture_events",
        "fixture_lineups",
        "fixture_statistics",
        "fixture_player_statistics",
    }

    if table_name not in allowed_tables:
        raise ValueError(
            "Invalid table name."
        )

    query = f"""
        SELECT
            f.fixture_id,
            f.match_date,
            home.team_name AS home_team,
            away.team_name AS away_team

        FROM fixtures f

        JOIN teams home
            ON home.team_id = f.home_team_id

        JOIN teams away
            ON away.team_id = f.away_team_id

        WHERE
            f.league_id = %s
            AND f.season = %s
            AND f.status = ANY(%s)

            AND NOT EXISTS (
                SELECT 1

                FROM {table_name} d

                WHERE
                    d.fixture_id = f.fixture_id
            )

        ORDER BY
            f.match_date,
            f.fixture_id
    """

    return conn.execute(
        query,
        (
            league_id,
            season,
            list(
                COMPLETED_STATUSES
            ),
        ),
    ).fetchall()


def request_budget_reached(
    client,
    max_requests,
):
    if max_requests is None:
        return False

    return (
        client.request_count
        >= max_requests
    )


def print_fixture(
    fixture,
):
    print(
        "    "
        f"{fixture['fixture_id']} "
        f"{fixture['home_team']} - "
        f"{fixture['away_team']}"
    )


def repair_events(
    conn,
    client,
    fixtures,
    resume,
    max_requests,
):
    recovered = 0
    unavailable = 0
    skipped = 0

    for fixture in fixtures:
        fixture_id = fixture[
            "fixture_id"
        ]

        raw_type = (
            "events_direct"
        )

        if (
            resume
            and raw_attempt_exists(
                conn,
                fixture_id,
                raw_type,
            )
        ):
            skipped += 1
            continue

        if request_budget_reached(
            client,
            max_requests,
        ):
            return (
                recovered,
                unavailable,
                skipped,
                False,
            )

        print_fixture(
            fixture
        )

        data = client.get(
            "/fixtures/events",
            params={
                "fixture": fixture_id,
            },
        )

        response = (
            data.get(
                "response"
            )
            or []
        )

        with conn.transaction():
            save_raw_data(
                conn,
                fixture_id,
                raw_type,
                data,
            )

            if response:
                insert_events(
                    conn,
                    fixture_id,
                    response,
                )

        if response:
            recovered += 1

            print(
                f"      recovered "
                f"{len(response)} events"
            )

        else:
            unavailable += 1

            print(
                "      provider returned "
                "no events"
            )

    return (
        recovered,
        unavailable,
        skipped,
        True,
    )


def repair_lineups(
    conn,
    client,
    fixtures,
    resume,
    max_requests,
):
    recovered = 0
    unavailable = 0
    skipped = 0

    for fixture in fixtures:
        fixture_id = fixture[
            "fixture_id"
        ]

        raw_type = (
            "lineups_direct"
        )

        if (
            resume
            and raw_attempt_exists(
                conn,
                fixture_id,
                raw_type,
            )
        ):
            skipped += 1
            continue

        if request_budget_reached(
            client,
            max_requests,
        ):
            return (
                recovered,
                unavailable,
                skipped,
                False,
            )

        print_fixture(
            fixture
        )

        data = client.get(
            "/fixtures/lineups",
            params={
                "fixture": fixture_id,
            },
        )

        response = (
            data.get(
                "response"
            )
            or []
        )

        with conn.transaction():
            save_raw_data(
                conn,
                fixture_id,
                raw_type,
                data,
            )

            if response:
                insert_lineups(
                    conn,
                    fixture_id,
                    response,
                )

        if response:
            recovered += 1

            print(
                f"      recovered "
                f"{len(response)} lineups"
            )

        else:
            unavailable += 1

            print(
                "      provider returned "
                "no lineups"
            )

    return (
        recovered,
        unavailable,
        skipped,
        True,
    )


def repair_team_statistics(
    conn,
    client,
    fixtures,
    resume,
    max_requests,
):
    recovered = 0
    unavailable = 0
    skipped = 0

    for fixture in fixtures:
        fixture_id = fixture[
            "fixture_id"
        ]

        raw_type = (
            "team_statistics_direct"
        )

        if (
            resume
            and raw_attempt_exists(
                conn,
                fixture_id,
                raw_type,
            )
        ):
            skipped += 1
            continue

        if request_budget_reached(
            client,
            max_requests,
        ):
            return (
                recovered,
                unavailable,
                skipped,
                False,
            )

        print_fixture(
            fixture
        )

        data = client.get(
            "/fixtures/statistics",
            params={
                "fixture": fixture_id,
            },
        )

        response = (
            data.get(
                "response"
            )
            or []
        )

        with conn.transaction():
            save_raw_data(
                conn,
                fixture_id,
                raw_type,
                data,
            )

            if response:
                insert_fixture_statistics(
                    conn,
                    fixture_id,
                    response,
                )

        if response:
            recovered += 1

            print(
                f"      recovered "
                f"{len(response)} team rows"
            )

        else:
            unavailable += 1

            print(
                "      provider returned "
                "no team statistics"
            )

    return (
        recovered,
        unavailable,
        skipped,
        True,
    )


def repair_player_statistics(
    conn,
    client,
    fixtures,
    resume,
    max_requests,
):
    recovered = 0
    unavailable = 0
    skipped = 0

    for fixture in fixtures:
        fixture_id = fixture[
            "fixture_id"
        ]

        raw_type = (
            "player_statistics_direct"
        )

        if (
            resume
            and raw_attempt_exists(
                conn,
                fixture_id,
                raw_type,
            )
        ):
            skipped += 1
            continue

        if request_budget_reached(
            client,
            max_requests,
        ):
            return (
                recovered,
                unavailable,
                skipped,
                False,
            )

        print_fixture(
            fixture
        )

        data = client.get(
            "/fixtures/players",
            params={
                "fixture": fixture_id,
            },
        )

        response = (
            data.get(
                "response"
            )
            or []
        )

        with conn.transaction():
            save_raw_data(
                conn,
                fixture_id,
                raw_type,
                data,
            )

            if response:
                insert_fixture_players(
                    conn,
                    fixture_id,
                    response,
                )

        if response:
            recovered += 1

            print(
                f"      recovered "
                f"{len(response)} team blocks"
            )

        else:
            unavailable += 1

            print(
                "      provider returned "
                "no player statistics"
            )

    return (
        recovered,
        unavailable,
        skipped,
        True,
    )


def backfill_orphan_players(
    conn,
    league_id,
):
    rows = conn.execute(
        """
        SELECT
            fps.player_id,
            MAX(
                fps.player_name
            ) AS player_name

        FROM fixture_player_statistics fps

        JOIN fixtures f
            ON f.fixture_id = fps.fixture_id

        LEFT JOIN players p
            ON p.player_id = fps.player_id

        WHERE
            f.league_id = %s
            AND fps.player_id IS NOT NULL
            AND p.player_id IS NULL

        GROUP BY
            fps.player_id

        ORDER BY
            fps.player_id
        """,
        (
            league_id,
        ),
    ).fetchall()

    inserted = 0
    unresolved = 0

    with conn.transaction():
        for row in rows:
            player_id = row[
                "player_id"
            ]

            player_name = row[
                "player_name"
            ]

            if not player_name:
                unresolved += 1
                continue

            conn.execute(
                """
                INSERT INTO players (
                    player_id,
                    player_name,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (
                    player_id
                )
                DO NOTHING
                """,
                (
                    player_id,
                    player_name,
                ),
            )

            inserted += 1

    return (
        len(rows),
        inserted,
        unresolved,
    )


def repair_data_type(
    conn,
    client,
    league_id,
    season,
    coverage,
    table_name,
    coverage_key,
    title,
    repair_function,
    resume,
    max_requests,
):
    if not coverage.get(
        coverage_key
    ):
        return True

    fixtures = get_missing_fixtures(
        conn,
        league_id,
        season,
        table_name,
    )

    if not fixtures:
        return True

    print()

    print(
        f"  {title}"
    )

    print(
        "  missing fixtures: "
        f"{len(fixtures)}"
    )

    (
        recovered,
        unavailable,
        skipped,
        completed,
    ) = repair_function(
        conn,
        client,
        fixtures,
        resume,
        max_requests,
    )

    print(
        "  recovered: "
        f"{recovered}"
    )

    print(
        "  provider unavailable: "
        f"{unavailable}"
    )

    print(
        "  already checked: "
        f"{skipped}"
    )

    return completed


def main():
    args = parse_args()

    API_key = load_environment()

    audit = load_coverage()

    seasons = choose_seasons(
        audit,
        args.season,
    )

    client = ApiClient(
        API_key,
        request_delay=(
            args.request_delay
        ),
    )

    print(
        "Premier League gap repair"
    )

    print()

    print(
        "Selected seasons:"
    )

    for season_info in seasons:
        print(
            "  "
            f"{season_info['label']}"
        )

    with get_connection() as conn:
        for season_info in seasons:
            season = season_info[
                "year"
            ]

            coverage = (
                season_info.get(
                    "coverage"
                )
                or {}
            )

            print()

            print(
                "Checking "
                f"{season_label(season)}"
            )

            completed = repair_data_type(
                conn,
                client,
                args.league_id,
                season,
                coverage,
                "fixture_events",
                "fixture_events",
                "events",
                repair_events,
                args.resume,
                args.max_requests,
            )

            if not completed:
                break

            completed = repair_data_type(
                conn,
                client,
                args.league_id,
                season,
                coverage,
                "fixture_lineups",
                "fixture_lineups",
                "lineups",
                repair_lineups,
                args.resume,
                args.max_requests,
            )

            if not completed:
                break

            completed = repair_data_type(
                conn,
                client,
                args.league_id,
                season,
                coverage,
                "fixture_statistics",
                "fixture_team_statistics",
                "team statistics",
                repair_team_statistics,
                args.resume,
                args.max_requests,
            )

            if not completed:
                break

            completed = repair_data_type(
                conn,
                client,
                args.league_id,
                season,
                coverage,
                "fixture_player_statistics",
                "fixture_player_statistics",
                "player statistics",
                repair_player_statistics,
                args.resume,
                args.max_requests,
            )

            if not completed:
                break

        print()

        print(
            "Backfilling player master..."
        )

        (
            orphan_count,
            inserted,
            unresolved,
        ) = backfill_orphan_players(
            conn,
            args.league_id,
        )

        print(
            "  orphan player IDs found: "
            f"{orphan_count}"
        )

        print(
            "  players created from "
            "fixture source names: "
            f"{inserted}"
        )

        print(
            "  unresolved players: "
            f"{unresolved}"
        )

    quota = client.quota_remaining()

    print()

    print(
        "Gap repair finished."
    )

    print(
        "API requests used: "
        f"{client.request_count}"
    )

    print(
        "Daily remaining: "
        f"{quota['daily']}"
    )


if __name__ == "__main__":
    main()