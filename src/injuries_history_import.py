import argparse
import json
import os
import time
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COVERAGE_FILE = (
    PROJECT_ROOT
    / "data"
    / "audits"
    / "premier_league_coverage.json"
)

BASE_URL = "https://v3.football.api-sports.io"

DEFAULT_LEAGUE_ID = 39
DEFAULT_REQUEST_DELAY = 0.22


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Import historical injuries "
            "from API-Football."
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
        "--from-season",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--to-season",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
    )

    parser.add_argument(
        "--resume",
        action="store_true",
    )

    return parser.parse_args()


def load_environment():
    load_dotenv(
        PROJECT_ROOT / ".env"
    )

    API_key = os.getenv(
        "API_FOOTBALL_KEY"
    )

    if not API_key:
        raise RuntimeError(
            "API_FOOTBALL_KEY is missing."
        )

    return API_key


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


class ApiClient:

    def __init__(
        self,
        API_key,
        request_delay=DEFAULT_REQUEST_DELAY,
    ):
        self.request_delay = request_delay

        self.request_count = 0

        self.last_request_time = 0.0

        self.last_headers = {}

        self.session = requests.Session()

        self.session.headers.update(
            {
                "x-apisports-key": API_key,
            }
        )

    def wait_for_rate_limit(self):
        elapsed = (
            time.monotonic()
            - self.last_request_time
        )

        remaining = (
            self.request_delay
            - elapsed
        )

        if remaining > 0:
            time.sleep(
                remaining
            )

    def get(
        self,
        endpoint,
        params=None,
        max_attempts=5,
    ):
        url = (
            f"{BASE_URL}{endpoint}"
        )

        for attempt in range(
            1,
            max_attempts + 1,
        ):
            self.wait_for_rate_limit()

            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=60,
                )

                self.last_request_time = (
                    time.monotonic()
                )

                self.request_count += 1

                self.last_headers = dict(
                    response.headers
                )

                if response.status_code == 429:
                    retry_after = (
                        response.headers.get(
                            "Retry-After"
                        )
                    )

                    wait_seconds = (
                        float(retry_after)
                        if retry_after
                        else min(
                            60,
                            5 * attempt,
                        )
                    )

                    print(
                        "rate limit reached, "
                        f"waiting {wait_seconds}s"
                    )

                    time.sleep(
                        wait_seconds
                    )

                    continue

                if (
                    500
                    <= response.status_code
                    < 600
                ):
                    wait_seconds = min(
                        30,
                        2 ** attempt,
                    )

                    print(
                        "api server error "
                        f"{response.status_code}"
                    )

                    time.sleep(
                        wait_seconds
                    )

                    continue

                response.raise_for_status()

            except requests.RequestException as error:
                if attempt >= max_attempts:
                    raise

                wait_seconds = min(
                    30,
                    2 ** attempt,
                )

                print(
                    f"request failed: {error}"
                )

                time.sleep(
                    wait_seconds
                )

                continue

            data = response.json()

            errors = data.get(
                "errors"
            )

            if errors:
                # invalid api parameters should not be retried
                raise RuntimeError(
                    "API-Football error: "
                    f"{errors}"
                )

            return data

        raise RuntimeError(
            "request failed after retries"
        )

    def quota_remaining(self):
        return {
            "daily": (
                self.last_headers.get(
                    "x-ratelimit-requests-remaining"
                )
            ),

            "minute": (
                self.last_headers.get(
                    "X-RateLimit-Remaining"
                )
                or self.last_headers.get(
                    "x-ratelimit-remaining"
                )
            ),
        }


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
    args,
):
    seasons = list(
        audit.get(
            "seasons",
            [],
        )
    )

    # only seasons where injuries are supported
    seasons = [
        item
        for item
        in seasons
        if (
            item.get(
                "coverage",
                {},
            ).get(
                "injuries"
            )
        )
    ]

    if args.season:
        selected = set(
            args.season
        )

        seasons = [
            item
            for item
            in seasons
            if item["year"]
            in selected
        ]

    if (
        args.from_season
        is not None
    ):
        seasons = [
            item
            for item
            in seasons
            if item["year"]
            >= args.from_season
        ]

    if (
        args.to_season
        is not None
    ):
        seasons = [
            item
            for item
            in seasons
            if item["year"]
            <= args.to_season
        ]

    seasons.sort(
        key=lambda item: (
            item["year"]
        )
    )

    return seasons


def season_label(year):
    return (
        f"{year}/"
        f"{str(year + 1)[-2:]}"
    )


def create_import_run(
    conn,
    league_id,
    season,
):
    row = conn.execute(
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
            'injuries_history',
            %s,
            %s,
            NOW(),
            'running',
            0,
            0,
            0
        )
        RETURNING import_run_id
        """,
        (
            league_id,
            season,
        ),
    ).fetchone()

    return row[
        "import_run_id"
    ]


def finish_import_run(
    conn,
    import_run_id,
    status,
    rows_received,
    rows_inserted,
    api_requests,
    error_message=None,
):
    conn.execute(
        """
        UPDATE import_runs
        SET
            finished_at = NOW(),
            status = %s,
            rows_received = %s,
            rows_inserted = %s,
            api_requests = %s,
            error_message = %s
        WHERE import_run_id = %s
        """,
        (
            status,
            rows_received,
            rows_inserted,
            api_requests,
            error_message,
            import_run_id,
        ),
    )


def season_already_imported(
    conn,
    league_id,
    season,
):
    row = conn.execute(
        """
        SELECT 1
        FROM import_runs
        WHERE
            import_type = 'injuries_history'
            AND league_id = %s
            AND season = %s
            AND status IN (
                'success',
                'completed'
            )
        LIMIT 1
        """,
        (
            league_id,
            season,
        ),
    ).fetchone()

    return row is not None


def save_raw_data(
    conn,
    league_id,
    season,
    payload,
):
    conn.execute(
        """
        INSERT INTO season_raw_data (
            league_id,
            season,
            data_type,
            data_key,
            source,
            payload,
            imported_at
        )
        VALUES (
            %s,
            %s,
            'injuries',
            'all',
            'api-football',
            %s,
            NOW()
        )
        ON CONFLICT (
            league_id,
            season,
            data_type,
            data_key,
            source
        )
        DO UPDATE SET
            payload = EXCLUDED.payload,
            imported_at = NOW()
        """,
        (
            league_id,
            season,
            Jsonb(
                payload
            ),
        ),
    )


def upsert_team(
    conn,
    team,
):
    team_id = team.get(
        "id"
    )

    if not team_id:
        return

    conn.execute(
        """
        INSERT INTO teams (
            team_id,
            team_name,
            team_code,
            country_name,
            logo_url
        )
        VALUES (
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
            team_name = COALESCE(
                EXCLUDED.team_name,
                teams.team_name
            ),
            team_code = COALESCE(
                EXCLUDED.team_code,
                teams.team_code
            ),
            country_name = COALESCE(
                EXCLUDED.country_name,
                teams.country_name
            ),
            logo_url = COALESCE(
                EXCLUDED.logo_url,
                teams.logo_url
            )
        """,
        (
            team_id,
            team.get(
                "name"
            ),
            team.get(
                "code"
            ),
            team.get(
                "country"
            ),
            team.get(
                "logo"
            ),
        ),
    )


def upsert_player(
    conn,
    player,
):
    player_id = player.get(
        "id"
    )

    if not player_id:
        return

    player_name = player.get(
        "name"
    )

    photo_url = player.get(
        "photo"
    )

    # some injury records contain a player id
    # but do not contain a player name
    if not player_name:
        conn.execute(
            """
            UPDATE players
            SET
                photo_url = COALESCE(
                    %s,
                    photo_url
                ),
                updated_at = NOW()
            WHERE player_id = %s
            """,
            (
                photo_url,
                player_id,
            ),
        )

        return

    conn.execute(
        """
        INSERT INTO players (
            player_id,
            player_name,
            photo_url,
            created_at,
            updated_at
        )
        VALUES (
            %s,
            %s,
            %s,
            NOW(),
            NOW()
        )
        ON CONFLICT (
            player_id
        )
        DO UPDATE SET
            player_name = COALESCE(
                EXCLUDED.player_name,
                players.player_name
            ),
            photo_url = COALESCE(
                EXCLUDED.photo_url,
                players.photo_url
            ),
            updated_at = NOW()
        """,
        (
            player_id,
            player_name,
            photo_url,
        ),
    )


def import_season_injuries(
    conn,
    client,
    league_id,
    season,
):
    data = client.get(
        "/injuries",
        params={
            "league": league_id,
            "season": season,
        },
    )

    response = (
        data.get(
            "response"
        )
        or []
    )

    save_raw_data(
        conn,
        league_id,
        season,
        data,
    )

    conn.execute(
        """
        DELETE FROM season_injuries
        WHERE
            league_id = %s
            AND season = %s
        """,
        (
            league_id,
            season,
        ),
    )

    inserted = 0

    missing_player_names = 0

    for item in response:
        player = (
            item.get(
                "player"
            )
            or {}
        )

        team = (
            item.get(
                "team"
            )
            or {}
        )

        fixture = (
            item.get(
                "fixture"
            )
            or {}
        )

        upsert_team(
            conn,
            team,
        )

        if (
            player.get(
                "id"
            )
            and not player.get(
                "name"
            )
        ):
            missing_player_names += 1

        upsert_player(
            conn,
            player,
        )

        injury_type = (
            player.get(
                "type"
            )
            or item.get(
                "type"
            )
        )

        reason = (
            player.get(
                "reason"
            )
            or item.get(
                "reason"
            )
        )

        cursor = conn.execute(
            """
            INSERT INTO season_injuries (
                league_id,
                season,
                fixture_id,
                team_id,
                player_id,
                player_name,
                injury_type,
                reason,
                fixture_date,
                raw_payload,
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
                %s,
                %s,
                NOW()
            )
            ON CONFLICT DO NOTHING
            """,
            (
                league_id,
                season,
                fixture.get(
                    "id"
                ),
                team.get(
                    "id"
                ),
                player.get(
                    "id"
                ),
                player.get(
                    "name"
                ),
                injury_type,
                reason,
                fixture.get(
                    "date"
                ),
                Jsonb(
                    item
                ),
            ),
        )

        if cursor.rowcount > 0:
            inserted += 1

    return (
        len(
            response
        ),
        inserted,
        missing_player_names,
    )


def import_season(
    conn,
    client,
    league_id,
    season,
    resume,
):
    label = season_label(
        season
    )

    if (
        resume
        and season_already_imported(
            conn,
            league_id,
            season,
        )
    ):
        print(
            f"{label}: already imported, "
            "skipping"
        )

        return

    print()

    print(
        f"Importing injuries {label}"
    )

    request_start = (
        client.request_count
    )

    with conn.transaction():
        import_run_id = (
            create_import_run(
                conn,
                league_id,
                season,
            )
        )

    rows_received = 0
    rows_inserted = 0

    try:
        with conn.transaction():
            (
                rows_received,
                rows_inserted,
                missing_player_names,
            ) = import_season_injuries(
                conn,
                client,
                league_id,
                season,
            )

        api_requests = (
            client.request_count
            - request_start
        )

        with conn.transaction():
            finish_import_run(
                conn,
                import_run_id,
                "success",
                rows_received,
                rows_inserted,
                api_requests,
            )

        quota = (
            client.quota_remaining()
        )

        print(
            f"  injury rows: "
            f"{rows_received}"
        )

        print(
            f"  stored rows: "
            f"{rows_inserted}"
        )

        print(
            "  injury rows with player id "
            "but missing player name: "
            f"{missing_player_names}"
        )

        print(
            f"  api requests: "
            f"{api_requests}"
        )

        print(
            "  daily remaining: "
            f"{quota['daily']}"
        )

    except Exception as error:
        api_requests = (
            client.request_count
            - request_start
        )

        with conn.transaction():
            finish_import_run(
                conn,
                import_run_id,
                "failed",
                rows_received,
                rows_inserted,
                api_requests,
                str(
                    error
                )[:2000],
            )

        raise


def main():
    args = parse_args()

    API_key = load_environment()

    audit = load_coverage()

    seasons = choose_seasons(
        audit,
        args,
    )

    if not seasons:
        raise RuntimeError(
            "No injury-covered seasons selected."
        )

    print(
        "Premier League injury "
        "history importer"
    )

    print(
        "Selected seasons:"
    )

    for item in seasons:
        print(
            f"  {item['label']}"
        )

    print()

    client = ApiClient(
        API_key,
        request_delay=(
            args.request_delay
        ),
    )

    with get_connection() as conn:
        for item in seasons:
            import_season(
                conn,
                client,
                args.league_id,
                item[
                    "year"
                ],
                args.resume,
            )

    print()

    print(
        "Injury history import completed."
    )

    print(
        "Total API requests: "
        f"{client.request_count}"
    )

    quota = (
        client.quota_remaining()
    )

    print(
        "Daily remaining: "
        f"{quota['daily']}"
    )


if __name__ == "__main__":
    main()