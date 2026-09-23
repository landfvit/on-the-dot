import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


from api.database import get_connection


ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(
    dotenv_path=ENV_FILE,
    override=True
)


BASE_URL = "https://v3.football.api-sports.io"

DEFAULT_LEAGUE_ID = 39
DEFAULT_SEASON = 2024

REQUEST_DELAY_SECONDS = 6.5
MAX_RETRIES = 5

# free plan allows only pages 1 to 3
MAX_FREE_PAGE = 3


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Import season players and squad memberships."
    )

    parser.add_argument(
        "--league",
        type=int,
        default=DEFAULT_LEAGUE_ID,
        help="API-Football league ID"
    )

    parser.add_argument(
        "--season",
        type=int,
        default=DEFAULT_SEASON,
        help="Season start year"
    )

    return parser.parse_args()


def get_API_key():
    API_key = os.getenv(
        "API_FOOTBALL_KEY"
    )

    if not API_key:
        raise RuntimeError(
            "API_FOOTBALL_KEY is missing from .env"
        )

    return API_key


def parse_integer_measurement(value):
    if value is None:
        return None

    text = str(
        value
    ).strip()

    number = ""

    for character in text:
        if character.isdigit():
            number += character

        elif number:
            break

    if not number:
        return None

    return int(
        number
    )


def parse_birth_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(
            value
        )

    except ValueError:
        return None


def make_request(
    endpoint,
    params,
    API_key
):
    url = (
        f"{BASE_URL}/{endpoint}"
    )

    headers = {
        "x-apisports-key": API_key
    }


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=30
            )

        except requests.RequestException as error:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"API request failed: {error}"
                ) from error


            print(
                f"request error, retry {attempt}/{MAX_RETRIES}"
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

            continue


        if response.status_code == 429:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "API rate limit reached after retries"
                )


            retry_after = response.headers.get(
                "Retry-After"
            )

            wait_seconds = 65


            if retry_after:
                try:
                    wait_seconds = max(
                        int(
                            retry_after
                        ),
                        10
                    )

                except ValueError:
                    pass


            print(
                f"rate limit reached, waiting {wait_seconds}s"
            )

            time.sleep(
                wait_seconds
            )

            continue


        if not response.ok:
            raise RuntimeError(
                f"API returned HTTP {response.status_code}: "
                f"{response.text}"
            )


        data = response.json()

        errors = data.get(
            "errors"
        )


        if errors:
            raise RuntimeError(
                f"API error: {errors}"
            )


        daily_remaining = (
            response.headers.get(
                "x-ratelimit-requests-remaining"
            )
        )


        if daily_remaining is not None:
            print(
                f"daily requests remaining: {daily_remaining}"
            )


        return data


    raise RuntimeError(
        "API request failed"
    )


def get_season_teams(
    connection,
    league_id,
    season
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                t.team_id,
                t.team_name

            FROM teams t

            JOIN (

                SELECT
                    home_team_id AS team_id

                FROM fixtures

                WHERE league_id = %s
                  AND season = %s


                UNION


                SELECT
                    away_team_id AS team_id

                FROM fixtures

                WHERE league_id = %s
                  AND season = %s

            ) season_teams
                ON t.team_id = season_teams.team_id

            ORDER BY
                t.team_name;
            """,
            (
                league_id,
                season,
                league_id,
                season
            )
        )

        return cursor.fetchall()


def create_import_run(
    connection,
    league_id,
    season
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO import_runs (
                import_type,
                league_id,
                season,
                started_at,
                status,
                rows_received,
                rows_inserted,
                api_requests
            )

            VALUES (
                'players_season',
                %s,
                %s,
                NOW(),
                'running',
                0,
                0,
                0
            )

            RETURNING import_run_id;
            """,
            (
                league_id,
                season
            )
        )

        row = cursor.fetchone()


    connection.commit()

    return row[
        "import_run_id"
    ]


def finish_import_run(
    connection,
    import_run_id,
    status,
    rows_received,
    rows_inserted,
    api_requests,
    error_message=None
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE import_runs

            SET
                finished_at = NOW(),
                status = %s,
                rows_received = %s,
                rows_inserted = %s,
                api_requests = %s,
                error_message = %s

            WHERE import_run_id = %s;
            """,
            (
                status,
                rows_received,
                rows_inserted,
                api_requests,
                error_message,
                import_run_id
            )
        )


    connection.commit()


def upsert_player(
    connection,
    player
):
    player_id = player.get(
        "id"
    )

    player_name = player.get(
        "name"
    )


    if player_id is None:
        return False

    if not player_name:
        return False


    birth = (
        player.get(
            "birth"
        )
        or {}
    )


    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO players (
                player_id,
                player_name,
                first_name,
                last_name,
                birth_date,
                nationality,
                height_cm,
                weight_kg,
                photo_url,
                updated_at
            )

            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW()
            )

            ON CONFLICT (
                player_id
            )

            DO UPDATE SET
                player_name =
                    EXCLUDED.player_name,

                first_name =
                    COALESCE(
                        EXCLUDED.first_name,
                        players.first_name
                    ),

                last_name =
                    COALESCE(
                        EXCLUDED.last_name,
                        players.last_name
                    ),

                birth_date =
                    COALESCE(
                        EXCLUDED.birth_date,
                        players.birth_date
                    ),

                nationality =
                    COALESCE(
                        EXCLUDED.nationality,
                        players.nationality
                    ),

                height_cm =
                    COALESCE(
                        EXCLUDED.height_cm,
                        players.height_cm
                    ),

                weight_kg =
                    COALESCE(
                        EXCLUDED.weight_kg,
                        players.weight_kg
                    ),

                photo_url =
                    COALESCE(
                        EXCLUDED.photo_url,
                        players.photo_url
                    ),

                updated_at =
                    NOW();
            """,
            (
                player_id,
                player_name,

                player.get(
                    "firstname"
                ),

                player.get(
                    "lastname"
                ),

                parse_birth_date(
                    birth.get(
                        "date"
                    )
                ),

                player.get(
                    "nationality"
                ),

                parse_integer_measurement(
                    player.get(
                        "height"
                    )
                ),

                parse_integer_measurement(
                    player.get(
                        "weight"
                    )
                ),

                player.get(
                    "photo"
                )
            )
        )


    return True


def upsert_membership(
    connection,
    league_id,
    season,
    expected_team_id,
    player,
    statistics
):
    player_id = player.get(
        "id"
    )

    team = (
        statistics.get(
            "team"
        )
        or {}
    )

    league = (
        statistics.get(
            "league"
        )
        or {}
    )

    games = (
        statistics.get(
            "games"
        )
        or {}
    )


    team_id = team.get(
        "id"
    )

    statistics_league_id = (
        league.get(
            "id"
        )
    )

    statistics_season = (
        league.get(
            "season"
        )
    )


    if player_id is None:
        return False

    if team_id is None:
        return False

    if team_id != expected_team_id:
        return False

    if statistics_league_id != league_id:
        return False

    if statistics_season is None:
        return False

    if int(
        statistics_season
    ) != season:
        return False


    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO squad_memberships (
                league_id,
                season,
                team_id,
                player_id,
                squad_number,
                position,
                age,
                photo_url,
                imported_at
            )

            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW()
            )

            ON CONFLICT (
                league_id,
                season,
                team_id,
                player_id
            )

            DO UPDATE SET
                squad_number =
                    COALESCE(
                        EXCLUDED.squad_number,
                        squad_memberships.squad_number
                    ),

                position =
                    COALESCE(
                        EXCLUDED.position,
                        squad_memberships.position
                    ),

                age =
                    COALESCE(
                        EXCLUDED.age,
                        squad_memberships.age
                    ),

                photo_url =
                    COALESCE(
                        EXCLUDED.photo_url,
                        squad_memberships.photo_url
                    ),

                imported_at =
                    NOW();
            """,
            (
                league_id,
                season,
                team_id,
                player_id,

                games.get(
                    "number"
                ),

                games.get(
                    "position"
                ),

                player.get(
                    "age"
                ),

                player.get(
                    "photo"
                )
            )
        )


    return True


def import_team_players(
    connection,
    league_id,
    season,
    team_id,
    team_name,
    API_key,
    imported_players,
    imported_memberships
):
    page = 1

    reported_total_pages = 1
    pages_to_import = 1

    team_rows_received = 0
    team_api_requests = 0

    truncated = False


    while page <= pages_to_import:
        print()

        print(
            f"{team_name}: requesting page {page}"
        )


        data = make_request(
            "players",
            {
                "league": league_id,
                "team": team_id,
                "season": season,
                "page": page
            },
            API_key
        )


        team_api_requests += 1


        paging = (
            data.get(
                "paging"
            )
            or {}
        )


        reported_total_pages = int(
            paging.get(
                "total",
                1
            )
        )


        if reported_total_pages > MAX_FREE_PAGE:
            pages_to_import = (
                MAX_FREE_PAGE
            )

            truncated = True

        else:
            pages_to_import = (
                reported_total_pages
            )


        if (
            page == 1
            and truncated
        ):
            print()

            print(
                f"warning: {team_name} has "
                f"{reported_total_pages} pages"
            )

            print(
                f"free plan allows only "
                f"pages 1-{MAX_FREE_PAGE}"
            )

            print(
                f"importing first "
                f"{MAX_FREE_PAGE} pages only"
            )


        response_rows = (
            data.get(
                "response"
            )
            or []
        )


        team_rows_received += len(
            response_rows
        )


        for item in response_rows:
            player = (
                item.get(
                    "player"
                )
                or {}
            )

            statistics_list = (
                item.get(
                    "statistics"
                )
                or []
            )


            if upsert_player(
                connection,
                player
            ):
                imported_players.add(
                    player[
                        "id"
                    ]
                )


            for statistics in statistics_list:
                inserted = (
                    upsert_membership(
                        connection,
                        league_id,
                        season,
                        team_id,
                        player,
                        statistics
                    )
                )


                if inserted:
                    imported_memberships.add(
                        (
                            league_id,
                            season,
                            team_id,
                            player[
                                "id"
                            ]
                        )
                    )


        connection.commit()


        print(
            f"{team_name}: "
            f"page {page}/{pages_to_import} complete"
        )


        if truncated:
            print(
                f"{team_name}: "
                f"API reports {reported_total_pages} total pages"
            )


        print(
            f"{team_name}: "
            f"{team_rows_received} player records"
        )


        page += 1


        if page <= pages_to_import:
            time.sleep(
                REQUEST_DELAY_SECONDS
            )


    return (
        team_rows_received,
        team_api_requests,
        truncated,
        reported_total_pages
    )


def build_warning_message(
    truncated_teams
):
    if not truncated_teams:
        return None


    parts = []


    for team in truncated_teams:
        parts.append(
            (
                f"{team['team_name']}: "
                f"imported {MAX_FREE_PAGE}/"
                f"{team['reported_pages']} pages"
            )
        )


    return (
        "Free plan pagination limit. "
        + "; ".join(
            parts
        )
    )


def import_players(
    league_id,
    season
):
    API_key = get_API_key()


    with get_connection() as connection:
        teams = get_season_teams(
            connection,
            league_id,
            season
        )


        if not teams:
            raise RuntimeError(
                "No teams found in fixtures "
                "for this league and season"
            )


        print(
            f"league: {league_id}"
        )

        print(
            f"season: {season}"
        )

        print(
            f"teams in database: {len(teams)}"
        )


        import_run_id = create_import_run(
            connection,
            league_id,
            season
        )


        rows_received = 0
        api_requests = 0

        imported_players = set()
        imported_memberships = set()

        truncated_teams = []


        try:
            for index, team in enumerate(
                teams,
                start=1
            ):
                team_id = team[
                    "team_id"
                ]

                team_name = team[
                    "team_name"
                ]


                print()

                print(
                    f"team {index}/{len(teams)}: "
                    f"{team_name} ({team_id})"
                )


                (
                    team_rows_received,
                    team_api_requests,
                    truncated,
                    reported_pages
                ) = import_team_players(
                    connection,
                    league_id,
                    season,
                    team_id,
                    team_name,
                    API_key,
                    imported_players,
                    imported_memberships
                )


                rows_received += (
                    team_rows_received
                )

                api_requests += (
                    team_api_requests
                )


                if truncated:
                    truncated_teams.append(
                        {
                            "team_id": team_id,
                            "team_name": team_name,
                            "reported_pages": reported_pages
                        }
                    )


                print(
                    f"total unique players: "
                    f"{len(imported_players)}"
                )

                print(
                    f"total memberships: "
                    f"{len(imported_memberships)}"
                )


                if index < len(teams):
                    time.sleep(
                        REQUEST_DELAY_SECONDS
                    )


            warning_message = (
                build_warning_message(
                    truncated_teams
                )
            )


            finish_import_run(
                connection,
                import_run_id,
                "completed",
                rows_received,
                len(
                    imported_memberships
                ),
                api_requests,
                warning_message
            )


        except Exception as error:
            connection.rollback()


            warning_message = str(
                error
            )


            if truncated_teams:
                warning_message += (
                    " | "
                    + build_warning_message(
                        truncated_teams
                    )
                )


            finish_import_run(
                connection,
                import_run_id,
                "failed",
                rows_received,
                len(
                    imported_memberships
                ),
                api_requests,
                warning_message
            )

            raise


        print()
        print(
            "import completed"
        )


        print(
            f"API requests: {api_requests}"
        )

        print(
            f"player records received: "
            f"{rows_received}"
        )

        print(
            f"unique players: "
            f"{len(imported_players)}"
        )

        print(
            f"squad memberships: "
            f"{len(imported_memberships)}"
        )


        if truncated_teams:
            print()
            print(
                "partial teams because of free plan:"
            )


            for team in truncated_teams:
                print(
                    f"- {team['team_name']}: "
                    f"{MAX_FREE_PAGE}/"
                    f"{team['reported_pages']} pages"
                )


            print()

            print(
                "these teams are not marked "
                "as complete historical squads"
            )

        else:
            print()

            print(
                "all teams imported completely"
            )


def main():
    arguments = parse_arguments()


    import_players(
        arguments.league,
        arguments.season
    )


if __name__ == "__main__":
    main()