import argparse
import os
import time
from datetime import date
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


PROJECT_ROOT = Path(__file__).resolve().parents[1]

BASE_URL = "https://v3.football.api-sports.io"

DEFAULT_LEAGUE_ID = 39
DEFAULT_REQUEST_DELAY = 0.22
DEFAULT_PROGRESS_EVERY = 25


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Import transfers, sidelined history "
            "and coach history from API-Football."
        )
    )

    parser.add_argument(
        "--league-id",
        type=int,
        default=DEFAULT_LEAGUE_ID,
    )

    parser.add_argument(
        "--data-type",
        choices=[
            "all",
            "transfers",
            "sidelined",
            "coaches",
        ],
        default="all",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Limit the number of players or coaches "
            "for testing."
        ),
    )

    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help=(
            "Stop gracefully after this many "
            "API requests."
        ),
    )

    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
    )

    parser.add_argument(
        "--progress-every",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
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
        max_requests=None,
    ):
        self.request_delay = request_delay
        self.max_requests = max_requests

        self.request_count = 0
        self.last_request_time = 0.0
        self.last_headers = {}

        self.session = requests.Session()

        self.session.headers.update(
            {
                "x-apisports-key": API_key,
            }
        )

    def can_request(self):
        if self.max_requests is None:
            return True

        return (
            self.request_count
            < self.max_requests
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
        if not self.can_request():
            raise RequestBudgetReached()

        url = (
            f"{BASE_URL}{endpoint}"
        )

        for attempt in range(
            1,
            max_attempts + 1,
        ):
            if not self.can_request():
                raise RequestBudgetReached()

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
                        float(
                            retry_after
                        )
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
                        f"{response.status_code}, "
                        f"retrying in "
                        f"{wait_seconds}s"
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
                    "request failed: "
                    f"{error}"
                )

                print(
                    "retrying in "
                    f"{wait_seconds}s"
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


class RequestBudgetReached(Exception):
    pass


def parse_date(value):
    if not value:
        return None

    value = str(
        value
    ).strip()

    if value.lower() in {
        "unknown",
        "n/a",
        "none",
        "-",
    }:
        return None

    try:
        return date.fromisoformat(
            value[:10]
        )

    except ValueError:
        return None


def import_successful(
    conn,
    entity_type,
    entity_id,
    data_type,
):
    row = conn.execute(
        """
        SELECT 1

        FROM entity_import_status

        WHERE
            entity_type = %s
            AND entity_id = %s
            AND data_type = %s
            AND source = 'api-football'
            AND status = 'success'

        LIMIT 1
        """,
        (
            entity_type,
            entity_id,
            data_type,
        ),
    ).fetchone()

    return row is not None


def save_import_status(
    conn,
    entity_type,
    entity_id,
    data_type,
    status,
    rows_received,
    raw_payload=None,
    error_message=None,
):
    conn.execute(
        """
        INSERT INTO entity_import_status (
            entity_type,
            entity_id,
            data_type,
            source,
            status,
            rows_received,
            raw_payload,
            error_message,
            imported_at
        )
        VALUES (
            %s,
            %s,
            %s,
            'api-football',
            %s,
            %s,
            %s,
            %s,
            NOW()
        )

        ON CONFLICT (
            entity_type,
            entity_id,
            data_type,
            source
        )

        DO UPDATE SET
            status = EXCLUDED.status,
            rows_received = EXCLUDED.rows_received,
            raw_payload = EXCLUDED.raw_payload,
            error_message = EXCLUDED.error_message,
            imported_at = NOW()
        """,
        (
            entity_type,
            entity_id,
            data_type,
            status,
            rows_received,
            (
                Jsonb(
                    raw_payload
                )
                if raw_payload
                is not None
                else None
            ),
            error_message,
        ),
    )


def upsert_team(
    conn,
    team,
):
    if not team:
        return

    team_id = team.get(
        "id"
    )

    if not team_id:
        return

    team_name = team.get(
        "name"
    )

    logo_url = team.get(
        "logo"
    )

    existing = conn.execute(
        """
        SELECT team_id
        FROM teams
        WHERE team_id = %s
        """,
        (
            team_id,
        ),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE teams
            SET
                team_name = COALESCE(
                    %s,
                    team_name
                ),
                logo_url = COALESCE(
                    %s,
                    logo_url
                )
            WHERE team_id = %s
            """,
            (
                team_name,
                logo_url,
                team_id,
            ),
        )

        return

    if not team_name:
        return

    conn.execute(
        """
        INSERT INTO teams (
            team_id,
            team_name,
            logo_url
        )
        VALUES (
            %s,
            %s,
            %s
        )
        """,
        (
            team_id,
            team_name,
            logo_url,
        ),
    )


def get_player_ids(
    conn,
    league_id,
):
    rows = conn.execute(
        """
        SELECT DISTINCT player_id

        FROM (
            SELECT
                fps.player_id

            FROM fixture_player_statistics fps

            JOIN fixtures f
                ON f.fixture_id = fps.fixture_id

            WHERE
                f.league_id = %s
                AND fps.player_id IS NOT NULL

            UNION

            SELECT
                pss.player_id

            FROM player_season_statistics pss

            WHERE
                pss.league_id = %s
                AND pss.player_id IS NOT NULL
        ) players

        ORDER BY player_id
        """,
        (
            league_id,
            league_id,
        ),
    ).fetchall()

    return [
        row[
            "player_id"
        ]
        for row in rows
    ]


def get_coach_ids(
    conn,
    league_id,
):
    rows = conn.execute(
        """
        SELECT DISTINCT
            fl.coach_id

        FROM fixture_lineups fl

        JOIN fixtures f
            ON f.fixture_id = fl.fixture_id

        WHERE
            f.league_id = %s
            AND fl.coach_id IS NOT NULL

        ORDER BY fl.coach_id
        """,
        (
            league_id,
        ),
    ).fetchall()

    return [
        row[
            "coach_id"
        ]
        for row in rows
    ]


def import_player_transfers(
    conn,
    client,
    player_id,
):
    data = client.get(
        "/transfers",
        params={
            "player": player_id,
        },
    )

    response = (
        data.get(
            "response"
        )
        or []
    )

    rows_received = 0

    with conn.transaction():
        conn.execute(
            """
            DELETE FROM player_transfers
            WHERE player_id = %s
            """,
            (
                player_id,
            ),
        )

        for player_block in response:
            player = (
                player_block.get(
                    "player"
                )
                or {}
            )

            response_player_id = (
                player.get(
                    "id"
                )
                or player_id
            )

            player_name = (
                player.get(
                    "name"
                )
            )

            transfers = (
                player_block.get(
                    "transfers"
                )
                or []
            )

            for transfer in transfers:
                teams = (
                    transfer.get(
                        "teams"
                    )
                    or {}
                )

                team_out = (
                    teams.get(
                        "out"
                    )
                    or {}
                )

                team_in = (
                    teams.get(
                        "in"
                    )
                    or {}
                )

                upsert_team(
                    conn,
                    team_out,
                )

                upsert_team(
                    conn,
                    team_in,
                )

                transfer_date_raw = (
                    transfer.get(
                        "date"
                    )
                )

                conn.execute(
                    """
                    INSERT INTO player_transfers (
                        player_id,
                        player_name,
                        transfer_date,
                        transfer_date_raw,
                        transfer_type,
                        team_out_id,
                        team_out_name,
                        team_in_id,
                        team_in_name,
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
                        response_player_id,
                        player_name,
                        parse_date(
                            transfer_date_raw
                        ),
                        (
                            str(
                                transfer_date_raw
                            )
                            if transfer_date_raw
                            is not None
                            else None
                        ),
                        transfer.get(
                            "type"
                        ),
                        team_out.get(
                            "id"
                        ),
                        team_out.get(
                            "name"
                        ),
                        team_in.get(
                            "id"
                        ),
                        team_in.get(
                            "name"
                        ),
                        Jsonb(
                            transfer
                        ),
                    ),
                )

                rows_received += 1

        save_import_status(
            conn,
            "player",
            player_id,
            "transfers",
            "success",
            rows_received,
            data,
        )

    return rows_received


def import_player_sidelined(
    conn,
    client,
    player_id,
):
    data = client.get(
        "/sidelined",
        params={
            "player": player_id,
        },
    )

    response = (
        data.get(
            "response"
        )
        or []
    )

    with conn.transaction():
        conn.execute(
            """
            DELETE FROM player_sidelined
            WHERE player_id = %s
            """,
            (
                player_id,
            ),
        )

        for item in response:
            start_raw = (
                item.get(
                    "start"
                )
            )

            end_raw = (
                item.get(
                    "end"
                )
            )

            conn.execute(
                """
                INSERT INTO player_sidelined (
                    player_id,
                    sidelined_type,
                    start_date,
                    end_date,
                    start_date_raw,
                    end_date_raw,
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
                    NOW()
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    player_id,
                    item.get(
                        "type"
                    ),
                    parse_date(
                        start_raw
                    ),
                    parse_date(
                        end_raw
                    ),
                    (
                        str(
                            start_raw
                        )
                        if start_raw
                        is not None
                        else None
                    ),
                    (
                        str(
                            end_raw
                        )
                        if end_raw
                        is not None
                        else None
                    ),
                    Jsonb(
                        item
                    ),
                ),
            )

        save_import_status(
            conn,
            "player",
            player_id,
            "sidelined",
            "success",
            len(
                response
            ),
            data,
        )

    return len(
        response
    )


def upsert_coach(
    conn,
    coach,
):
    coach_id = coach.get(
        "id"
    )

    if not coach_id:
        return False

    birth = (
        coach.get(
            "birth"
        )
        or {}
    )

    current_team = (
        coach.get(
            "team"
        )
        or {}
    )

    upsert_team(
        conn,
        current_team,
    )

    conn.execute(
        """
        INSERT INTO coaches (
            coach_id,
            coach_name,
            first_name,
            last_name,
            age,
            birth_date,
            birth_place,
            birth_country,
            nationality,
            height,
            weight,
            photo_url,
            current_team_id,
            current_team_name,
            raw_payload,
            created_at,
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
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            NOW(),
            NOW()
        )

        ON CONFLICT (
            coach_id
        )

        DO UPDATE SET
            coach_name = COALESCE(
                EXCLUDED.coach_name,
                coaches.coach_name
            ),
            first_name = COALESCE(
                EXCLUDED.first_name,
                coaches.first_name
            ),
            last_name = COALESCE(
                EXCLUDED.last_name,
                coaches.last_name
            ),
            age = COALESCE(
                EXCLUDED.age,
                coaches.age
            ),
            birth_date = COALESCE(
                EXCLUDED.birth_date,
                coaches.birth_date
            ),
            birth_place = COALESCE(
                EXCLUDED.birth_place,
                coaches.birth_place
            ),
            birth_country = COALESCE(
                EXCLUDED.birth_country,
                coaches.birth_country
            ),
            nationality = COALESCE(
                EXCLUDED.nationality,
                coaches.nationality
            ),
            height = COALESCE(
                EXCLUDED.height,
                coaches.height
            ),
            weight = COALESCE(
                EXCLUDED.weight,
                coaches.weight
            ),
            photo_url = COALESCE(
                EXCLUDED.photo_url,
                coaches.photo_url
            ),
            current_team_id = EXCLUDED.current_team_id,
            current_team_name = EXCLUDED.current_team_name,
            raw_payload = EXCLUDED.raw_payload,
            updated_at = NOW()
        """,
        (
            coach_id,
            coach.get(
                "name"
            ),
            coach.get(
                "firstname"
            ),
            coach.get(
                "lastname"
            ),
            coach.get(
                "age"
            ),
            parse_date(
                birth.get(
                    "date"
                )
            ),
            birth.get(
                "place"
            ),
            birth.get(
                "country"
            ),
            coach.get(
                "nationality"
            ),
            coach.get(
                "height"
            ),
            coach.get(
                "weight"
            ),
            coach.get(
                "photo"
            ),
            current_team.get(
                "id"
            ),
            current_team.get(
                "name"
            ),
            Jsonb(
                coach
            ),
        ),
    )

    return True


def import_coach(
    conn,
    client,
    coach_id,
    data=None,
):
    if data is None:
        data = client.get("/coachs", params={"id": coach_id})

    response = (
        data.get(
            "response"
        )
        or []
    )

    career_rows = 0

    if not response or any(coach.get("id") != coach_id for coach in response):
        raise ValueError(f"Missing or mismatched coach profile: {coach_id}")

    with conn.transaction():
        conn.execute(
            """
            DELETE FROM coach_careers
            WHERE coach_id = %s
            """,
            (
                coach_id,
            ),
        )

        for coach in response:
            actual_coach_id = (
                coach.get(
                    "id"
                )
                or coach_id
            )

            if not upsert_coach(
                conn,
                coach,
            ):
                continue

            career = (
                coach.get(
                    "career"
                )
                or []
            )

            for item in career:
                team = (
                    item.get(
                        "team"
                    )
                    or {}
                )

                upsert_team(
                    conn,
                    team,
                )

                start_raw = (
                    item.get(
                        "start"
                    )
                )

                end_raw = (
                    item.get(
                        "end"
                    )
                )

                conn.execute(
                    """
                    INSERT INTO coach_careers (
                        coach_id,
                        team_id,
                        team_name,
                        start_date,
                        end_date,
                        start_date_raw,
                        end_date_raw,
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
                        NOW()
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        actual_coach_id,
                        team.get(
                            "id"
                        ),
                        team.get(
                            "name"
                        ),
                        parse_date(
                            start_raw
                        ),
                        parse_date(
                            end_raw
                        ),
                        (
                            str(
                                start_raw
                            )
                            if start_raw
                            is not None
                            else None
                        ),
                        (
                            str(
                                end_raw
                            )
                            if end_raw
                            is not None
                            else None
                        ),
                        Jsonb(
                            item
                        ),
                    ),
                )

                career_rows += 1

        save_import_status(
            conn,
            "coach",
            coach_id,
            "profile",
            "success",
            career_rows,
            data,
        )

    return career_rows


def save_failure(
    conn,
    entity_type,
    entity_id,
    data_type,
    error,
):
    with conn.transaction():
        save_import_status(
            conn,
            entity_type,
            entity_id,
            data_type,
            "failed",
            0,
            None,
            str(
                error
            )[:2000],
        )


def print_progress(
    current,
    total,
    label,
    rows,
    progress_every,
):
    if (
        current == 1
        or current == total
        or current % progress_every == 0
    ):
        print(
            f"  {label}: "
            f"{current}/{total} "
            f"| rows={rows}"
        )


def import_transfers(
    conn,
    client,
    player_ids,
    resume,
    progress_every,
):
    print()

    print(
        "Importing player transfers"
    )

    total_rows = 0
    total = len(
        player_ids
    )

    for index, player_id in enumerate(
        player_ids,
        start=1,
    ):
        if (
            resume
            and import_successful(
                conn,
                "player",
                player_id,
                "transfers",
            )
        ):
            print_progress(
                index,
                total,
                "transfers",
                total_rows,
                progress_every,
            )

            continue

        try:
            rows = import_player_transfers(
                conn,
                client,
                player_id,
            )

            total_rows += rows

        except RequestBudgetReached:
            print()

            print(
                "request budget reached"
            )

            return False

        except Exception as error:
            save_failure(
                conn,
                "player",
                player_id,
                "transfers",
                error,
            )

            print(
                "  transfer error "
                f"player_id={player_id}: "
                f"{error}"
            )

        print_progress(
            index,
            total,
            "transfers",
            total_rows,
            progress_every,
        )

    print(
        "Transfers complete. "
        f"Rows: {total_rows}"
    )

    return True


def import_sidelined(
    conn,
    client,
    player_ids,
    resume,
    progress_every,
):
    print()

    print(
        "Importing player sidelined history"
    )

    total_rows = 0
    total = len(
        player_ids
    )

    for index, player_id in enumerate(
        player_ids,
        start=1,
    ):
        if (
            resume
            and import_successful(
                conn,
                "player",
                player_id,
                "sidelined",
            )
        ):
            print_progress(
                index,
                total,
                "sidelined",
                total_rows,
                progress_every,
            )

            continue

        try:
            rows = import_player_sidelined(
                conn,
                client,
                player_id,
            )

            total_rows += rows

        except RequestBudgetReached:
            print()

            print(
                "request budget reached"
            )

            return False

        except Exception as error:
            save_failure(
                conn,
                "player",
                player_id,
                "sidelined",
                error,
            )

            print(
                "  sidelined error "
                f"player_id={player_id}: "
                f"{error}"
            )

        print_progress(
            index,
            total,
            "sidelined",
            total_rows,
            progress_every,
        )

    print(
        "Sidelined complete. "
        f"Rows: {total_rows}"
    )

    return True


def import_coaches(
    conn,
    client,
    coach_ids,
    resume,
    progress_every,
):
    print()

    print(
        "Importing coaches"
    )

    total_rows = 0
    total = len(
        coach_ids
    )

    for index, coach_id in enumerate(
        coach_ids,
        start=1,
    ):
        if (
            resume
            and import_successful(
                conn,
                "coach",
                coach_id,
                "profile",
            )
        ):
            print_progress(
                index,
                total,
                "coaches",
                total_rows,
                progress_every,
            )

            continue

        try:
            rows = import_coach(
                conn,
                client,
                coach_id,
            )

            total_rows += rows

        except RequestBudgetReached:
            print()

            print(
                "request budget reached"
            )

            return False

        except Exception as error:
            save_failure(
                conn,
                "coach",
                coach_id,
                "profile",
                error,
            )

            print(
                "  coach error "
                f"coach_id={coach_id}: "
                f"{error}"
            )

        print_progress(
            index,
            total,
            "coaches",
            total_rows,
            progress_every,
        )

    print(
        "Coaches complete. "
        f"Career rows: {total_rows}"
    )

    return True


def main():
    args = parse_args()

    API_key = load_environment()

    client = ApiClient(
        API_key,
        request_delay=(
            args.request_delay
        ),
        max_requests=(
            args.max_requests
        ),
    )

    with get_connection() as conn:
        player_ids = get_player_ids(
            conn,
            args.league_id,
        )

        coach_ids = get_coach_ids(
            conn,
            args.league_id,
        )

        if args.limit is not None:
            player_ids = player_ids[
                :args.limit
            ]

            coach_ids = coach_ids[
                :args.limit
            ]

        print(
            "Premier League entity "
            "history importer"
        )

        print()

        print(
            "Players found: "
            f"{len(player_ids)}"
        )

        print(
            "Historical coaches found: "
            f"{len(coach_ids)}"
        )

        if (
            args.data_type
            in {
                "all",
                "transfers",
            }
        ):
            completed = import_transfers(
                conn,
                client,
                player_ids,
                args.resume,
                args.progress_every,
            )

            if not completed:
                print_summary(
                    client
                )

                return

        if (
            args.data_type
            in {
                "all",
                "sidelined",
            }
        ):
            completed = import_sidelined(
                conn,
                client,
                player_ids,
                args.resume,
                args.progress_every,
            )

            if not completed:
                print_summary(
                    client
                )

                return

        if (
            args.data_type
            in {
                "all",
                "coaches",
            }
        ):
            completed = import_coaches(
                conn,
                client,
                coach_ids,
                args.resume,
                args.progress_every,
            )

            if not completed:
                print_summary(
                    client
                )

                return

    print()

    print(
        "Entity history import completed."
    )

    print_summary(
        client
    )


def print_summary(
    client,
):
    quota = (
        client.quota_remaining()
    )

    print()

    print(
        "API requests used: "
        f"{client.request_count}"
    )

    print(
        "Daily remaining: "
        f"{quota['daily']}"
    )

    print(
        "Minute remaining: "
        f"{quota['minute']}"
    )


if __name__ == "__main__":
    main()
