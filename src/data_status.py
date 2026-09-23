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


# load season summary
with conn.cursor() as cursor:

    cursor.execute(
        """
        SELECT
            season,
            teams,
            total_fixtures,
            finished_fixtures,
            fixtures_with_complete_stats,
            fixtures_with_partial_stats,
            fixtures_without_stats,
            statistics_coverage_percentage
        FROM season_data_summary
        ORDER BY season;
        """
    )

    season_rows = cursor.fetchall()


print()
print("DATA STATUS")
print()

print(
    f"{'season':<8}"
    f"{'teams':<8}"
    f"{'fixtures':<12}"
    f"{'finished':<12}"
    f"{'complete':<12}"
    f"{'partial':<10}"
    f"{'missing':<10}"
    f"{'coverage':<10}"
)


for row in season_rows:

    season = row[0]
    teams = row[1]
    total_fixtures = row[2]
    finished_fixtures = row[3]
    complete_stats = row[4]
    partial_stats = row[5]
    missing_stats = row[6]
    coverage = row[7]

    print(
        f"{season:<8}"
        f"{teams:<8}"
        f"{total_fixtures:<12}"
        f"{finished_fixtures:<12}"
        f"{complete_stats:<12}"
        f"{partial_stats:<10}"
        f"{missing_stats:<10}"
        f"{str(coverage) + '%':<10}"
    )


# load incomplete statistics
with conn.cursor() as cursor:

    cursor.execute(
        """
        SELECT
            COUNT(*)
        FROM fixture_data_status
        WHERE data_status = 'partial';
        """
    )

    partial_count = cursor.fetchone()[0]


print()
print(
    "fixtures with partial statistics:",
    partial_count
)


# load latest imports
with conn.cursor() as cursor:

    cursor.execute(
        """
        SELECT
            import_run_id,
            import_type,
            season,
            status,
            started_at,
            finished_at,
            rows_received,
            rows_inserted,
            api_requests
        FROM import_runs
        ORDER BY started_at DESC
        LIMIT 10;
        """
    )

    import_rows = cursor.fetchall()


print()
print("RECENT IMPORTS")
print()


if not import_rows:

    print("no import runs recorded yet")

else:

    for row in import_rows:

        print(
            "id:",
            row[0],
            "| type:",
            row[1],
            "| season:",
            row[2],
            "| status:",
            row[3],
            "| received:",
            row[6],
            "| inserted:",
            row[7],
            "| requests:",
            row[8]
        )


conn.close()