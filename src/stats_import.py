import os
import time

import psycopg
import requests
from dotenv import load_dotenv


load_dotenv()

API_key = os.getenv("API_FOOTBALL_KEY")

url = "https://v3.football.api-sports.io/fixtures/statistics"

headers = {
    "x-apisports-key": API_key
}

league_id = 39
season = 2024

batch_size = 20
request_delay = 7
max_retries = 5


def percentage_to_number(value):
    if value is None:
        return None

    return float(
        str(value).replace("%", "")
    )


def create_import_run(conn):
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
                "fixture_statistics",
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


import_run_id = create_import_run(
    conn
)

rows_received = 0
rows_inserted = 0
api_requests = 0

failed_fixtures = []


# find fixtures with missing statistics
with conn.cursor() as cursor:

    cursor.execute(
        """
        SELECT
            f.fixture_id

        FROM fixtures f

        LEFT JOIN fixture_statistics s
            ON f.fixture_id = s.fixture_id

        WHERE f.status = 'FT'
          AND f.league_id = %s
          AND f.season = %s

        GROUP BY f.fixture_id

        HAVING COUNT(
            DISTINCT s.team_id
        ) < 2

        ORDER BY MIN(
            f.match_date
        )

        LIMIT %s;
        """,
        (
            league_id,
            season,
            batch_size
        )
    )

    fixtures = cursor.fetchall()


print()
print(
    "fixtures to import:",
    len(fixtures)
)


for fixture_row in fixtures:

    fixture_id = fixture_row[0]

    print()
    print(
        "fixture:",
        fixture_id
    )

    data = None
    request_success = False

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            response = requests.get(
                url,
                headers=headers,
                params={
                    "fixture": fixture_id
                },
                timeout=30
            )

            api_requests += 1

            response.raise_for_status()

            data = response.json()

        except Exception as error:

            print(
                "request failed:",
                error
            )

            if attempt < max_retries:
                time.sleep(10)

            continue

        if data.get("errors"):

            if data["errors"].get(
                "rateLimit"
            ):

                print(
                    "rate limit reached, waiting..."
                )

                if attempt < max_retries:
                    time.sleep(10)

                continue

            print(
                "api error:",
                data["errors"]
            )

            break

        request_success = True
        break


    if not request_success:

        failed_fixtures.append(
            fixture_id
        )

        print(
            "fixture skipped:",
            fixture_id
        )

        time.sleep(
            request_delay
        )

        continue


    team_statistics = data.get(
        "response",
        []
    )

    rows_received += len(
        team_statistics
    )


    try:

        with conn.cursor() as cursor:

            for team_data in team_statistics:

                team_id = team_data[
                    "team"
                ]["id"]

                stats = {
                    stat["type"]:
                        stat["value"]

                    for stat in team_data[
                        "statistics"
                    ]
                }

                cursor.execute(
                    """
                    INSERT INTO fixture_statistics (
                        fixture_id,
                        team_id,

                        shots_on_goal,
                        shots_off_goal,
                        total_shots,
                        blocked_shots,
                        shots_inside_box,
                        shots_outside_box,

                        fouls,
                        corner_kicks,
                        offsides,

                        ball_possession,

                        yellow_cards,
                        red_cards,

                        goalkeeper_saves,

                        total_passes,
                        passes_accurate,
                        passes_percentage
                    )
                    VALUES (
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s,
                        %s, %s,
                        %s,
                        %s, %s, %s
                    )

                    ON CONFLICT (
                        fixture_id,
                        team_id
                    )

                    DO UPDATE SET
                        shots_on_goal =
                            EXCLUDED.shots_on_goal,

                        shots_off_goal =
                            EXCLUDED.shots_off_goal,

                        total_shots =
                            EXCLUDED.total_shots,

                        blocked_shots =
                            EXCLUDED.blocked_shots,

                        shots_inside_box =
                            EXCLUDED.shots_inside_box,

                        shots_outside_box =
                            EXCLUDED.shots_outside_box,

                        fouls =
                            EXCLUDED.fouls,

                        corner_kicks =
                            EXCLUDED.corner_kicks,

                        offsides =
                            EXCLUDED.offsides,

                        ball_possession =
                            EXCLUDED.ball_possession,

                        yellow_cards =
                            EXCLUDED.yellow_cards,

                        red_cards =
                            EXCLUDED.red_cards,

                        goalkeeper_saves =
                            EXCLUDED.goalkeeper_saves,

                        total_passes =
                            EXCLUDED.total_passes,

                        passes_accurate =
                            EXCLUDED.passes_accurate,

                        passes_percentage =
                            EXCLUDED.passes_percentage;
                    """,
                    (
                        fixture_id,
                        team_id,

                        stats.get(
                            "Shots on Goal"
                        ),

                        stats.get(
                            "Shots off Goal"
                        ),

                        stats.get(
                            "Total Shots"
                        ),

                        stats.get(
                            "Blocked Shots"
                        ),

                        stats.get(
                            "Shots insidebox"
                        ),

                        stats.get(
                            "Shots outsidebox"
                        ),

                        stats.get(
                            "Fouls"
                        ),

                        stats.get(
                            "Corner Kicks"
                        ),

                        stats.get(
                            "Offsides"
                        ),

                        percentage_to_number(
                            stats.get(
                                "Ball Possession"
                            )
                        ),

                        stats.get(
                            "Yellow Cards"
                        ),

                        stats.get(
                            "Red Cards"
                        ),

                        stats.get(
                            "Goalkeeper Saves"
                        ),

                        stats.get(
                            "Total passes"
                        ),

                        stats.get(
                            "Passes accurate"
                        ),

                        percentage_to_number(
                            stats.get(
                                "Passes %"
                            )
                        )
                    )
                )

                rows_inserted += 1

        conn.commit()

        print(
            "saved statistics:",
            len(team_statistics)
        )

    except Exception as error:

        conn.rollback()

        failed_fixtures.append(
            fixture_id
        )

        print(
            "database error:",
            error
        )


    time.sleep(
        request_delay
    )


if failed_fixtures:

    status = "partial"

    error_message = (
        "failed fixtures: "
        + ", ".join(
            str(fixture_id)
            for fixture_id
            in failed_fixtures
        )
    )

else:

    status = "success"
    error_message = None


finish_import_run(
    conn,
    import_run_id,
    status,
    rows_received,
    rows_inserted,
    api_requests,
    error_message
)


conn.close()


print()
print("statistics import finished")

print(
    "status:",
    status
)

print(
    "api requests:",
    api_requests
)

print(
    "rows received:",
    rows_received
)

print(
    "rows saved:",
    rows_inserted
)

print(
    "failed fixtures:",
    len(failed_fixtures)
)