import os

import psycopg
import requests
from dotenv import load_dotenv


load_dotenv()

API_key = os.getenv("API_FOOTBALL_KEY")

url = "https://v3.football.api-sports.io/fixtures"

headers = {
    "x-apisports-key": API_key
}

league_id = 39

seasons = [
    2022,
    2023,
    2024
]


def create_import_run(conn, season):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO import_runs (
                import_type,
                league_id,
                season
            )
            VALUES (%s, %s, %s)
            RETURNING import_run_id;
            """,
            (
                "fixtures",
                league_id,
                season
            )
        )

        import_run_id = cursor.fetchone()[0]

    conn.commit()

    return import_run_id


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


# connect to database
conn = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)


for season in seasons:

    print()
    print("importing season:", season)

    import_run_id = create_import_run(
        conn,
        season
    )

    rows_received = 0
    rows_inserted = 0
    api_requests = 0

    try:

        params = {
            "league": league_id,
            "season": season
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )

        api_requests += 1

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):

            error_message = str(
                data["errors"]
            )

            print(
                "api error:",
                error_message
            )

            finish_import_run(
                conn,
                import_run_id,
                "failed",
                rows_received,
                rows_inserted,
                api_requests,
                error_message
            )

            continue

        rows_received = len(
            data["response"]
        )

        print(
            "total fixtures:",
            rows_received
        )

        with conn.cursor() as cursor:

            for match in data["response"]:

                fixture = match["fixture"]
                league = match["league"]
                teams = match["teams"]
                goals = match["goals"]

                home_team = teams["home"]
                away_team = teams["away"]

                # insert league
                cursor.execute(
                    """
                    INSERT INTO leagues (
                        league_id,
                        league_name,
                        country_name
                    )
                    VALUES (%s, %s, %s)

                    ON CONFLICT (league_id)
                    DO UPDATE SET
                        league_name =
                            EXCLUDED.league_name,

                        country_name =
                            EXCLUDED.country_name;
                    """,
                    (
                        league["id"],
                        league["name"],
                        league["country"]
                    )
                )

                # insert season
                cursor.execute(
                    """
                    INSERT INTO seasons (
                        league_id,
                        season
                    )
                    VALUES (%s, %s)

                    ON CONFLICT (
                        league_id,
                        season
                    )
                    DO NOTHING;
                    """,
                    (
                        league["id"],
                        league["season"]
                    )
                )

                # insert home team
                cursor.execute(
                    """
                    INSERT INTO teams (
                        team_id,
                        team_name
                    )
                    VALUES (%s, %s)

                    ON CONFLICT (team_id)
                    DO UPDATE SET
                        team_name =
                            EXCLUDED.team_name;
                    """,
                    (
                        home_team["id"],
                        home_team["name"]
                    )
                )

                # insert away team
                cursor.execute(
                    """
                    INSERT INTO teams (
                        team_id,
                        team_name
                    )
                    VALUES (%s, %s)

                    ON CONFLICT (team_id)
                    DO UPDATE SET
                        team_name =
                            EXCLUDED.team_name;
                    """,
                    (
                        away_team["id"],
                        away_team["name"]
                    )
                )

                # insert fixture
                cursor.execute(
                    """
                    INSERT INTO fixtures (
                        fixture_id,
                        league_id,
                        season,
                        match_date,
                        status,
                        home_team_id,
                        away_team_id,
                        home_goals,
                        away_goals
                    )
                    VALUES (
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s
                    )

                    ON CONFLICT (fixture_id)
                    DO UPDATE SET
                        league_id =
                            EXCLUDED.league_id,

                        season =
                            EXCLUDED.season,

                        match_date =
                            EXCLUDED.match_date,

                        status =
                            EXCLUDED.status,

                        home_team_id =
                            EXCLUDED.home_team_id,

                        away_team_id =
                            EXCLUDED.away_team_id,

                        home_goals =
                            EXCLUDED.home_goals,

                        away_goals =
                            EXCLUDED.away_goals;
                    """,
                    (
                        fixture["id"],
                        league["id"],
                        league["season"],
                        fixture["date"],
                        fixture["status"]["short"],
                        home_team["id"],
                        away_team["id"],
                        goals["home"],
                        goals["away"]
                    )
                )

                rows_inserted += 1

        conn.commit()

        finish_import_run(
            conn,
            import_run_id,
            "success",
            rows_received,
            rows_inserted,
            api_requests
        )

        print(
            "season saved:",
            season
        )

        print(
            "remaining requests:",
            response.headers.get(
                "x-ratelimit-requests-remaining"
            )
        )

    except Exception as error:

        conn.rollback()

        error_message = str(error)

        print(
            "import failed:",
            error_message
        )

        finish_import_run(
            conn,
            import_run_id,
            "failed",
            rows_received,
            rows_inserted,
            api_requests,
            error_message
        )


conn.close()

print()
print("fixtures import finished")