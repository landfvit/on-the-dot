import os
import sys

from pathlib import Path

import psycopg
import requests

from dotenv import load_dotenv


BASE_DIR = Path(
    __file__
).resolve().parent.parent


load_dotenv(
    BASE_DIR / ".env"
)


API_key = os.getenv(
    "API_FOOTBALL_KEY"
)


API_BASE_URL = (
    "https://v3.football.api-sports.io"
)


DB_HOST = os.getenv(
    "DB_HOST"
)

DB_PORT = os.getenv(
    "DB_PORT"
)

DB_NAME = os.getenv(
    "DB_NAME"
)

DB_USER = os.getenv(
    "DB_USER"
)

DB_PASSWORD = os.getenv(
    "DB_PASSWORD"
)


LEAGUE_ID = 39
SEASON = 2024


def get_connection():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def api_get(
    endpoint,
    params=None
):
    headers = {
        "x-apisports-key": API_key
    }


    response = requests.get(
        f"{API_BASE_URL}{endpoint}",
        headers=headers,
        params=params,
        timeout=30
    )


    response.raise_for_status()


    data = response.json()


    errors = data.get(
        "errors"
    )


    if errors:
        raise RuntimeError(
            f"api error: {errors}"
        )


    remaining_daily = response.headers.get(
        "x-ratelimit-requests-remaining"
    )


    remaining_minute = response.headers.get(
        "X-RateLimit-Remaining"
    )


    print(
        f"GET {endpoint}"
    )


    print(
        f"daily remaining: {remaining_daily}"
    )


    print(
        f"minute remaining: {remaining_minute}"
    )


    return data


def start_import_run(
    conn
):
    with conn.cursor() as cursor:
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
                %s,
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
                "branding",
                LEAGUE_ID,
                SEASON
            )
        )


        row = cursor.fetchone()


    conn.commit()


    return row[0]


def finish_import_run(
    conn,
    import_run_id,
    status,
    rows_received,
    rows_inserted,
    api_requests,
    error_message=None
):
    with conn.cursor() as cursor:
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


    conn.commit()


def import_countries(
    conn
):
    data = api_get(
        "/countries"
    )


    response = data.get(
        "response",
        []
    )


    country_map = {}


    with conn.cursor() as cursor:
        for country in response:
            country_name = country.get(
                "name"
            )


            country_code = country.get(
                "code"
            )


            flag_url = country.get(
                "flag"
            )


            if (
                not country_name
                or not country_code
            ):
                continue


            cursor.execute(
                """
                INSERT INTO countries (
                    country_code,
                    country_name,
                    flag_url,
                    updated_at
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    NOW()
                )

                ON CONFLICT (
                    country_code
                )

                DO UPDATE SET
                    country_name =
                        EXCLUDED.country_name,

                    flag_url =
                        EXCLUDED.flag_url,

                    updated_at =
                        NOW();
                """,
                (
                    country_code,
                    country_name,
                    flag_url
                )
            )


            country_map[
                country_name.casefold()
            ] = {
                "code": country_code,
                "flag_url": flag_url
            }


    conn.commit()


    print(
        f"countries updated: {len(country_map)}"
    )


    return (
        len(response),
        len(country_map),
        country_map
    )


def import_league(
    conn,
    country_map
):
    data = api_get(
        "/leagues",
        {
            "id": LEAGUE_ID
        }
    )


    response = data.get(
        "response",
        []
    )


    if not response:
        raise RuntimeError(
            "league was not returned by api"
        )


    item = response[0]


    league = item.get(
        "league",
        {}
    )


    country = item.get(
        "country",
        {}
    )


    league_id = league.get(
        "id"
    )


    league_name = league.get(
        "name"
    )


    logo_url = league.get(
        "logo"
    )


    country_name = country.get(
        "name"
    )


    country_code = country.get(
        "code"
    )


    country_flag_url = country.get(
        "flag"
    )


    if (
        country_name
        and country_name.casefold()
        in country_map
    ):
        country_data = country_map[
            country_name.casefold()
        ]


        country_code = (
            country_code
            or country_data["code"]
        )


        country_flag_url = (
            country_flag_url
            or country_data["flag_url"]
        )


    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE leagues

            SET
                league_name = COALESCE(
                    %s,
                    league_name
                ),

                country_name = COALESCE(
                    %s,
                    country_name
                ),

                logo_url = %s,

                country_code = %s,

                country_flag_url = %s

            WHERE league_id = %s;
            """,
            (
                league_name,
                country_name,
                logo_url,
                country_code,
                country_flag_url,
                league_id
            )
        )


    conn.commit()


    print(
        f"league updated: {league_name}"
    )


    return 1


def import_teams(
    conn,
    country_map
):
    data = api_get(
        "/teams",
        {
            "league": LEAGUE_ID,
            "season": SEASON
        }
    )


    response = data.get(
        "response",
        []
    )


    rows_inserted = 0


    with conn.cursor() as cursor:
        for item in response:
            team = item.get(
                "team",
                {}
            )


            team_id = team.get(
                "id"
            )


            team_name = team.get(
                "name"
            )


            team_code = team.get(
                "code"
            )


            country_name = team.get(
                "country"
            )


            logo_url = team.get(
                "logo"
            )


            country_code = None


            if country_name:
                country_data = country_map.get(
                    country_name.casefold()
                )


                if country_data:
                    country_code = (
                        country_data["code"]
                    )


            if team_id is None:
                continue


            cursor.execute(
                """
                INSERT INTO teams (
                    team_id,
                    team_name,
                    team_code,
                    country_name,
                    country_code,
                    logo_url
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                ON CONFLICT (
                    team_id
                )

                DO UPDATE SET
                    team_name =
                        EXCLUDED.team_name,

                    team_code =
                        EXCLUDED.team_code,

                    country_name =
                        EXCLUDED.country_name,

                    country_code =
                        EXCLUDED.country_code,

                    logo_url =
                        EXCLUDED.logo_url;
                """,
                (
                    team_id,
                    team_name,
                    team_code,
                    country_name,
                    country_code,
                    logo_url
                )
            )


            rows_inserted += 1


    conn.commit()


    print(
        f"teams updated: {rows_inserted}"
    )


    return (
        len(response),
        rows_inserted
    )


def main():
    if not API_key:
        print(
            "API_FOOTBALL_KEY is missing"
        )


        sys.exit(
            1
        )


    rows_received = 0
    rows_inserted = 0
    api_requests = 0


    with get_connection() as conn:
        import_run_id = start_import_run(
            conn
        )


        try:
            (
                country_rows_received,
                country_rows_inserted,
                country_map
            ) = import_countries(
                conn
            )


            rows_received += (
                country_rows_received
            )


            rows_inserted += (
                country_rows_inserted
            )


            api_requests += 1


            league_rows = import_league(
                conn,
                country_map
            )


            rows_received += (
                league_rows
            )


            rows_inserted += (
                league_rows
            )


            api_requests += 1


            (
                team_rows_received,
                team_rows_inserted
            ) = import_teams(
                conn,
                country_map
            )


            rows_received += (
                team_rows_received
            )


            rows_inserted += (
                team_rows_inserted
            )


            api_requests += 1


            finish_import_run(
                conn=conn,
                import_run_id=import_run_id,
                status="success",
                rows_received=rows_received,
                rows_inserted=rows_inserted,
                api_requests=api_requests
            )


            print(
                "branding import completed"
            )


            print(
                f"rows received: {rows_received}"
            )


            print(
                f"rows inserted/updated: {rows_inserted}"
            )


            print(
                f"api requests: {api_requests}"
            )


        except Exception as error:
            conn.rollback()


            finish_import_run(
                conn=conn,
                import_run_id=import_run_id,
                status="failed",
                rows_received=rows_received,
                rows_inserted=rows_inserted,
                api_requests=api_requests,
                error_message=str(
                    error
                )
            )


            print(
                f"branding import failed: {error}"
            )


            raise


if __name__ == "__main__":
    main()