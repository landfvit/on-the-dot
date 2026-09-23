import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


# connect to database
conn = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)


checks = []


# fixtures without teams
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixtures f
        LEFT JOIN teams home
            ON f.home_team_id = home.team_id
        LEFT JOIN teams away
            ON f.away_team_id = away.team_id
        WHERE home.team_id IS NULL
           OR away.team_id IS NULL;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "fixtures without valid teams",
            count
        )
    )


# finished fixtures without goals
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixtures
        WHERE status = 'FT'
          AND (
              home_goals IS NULL
              OR away_goals IS NULL
          );
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "finished fixtures without goals",
            count
        )
    )


# fixtures with negative goals
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixtures
        WHERE home_goals < 0
           OR away_goals < 0;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "fixtures with negative goals",
            count
        )
    )


# statistics without both teams
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixture_data_status
        WHERE data_status = 'partial';
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "fixtures with partial statistics",
            count
        )
    )


# possession outside valid range
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixture_statistics
        WHERE ball_possession < 0
           OR ball_possession > 100;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "invalid possession values",
            count
        )
    )


# pass percentage outside valid range
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixture_statistics
        WHERE passes_percentage < 0
           OR passes_percentage > 100;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "invalid pass percentage values",
            count
        )
    )


# negative statistics
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixture_statistics
        WHERE shots_on_goal < 0
           OR shots_off_goal < 0
           OR total_shots < 0
           OR blocked_shots < 0
           OR fouls < 0
           OR corner_kicks < 0
           OR offsides < 0
           OR yellow_cards < 0
           OR red_cards < 0
           OR goalkeeper_saves < 0
           OR total_passes < 0
           OR passes_accurate < 0;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "negative statistics values",
            count
        )
    )


# accurate passes greater than total passes
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixture_statistics
        WHERE passes_accurate > total_passes;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "accurate passes greater than total passes",
            count
        )
    )


# shots on goal greater than total shots
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM fixture_statistics
        WHERE shots_on_goal > total_shots;
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "shots on goal greater than total shots",
            count
        )
    )


# unfinished import runs
with conn.cursor() as cursor:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM import_runs
        WHERE status = 'running';
        """
    )

    count = cursor.fetchone()[0]

    checks.append(
        (
            "unfinished import runs",
            count
        )
    )


conn.close()


print()
print("DATA QUALITY")
print()


issues_found = False


for check_name, count in checks:

    if count == 0:
        status = "OK"
    else:
        status = "ISSUE"
        issues_found = True

    print(
        f"{status:<8}"
        f"{check_name:<45}"
        f"{count}"
    )


print()

if issues_found:
    print(
        "data quality check finished with issues"
    )
else:
    print(
        "all data quality checks passed"
    )