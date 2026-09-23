import json
import os

from datetime import datetime, timezone
from pathlib import Path

import psycopg

from dotenv import load_dotenv
from psycopg.rows import dict_row


BASE_DIR = Path(
    __file__
).resolve().parent.parent


load_dotenv(
    BASE_DIR / ".env"
)


OUTPUT_DIR = (
    BASE_DIR
    / "web"
    / "static"
    / "data"
)


OUTPUT_FILE = (
    OUTPUT_DIR
    / "entity_branding.json"
)


def get_connection():
    return psycopg.connect(
        host=os.getenv(
            "DB_HOST"
        ),
        port=os.getenv(
            "DB_PORT"
        ),
        dbname=os.getenv(
            "DB_NAME"
        ),
        user=os.getenv(
            "DB_USER"
        ),
        password=os.getenv(
            "DB_PASSWORD"
        ),
        row_factory=dict_row
    )


def load_teams(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                team_id,
                team_name,
                team_code,
                country_name,
                country_code,
                logo_url
            FROM teams
            WHERE logo_url IS NOT NULL
            ORDER BY team_name;
            """
        )

        rows = cursor.fetchall()


    teams = {}


    for row in rows:
        teams[
            str(
                row["team_id"]
            )
        ] = {
            "id": row[
                "team_id"
            ],
            "name": row[
                "team_name"
            ],
            "code": row[
                "team_code"
            ],
            "country_name": row[
                "country_name"
            ],
            "country_code": row[
                "country_code"
            ],
            "logo_url": row[
                "logo_url"
            ]
        }


    return teams


def load_competitions(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                league_id,
                league_name,
                country_name,
                country_code,
                country_flag_url,
                logo_url
            FROM leagues
            WHERE logo_url IS NOT NULL
            ORDER BY league_name;
            """
        )

        rows = cursor.fetchall()


    competitions = {}


    for row in rows:
        competitions[
            str(
                row["league_id"]
            )
        ] = {
            "id": row[
                "league_id"
            ],
            "name": row[
                "league_name"
            ],
            "country_name": row[
                "country_name"
            ],
            "country_code": row[
                "country_code"
            ],
            "flag_url": row[
                "country_flag_url"
            ],
            "logo_url": row[
                "logo_url"
            ]
        }


    return competitions


def load_countries(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                country_code,
                country_name,
                flag_url
            FROM countries
            ORDER BY country_name;
            """
        )

        rows = cursor.fetchall()


    countries = {}


    for row in rows:
        countries[
            row["country_code"]
        ] = {
            "code": row[
                "country_code"
            ],
            "name": row[
                "country_name"
            ],
            "flag_url": row[
                "flag_url"
            ]
        }


    return countries


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    with get_connection() as conn:
        teams = load_teams(
            conn
        )

        competitions = load_competitions(
            conn
        )

        countries = load_countries(
            conn
        )


    data = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "sports": {
            "football": {
                "teams": teams,
                "competitions": competitions
            }
        },

        "countries": countries
    }


    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


    print(
        f"branding exported: {OUTPUT_FILE}"
    )


    print(
        f"teams: {len(teams)}"
    )


    print(
        f"competitions: {len(competitions)}"
    )


    print(
        f"countries: {len(countries)}"
    )


if __name__ == "__main__":
    main()