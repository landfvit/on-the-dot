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

# pro allows up to 5 requests per second
REQUEST_DELAY_SECONDS = 0.25

MAX_RETRIES = 5


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Import league players and season statistics."
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


def parse_integer(value):
    if value is None:
        return None

    try:
        return int(
            float(
                str(value).strip()
            )
        )

    except (
        ValueError,
        TypeError
    ):
        return None


def parse_float(value):
    if value is None:
        return None

    try:
        return float(
            str(value)
            .replace("%", "")
            .strip()
        )

    except (
        ValueError,
        TypeError
    ):
        return None


def parse_measurement(value):
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
    url = f"{BASE_URL}/{endpoint}"

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
                f"request error, retry "
                f"{attempt}/{MAX_RETRIES}"
            )

            time.sleep(
                2
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

            wait_seconds = 2


            if retry_after:
                try:
                    wait_seconds = max(
                        float(retry_after),
                        1
                    )

                except ValueError:
                    pass


            print(
                f"rate limit reached, "
                f"waiting {wait_seconds}s"
            )

            time.sleep(
                wait_seconds
            )

            continue


        if not response.ok:
            raise RuntimeError(
                f"API returned HTTP "
                f"{response.status_code}: "
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


        daily_remaining = response.headers.get(
            "x-ratelimit-requests-remaining"
        )

        minute_remaining = response.headers.get(
            "X-RateLimit-Remaining"
        )


        if daily_remaining is not None:
            print(
                f"daily remaining: "
                f"{daily_remaining}"
            )


        if minute_remaining is not None:
            print(
                f"minute remaining: "
                f"{minute_remaining}"
            )


        return data


    raise RuntimeError(
        "API request failed"
    )


def get_participating_team_ids(
    connection,
    league_id,
    season
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT team_id

            FROM (

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

            WHERE team_id IS NOT NULL

            ORDER BY team_id;
            """,
            (
                league_id,
                season,
                league_id,
                season
            )
        )

        rows = cursor.fetchall()


    return {
        row["team_id"]
        for row in rows
    }


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
                'players_full',
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

                parse_measurement(
                    player.get(
                        "height"
                    )
                ),

                parse_measurement(
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
    team_id,
    player,
    statistics
):
    games = (
        statistics.get(
            "games"
        )
        or {}
    )


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
                player["id"],

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


def upsert_player_statistics(
    connection,
    league_id,
    season,
    team_id,
    player_id,
    statistics
):
    games = (
        statistics.get("games")
        or {}
    )

    substitutes = (
        statistics.get("substitutes")
        or {}
    )

    shots = (
        statistics.get("shots")
        or {}
    )

    goals = (
        statistics.get("goals")
        or {}
    )

    passes = (
        statistics.get("passes")
        or {}
    )

    tackles = (
        statistics.get("tackles")
        or {}
    )

    duels = (
        statistics.get("duels")
        or {}
    )

    dribbles = (
        statistics.get("dribbles")
        or {}
    )

    fouls = (
        statistics.get("fouls")
        or {}
    )

    cards = (
        statistics.get("cards")
        or {}
    )

    penalty = (
        statistics.get("penalty")
        or {}
    )


    appearances = games.get(
        "appearences"
    )

    if appearances is None:
        appearances = games.get(
            "appearances"
        )


    penalties_committed = penalty.get(
        "commited"
    )

    if penalties_committed is None:
        penalties_committed = penalty.get(
            "committed"
        )


    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO player_season_statistics (

                league_id,
                season,
                team_id,
                player_id,

                appearances,
                lineups,
                minutes,

                squad_number,
                position,

                rating,
                captain,

                substitutes_in,
                substitutes_out,
                substitutes_bench,

                shots_total,
                shots_on_goal,

                goals_total,
                goals_conceded,
                assists,
                saves,

                passes_total,
                key_passes,
                pass_accuracy,

                tackles_total,
                blocks,
                interceptions,

                duels_total,
                duels_won,

                dribbles_attempts,
                dribbles_success,
                dribbled_past,

                fouls_drawn,
                fouls_committed,

                yellow_cards,
                yellow_red_cards,
                red_cards,

                penalties_won,
                penalties_committed,
                penalties_scored,
                penalties_missed,
                penalties_saved,

                updated_at
            )

            VALUES (

                %s, %s, %s, %s,

                %s, %s, %s,

                %s, %s,

                %s, %s,

                %s, %s, %s,

                %s, %s,

                %s, %s, %s, %s,

                %s, %s, %s,

                %s, %s, %s,

                %s, %s,

                %s, %s, %s,

                %s, %s,

                %s, %s, %s,

                %s, %s, %s, %s, %s,

                NOW()
            )

            ON CONFLICT (
                league_id,
                season,
                team_id,
                player_id
            )

            DO UPDATE SET

                appearances =
                    EXCLUDED.appearances,

                lineups =
                    EXCLUDED.lineups,

                minutes =
                    EXCLUDED.minutes,

                squad_number =
                    EXCLUDED.squad_number,

                position =
                    EXCLUDED.position,

                rating =
                    EXCLUDED.rating,

                captain =
                    EXCLUDED.captain,

                substitutes_in =
                    EXCLUDED.substitutes_in,

                substitutes_out =
                    EXCLUDED.substitutes_out,

                substitutes_bench =
                    EXCLUDED.substitutes_bench,

                shots_total =
                    EXCLUDED.shots_total,

                shots_on_goal =
                    EXCLUDED.shots_on_goal,

                goals_total =
                    EXCLUDED.goals_total,

                goals_conceded =
                    EXCLUDED.goals_conceded,

                assists =
                    EXCLUDED.assists,

                saves =
                    EXCLUDED.saves,

                passes_total =
                    EXCLUDED.passes_total,

                key_passes =
                    EXCLUDED.key_passes,

                pass_accuracy =
                    EXCLUDED.pass_accuracy,

                tackles_total =
                    EXCLUDED.tackles_total,

                blocks =
                    EXCLUDED.blocks,

                interceptions =
                    EXCLUDED.interceptions,

                duels_total =
                    EXCLUDED.duels_total,

                duels_won =
                    EXCLUDED.duels_won,

                dribbles_attempts =
                    EXCLUDED.dribbles_attempts,

                dribbles_success =
                    EXCLUDED.dribbles_success,

                dribbled_past =
                    EXCLUDED.dribbled_past,

                fouls_drawn =
                    EXCLUDED.fouls_drawn,

                fouls_committed =
                    EXCLUDED.fouls_committed,

                yellow_cards =
                    EXCLUDED.yellow_cards,

                yellow_red_cards =
                    EXCLUDED.yellow_red_cards,

                red_cards =
                    EXCLUDED.red_cards,

                penalties_won =
                    EXCLUDED.penalties_won,

                penalties_committed =
                    EXCLUDED.penalties_committed,

                penalties_scored =
                    EXCLUDED.penalties_scored,

                penalties_missed =
                    EXCLUDED.penalties_missed,

                penalties_saved =
                    EXCLUDED.penalties_saved,

                updated_at =
                    NOW();
            """,
            (
                league_id,
                season,
                team_id,
                player_id,

                parse_integer(
                    appearances
                ),

                parse_integer(
                    games.get("lineups")
                ),

                parse_integer(
                    games.get("minutes")
                ),

                parse_integer(
                    games.get("number")
                ),

                games.get("position"),

                parse_float(
                    games.get("rating")
                ),

                games.get("captain"),

                parse_integer(
                    substitutes.get("in")
                ),

                parse_integer(
                    substitutes.get("out")
                ),

                parse_integer(
                    substitutes.get("bench")
                ),

                parse_integer(
                    shots.get("total")
                ),

                parse_integer(
                    shots.get("on")
                ),

                parse_integer(
                    goals.get("total")
                ),

                parse_integer(
                    goals.get("conceded")
                ),

                parse_integer(
                    goals.get("assists")
                ),

                parse_integer(
                    goals.get("saves")
                ),

                parse_integer(
                    passes.get("total")
                ),

                parse_integer(
                    passes.get("key")
                ),

                parse_float(
                    passes.get("accuracy")
                ),

                parse_integer(
                    tackles.get("total")
                ),

                parse_integer(
                    tackles.get("blocks")
                ),

                parse_integer(
                    tackles.get("interceptions")
                ),

                parse_integer(
                    duels.get("total")
                ),

                parse_integer(
                    duels.get("won")
                ),

                parse_integer(
                    dribbles.get("attempts")
                ),

                parse_integer(
                    dribbles.get("success")
                ),

                parse_integer(
                    dribbles.get("past")
                ),

                parse_integer(
                    fouls.get("drawn")
                ),

                parse_integer(
                    fouls.get("committed")
                ),

                parse_integer(
                    cards.get("yellow")
                ),

                parse_integer(
                    cards.get("yellowred")
                ),

                parse_integer(
                    cards.get("red")
                ),

                parse_integer(
                    penalty.get("won")
                ),

                parse_integer(
                    penalties_committed
                ),

                parse_integer(
                    penalty.get("scored")
                ),

                parse_integer(
                    penalty.get("missed")
                ),

                parse_integer(
                    penalty.get("saved")
                )
            )
        )


def import_players(
    league_id,
    season
):
    API_key = get_API_key()


    with get_connection() as connection:
        team_ids = get_participating_team_ids(
            connection,
            league_id,
            season
        )


        if not team_ids:
            raise RuntimeError(
                "No teams found for this league and season"
            )


        print(
            f"league: {league_id}"
        )

        print(
            f"season: {season}"
        )

        print(
            f"teams in database: {len(team_ids)}"
        )


        import_run_id = create_import_run(
            connection,
            league_id,
            season
        )


        page = 1
        total_pages = 1

        api_requests = 0
        rows_received = 0

        imported_players = set()
        imported_memberships = set()
        imported_statistics = set()


        try:
            while page <= total_pages:
                print()

                print(
                    f"requesting page "
                    f"{page}/{total_pages}"
                )


                data = make_request(
                    "players",
                    {
                        "league": league_id,
                        "season": season,
                        "page": page
                    },
                    API_key
                )


                api_requests += 1


                paging = (
                    data.get("paging")
                    or {}
                )


                total_pages = int(
                    paging.get(
                        "total",
                        1
                    )
                )


                response_rows = (
                    data.get("response")
                    or []
                )


                rows_received += len(
                    response_rows
                )


                for item in response_rows:
                    player = (
                        item.get("player")
                        or {}
                    )

                    statistics_list = (
                        item.get("statistics")
                        or []
                    )


                    player_id = player.get(
                        "id"
                    )


                    if player_id is None:
                        continue


                    if upsert_player(
                        connection,
                        player
                    ):
                        imported_players.add(
                            player_id
                        )


                    for statistics in statistics_list:
                        team = (
                            statistics.get("team")
                            or {}
                        )

                        league = (
                            statistics.get("league")
                            or {}
                        )


                        team_id = team.get(
                            "id"
                        )

                        statistics_league_id = (
                            league.get("id")
                        )

                        statistics_season = (
                            league.get("season")
                        )


                        if team_id is None:
                            continue

                        if team_id not in team_ids:
                            continue

                        if (
                            statistics_league_id
                            != league_id
                        ):
                            continue

                        if statistics_season is None:
                            continue

                        if (
                            int(statistics_season)
                            != season
                        ):
                            continue


                        upsert_membership(
                            connection,
                            league_id,
                            season,
                            team_id,
                            player,
                            statistics
                        )


                        upsert_player_statistics(
                            connection,
                            league_id,
                            season,
                            team_id,
                            player_id,
                            statistics
                        )


                        membership_key = (
                            league_id,
                            season,
                            team_id,
                            player_id
                        )


                        imported_memberships.add(
                            membership_key
                        )

                        imported_statistics.add(
                            membership_key
                        )


                connection.commit()


                print(
                    f"page {page}/{total_pages} complete"
                )

                print(
                    f"unique players: "
                    f"{len(imported_players)}"
                )

                print(
                    f"memberships: "
                    f"{len(imported_memberships)}"
                )

                print(
                    f"statistics rows: "
                    f"{len(imported_statistics)}"
                )


                page += 1


                if page <= total_pages:
                    time.sleep(
                        REQUEST_DELAY_SECONDS
                    )


            finish_import_run(
                connection,
                import_run_id,
                "completed",
                rows_received,
                len(imported_statistics),
                api_requests
            )


        except Exception as error:
            connection.rollback()


            finish_import_run(
                connection,
                import_run_id,
                "failed",
                rows_received,
                len(imported_statistics),
                api_requests,
                str(error)
            )


            raise


        print()
        print(
            "import completed"
        )

        print(
            f"API requests: "
            f"{api_requests}"
        )

        print(
            f"records received: "
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

        print(
            f"player statistics rows: "
            f"{len(imported_statistics)}"
        )


def main():
    arguments = parse_arguments()


    import_players(
        arguments.league,
        arguments.season
    )


if __name__ == "__main__":
    main()