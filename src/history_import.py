import argparse
import json
import os
import time
from datetime import datetime
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
DEFAULT_BATCH_SIZE = 20
DEFAULT_REQUEST_DELAY = 0.22

COMPLETED_STATUSES = {
    "FT",
    "AET",
    "PEN",
}

NO_DETAIL_STATUSES = {
    "NS",
    "TBD",
    "PST",
    "CANC",
    "ABD",
    "AWD",
    "WO",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Import historical Premier League "
            "match data from API-Football."
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
        help=(
            "Import only this season. "
            "Can be used multiple times."
        ),
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
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )

    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip fixture detail that already "
            "exists in fixture_raw_data."
        ),
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
        self.API_key = API_key

        self.request_delay = (
            request_delay
        )

        self.request_count = 0

        self.last_request_time = 0.0

        self.last_headers = {}

        self.session = (
            requests.Session()
        )

        self.session.headers.update(
            {
                "x-apisports-key": (
                    API_key
                )
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
                response = (
                    self.session.get(
                        url,
                        params=params,
                        timeout=60,
                    )
                )

                self.last_request_time = (
                    time.monotonic()
                )

                self.request_count += 1

                self.last_headers = (
                    dict(
                        response.headers
                    )
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

            except (
                requests.RequestException,
                RuntimeError,
            ) as error:

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

        raise RuntimeError(
            "request failed after retries"
        )

    def quota_remaining(self):
        daily = (
            self.last_headers.get(
                "x-ratelimit-requests-remaining"
            )
        )

        minute = (
            self.last_headers.get(
                "X-RateLimit-Remaining"
            )
            or self.last_headers.get(
                "x-ratelimit-remaining"
            )
        )

        return {
            "daily": daily,
            "minute": minute,
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
    seasons = audit.get(
        "seasons",
        [],
    )

    if args.season:
        selected = set(
            args.season
        )

        seasons = [
            season
            for season in seasons
            if season["year"]
            in selected
        ]

    if (
        args.from_season
        is not None
    ):
        seasons = [
            season
            for season in seasons
            if season["year"]
            >= args.from_season
        ]

    if (
        args.to_season
        is not None
    ):
        seasons = [
            season
            for season in seasons
            if season["year"]
            <= args.to_season
        ]

    seasons.sort(
        key=lambda item: (
            item["year"]
        )
    )

    return seasons


def chunks(
    values,
    size,
):
    for index in range(
        0,
        len(values),
        size,
    ):
        yield values[
            index:index + size
        ]


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None


def parse_number(value):
    if value is None:
        return None

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        cleaned = (
            value
            .replace(
                "%",
                "",
            )
            .strip()
        )

        if not cleaned:
            return None

        try:
            return float(
                cleaned
            )

        except ValueError:
            return None

    return None


def parse_integer(value):
    number = parse_number(
        value
    )

    if number is None:
        return None

    return int(
        number
    )


def parse_float(value):
    number = parse_number(
        value
    )

    if number is None:
        return None

    return float(
        number
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
            'history_match_bulk',
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


def ensure_league_and_season(
    conn,
    audit,
    league_id,
    season,
):
    league = audit.get(
        "league",
        {},
    )

    country = audit.get(
        "country",
        {},
    )

    conn.execute(
        """
        INSERT INTO leagues (
            league_id,
            league_name,
            country_name,
            logo_url,
            country_code,
            country_flag_url
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
            league_id
        )
        DO UPDATE SET
            league_name = EXCLUDED.league_name,
            country_name = EXCLUDED.country_name,
            logo_url = COALESCE(
                EXCLUDED.logo_url,
                leagues.logo_url
            ),
            country_code = COALESCE(
                EXCLUDED.country_code,
                leagues.country_code
            ),
            country_flag_url = COALESCE(
                EXCLUDED.country_flag_url,
                leagues.country_flag_url
            )
        """,
        (
            league_id,
            league.get(
                "name",
                "Premier League",
            ),
            country.get(
                "name",
            ),
            league.get(
                "logo",
            ),
            country.get(
                "code",
            ),
            country.get(
                "flag",
            ),
        ),
    )

    conn.execute(
        """
        INSERT INTO seasons (
            league_id,
            season
        )
        VALUES (
            %s,
            %s
        )
        ON CONFLICT (
            league_id,
            season
        )
        DO NOTHING
        """,
        (
            league_id,
            season,
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


def upsert_venue(
    conn,
    venue,
    country_name=None,
):
    if not venue:
        return

    venue_id = venue.get(
        "id"
    )

    if not venue_id:
        return

    conn.execute(
        """
        INSERT INTO venues (
            venue_id,
            venue_name,
            address,
            city,
            country_name,
            capacity,
            surface,
            image_url,
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
            NOW()
        )
        ON CONFLICT (
            venue_id
        )
        DO UPDATE SET
            venue_name = COALESCE(
                EXCLUDED.venue_name,
                venues.venue_name
            ),
            address = COALESCE(
                EXCLUDED.address,
                venues.address
            ),
            city = COALESCE(
                EXCLUDED.city,
                venues.city
            ),
            country_name = COALESCE(
                EXCLUDED.country_name,
                venues.country_name
            ),
            capacity = COALESCE(
                EXCLUDED.capacity,
                venues.capacity
            ),
            surface = COALESCE(
                EXCLUDED.surface,
                venues.surface
            ),
            image_url = COALESCE(
                EXCLUDED.image_url,
                venues.image_url
            ),
            updated_at = NOW()
        """,
        (
            venue_id,
            venue.get(
                "name"
            ),
            venue.get(
                "address"
            ),
            venue.get(
                "city"
            ),
            country_name,
            venue.get(
                "capacity"
            ),
            venue.get(
                "surface"
            ),
            venue.get(
                "image"
            ),
        ),
    )


def import_teams_and_venues(
    conn,
    client,
    league_id,
    season,
):
    data = client.get(
        "/teams",
        params={
            "league": league_id,
            "season": season,
        },
    )

    rows = data.get(
        "response",
        [],
    )

    for row in rows:
        team = row.get(
            "team",
            {},
        )

        venue = row.get(
            "venue",
            {},
        )

        upsert_team(
            conn,
            team,
        )

        upsert_venue(
            conn,
            venue,
            country_name=team.get(
                "country"
            ),
        )

    return len(
        rows
    )


def save_raw_data(
    conn,
    fixture_id,
    data_type,
    payload,
):
    conn.execute(
        """
        INSERT INTO fixture_raw_data (
            fixture_id,
            data_type,
            source,
            payload,
            imported_at
        )
        VALUES (
            %s,
            %s,
            'api-football',
            %s,
            NOW()
        )
        ON CONFLICT (
            fixture_id,
            data_type,
            source
        )
        DO UPDATE SET
            payload = EXCLUDED.payload,
            imported_at = NOW()
        """,
        (
            fixture_id,
            data_type,
            Jsonb(
                payload
            ),
        ),
    )


def upsert_fixture(
    conn,
    item,
):
    fixture = item.get(
        "fixture",
        {},
    )

    league = item.get(
        "league",
        {},
    )

    teams = item.get(
        "teams",
        {},
    )

    home_team = teams.get(
        "home",
        {},
    )

    away_team = teams.get(
        "away",
        {},
    )

    goals = item.get(
        "goals",
        {},
    )

    score = item.get(
        "score",
        {},
    )

    status = fixture.get(
        "status",
        {},
    )

    venue = fixture.get(
        "venue",
        {},
    ) or {}

    fixture_id = fixture.get(
        "id"
    )

    if not fixture_id:
        return None

    upsert_team(
        conn,
        home_team,
    )

    upsert_team(
        conn,
        away_team,
    )

    venue_id = venue.get(
        "id"
    )

    # api-football uses 0 for an unknown historical venue
    if not venue_id:
        venue_id = None

    if venue_id is not None:
        upsert_venue(
            conn,
            venue,
            country_name=league.get(
                "country"
            ),
        )

    halftime = score.get(
        "halftime",
        {},
    ) or {}

    fulltime = score.get(
        "fulltime",
        {},
    ) or {}

    extratime = score.get(
        "extratime",
        {},
    ) or {}

    penalty = score.get(
        "penalty",
        {},
    ) or {}

    conn.execute(
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
            away_goals,
            round,
            referee,
            timezone,
            venue_id,
            halftime_home,
            halftime_away,
            fulltime_home,
            fulltime_away,
            extratime_home,
            extratime_away,
            penalty_home,
            penalty_away,
            last_api_sync_at
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
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            NOW()
        )
        ON CONFLICT (
            fixture_id
        )
        DO UPDATE SET
            league_id = EXCLUDED.league_id,
            season = EXCLUDED.season,
            match_date = EXCLUDED.match_date,
            status = EXCLUDED.status,
            home_team_id = EXCLUDED.home_team_id,
            away_team_id = EXCLUDED.away_team_id,
            home_goals = EXCLUDED.home_goals,
            away_goals = EXCLUDED.away_goals,
            round = EXCLUDED.round,
            referee = EXCLUDED.referee,
            timezone = EXCLUDED.timezone,
            venue_id = EXCLUDED.venue_id,
            halftime_home = EXCLUDED.halftime_home,
            halftime_away = EXCLUDED.halftime_away,
            fulltime_home = EXCLUDED.fulltime_home,
            fulltime_away = EXCLUDED.fulltime_away,
            extratime_home = EXCLUDED.extratime_home,
            extratime_away = EXCLUDED.extratime_away,
            penalty_home = EXCLUDED.penalty_home,
            penalty_away = EXCLUDED.penalty_away,
            last_api_sync_at = NOW()
        """,
        (
            fixture_id,
            league.get(
                "id"
            ),
            league.get(
                "season"
            ),
            parse_datetime(
                fixture.get(
                    "date"
                )
            ),
            status.get(
                "short"
            ),
            home_team.get(
                "id"
            ),
            away_team.get(
                "id"
            ),
            goals.get(
                "home"
            ),
            goals.get(
                "away"
            ),
            league.get(
                "round"
            ),
            fixture.get(
                "referee"
            ),
            fixture.get(
                "timezone"
            ),
            venue_id,
            halftime.get(
                "home"
            ),
            halftime.get(
                "away"
            ),
            fulltime.get(
                "home"
            ),
            fulltime.get(
                "away"
            ),
            extratime.get(
                "home"
            ),
            extratime.get(
                "away"
            ),
            penalty.get(
                "home"
            ),
            penalty.get(
                "away"
            ),
        ),
    )

    return fixture_id


def import_fixture_list(
    conn,
    client,
    league_id,
    season,
):
    data = client.get(
        "/fixtures",
        params={
            "league": league_id,
            "season": season,
        },
    )

    response = data.get(
        "response",
        [],
    )

    fixture_ids = []

    fixture_statuses = {}

    for item in response:
        fixture_id = upsert_fixture(
            conn,
            item,
        )

        if not fixture_id:
            continue

        fixture_ids.append(
            fixture_id
        )

        status = (
            item.get(
                "fixture",
                {},
            )
            .get(
                "status",
                {},
            )
            .get(
                "short"
            )
        )

        fixture_statuses[
            fixture_id
        ] = status

        save_raw_data(
            conn,
            fixture_id,
            "fixture_base",
            item,
        )

    return (
        fixture_ids,
        fixture_statuses,
    )


def normalize_stat_name(value):
    if value is None:
        return ""

    return (
        str(
            value
        )
        .strip()
        .lower()
        .replace(
            "-",
            " ",
        )
    )


def parse_team_statistics(
    statistics,
):
    values = {}

    for statistic in statistics:
        name = normalize_stat_name(
            statistic.get(
                "type"
            )
        )

        values[
            name
        ] = statistic.get(
            "value"
        )

    return {
        "shots_on_goal": parse_integer(
            values.get(
                "shots on goal"
            )
        ),

        "shots_off_goal": parse_integer(
            values.get(
                "shots off goal"
            )
        ),

        "total_shots": parse_integer(
            values.get(
                "total shots"
            )
        ),

        "blocked_shots": parse_integer(
            values.get(
                "blocked shots"
            )
        ),

        "shots_inside_box": parse_integer(
            values.get(
                "shots insidebox"
            )
            or values.get(
                "shots inside box"
            )
        ),

        "shots_outside_box": parse_integer(
            values.get(
                "shots outsidebox"
            )
            or values.get(
                "shots outside box"
            )
        ),

        "fouls": parse_integer(
            values.get(
                "fouls"
            )
        ),

        "corner_kicks": parse_integer(
            values.get(
                "corner kicks"
            )
        ),

        "offsides": parse_integer(
            values.get(
                "offsides"
            )
        ),

        "ball_possession": parse_float(
            values.get(
                "ball possession"
            )
        ),

        "yellow_cards": parse_integer(
            values.get(
                "yellow cards"
            )
        ),

        "red_cards": parse_integer(
            values.get(
                "red cards"
            )
        ),

        "goalkeeper_saves": parse_integer(
            values.get(
                "goalkeeper saves"
            )
        ),

        "total_passes": parse_integer(
            values.get(
                "total passes"
            )
        ),

        "passes_accurate": parse_integer(
            values.get(
                "passes accurate"
            )
        ),

        "passes_percentage": parse_float(
            values.get(
                "passes %"
            )
            or values.get(
                "passes percentage"
            )
        ),
    }


def insert_fixture_statistics(
    conn,
    fixture_id,
    statistics_blocks,
):
    for block in statistics_blocks:
        team = block.get(
            "team",
            {},
        )

        team_id = team.get(
            "id"
        )

        if not team_id:
            continue

        upsert_team(
            conn,
            team,
        )

        parsed = parse_team_statistics(
            block.get(
                "statistics",
                [],
            )
        )

        conn.execute(
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
                passes_percentage,
                raw_payload,
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
                %s,
                %s,
                %s,
                %s,
                NOW()
            )
            ON CONFLICT (
                fixture_id,
                team_id
            )
            DO UPDATE SET
                shots_on_goal = EXCLUDED.shots_on_goal,
                shots_off_goal = EXCLUDED.shots_off_goal,
                total_shots = EXCLUDED.total_shots,
                blocked_shots = EXCLUDED.blocked_shots,
                shots_inside_box = EXCLUDED.shots_inside_box,
                shots_outside_box = EXCLUDED.shots_outside_box,
                fouls = EXCLUDED.fouls,
                corner_kicks = EXCLUDED.corner_kicks,
                offsides = EXCLUDED.offsides,
                ball_possession = EXCLUDED.ball_possession,
                yellow_cards = EXCLUDED.yellow_cards,
                red_cards = EXCLUDED.red_cards,
                goalkeeper_saves = EXCLUDED.goalkeeper_saves,
                total_passes = EXCLUDED.total_passes,
                passes_accurate = EXCLUDED.passes_accurate,
                passes_percentage = EXCLUDED.passes_percentage,
                raw_payload = EXCLUDED.raw_payload,
                updated_at = NOW()
            """,
            (
                fixture_id,
                team_id,
                parsed[
                    "shots_on_goal"
                ],
                parsed[
                    "shots_off_goal"
                ],
                parsed[
                    "total_shots"
                ],
                parsed[
                    "blocked_shots"
                ],
                parsed[
                    "shots_inside_box"
                ],
                parsed[
                    "shots_outside_box"
                ],
                parsed[
                    "fouls"
                ],
                parsed[
                    "corner_kicks"
                ],
                parsed[
                    "offsides"
                ],
                parsed[
                    "ball_possession"
                ],
                parsed[
                    "yellow_cards"
                ],
                parsed[
                    "red_cards"
                ],
                parsed[
                    "goalkeeper_saves"
                ],
                parsed[
                    "total_passes"
                ],
                parsed[
                    "passes_accurate"
                ],
                parsed[
                    "passes_percentage"
                ],
                Jsonb(
                    block
                ),
            ),
        )


def insert_events(
    conn,
    fixture_id,
    events,
):
    for index, event in enumerate(
        events
    ):
        time_data = event.get(
            "time",
            {},
        )

        team = event.get(
            "team",
            {},
        )

        player = event.get(
            "player",
            {},
        )

        assist = event.get(
            "assist",
            {},
        )

        team_id = team.get(
            "id"
        )

        if team_id:
            upsert_team(
                conn,
                team,
            )

        conn.execute(
            """
            INSERT INTO fixture_events (
                fixture_id,
                source_order,
                team_id,
                elapsed_minute,
                extra_minute,
                player_id,
                player_name,
                assist_player_id,
                assist_player_name,
                event_type,
                event_detail,
                comments,
                raw_payload
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
                %s
            )
            ON CONFLICT (
                fixture_id,
                source_order
            )
            DO UPDATE SET
                team_id = EXCLUDED.team_id,
                elapsed_minute = EXCLUDED.elapsed_minute,
                extra_minute = EXCLUDED.extra_minute,
                player_id = EXCLUDED.player_id,
                player_name = EXCLUDED.player_name,
                assist_player_id = EXCLUDED.assist_player_id,
                assist_player_name = EXCLUDED.assist_player_name,
                event_type = EXCLUDED.event_type,
                event_detail = EXCLUDED.event_detail,
                comments = EXCLUDED.comments,
                raw_payload = EXCLUDED.raw_payload
            """,
            (
                fixture_id,
                index,
                team_id,
                time_data.get(
                    "elapsed"
                ),
                time_data.get(
                    "extra"
                ),
                player.get(
                    "id"
                ),
                player.get(
                    "name"
                ),
                assist.get(
                    "id"
                ),
                assist.get(
                    "name"
                ),
                event.get(
                    "type"
                ),
                event.get(
                    "detail"
                ),
                event.get(
                    "comments"
                ),
                Jsonb(
                    event
                ),
            ),
        )


def insert_lineup_players(
    conn,
    fixture_id,
    team_id,
    lineup_type,
    players,
):
    for index, entry in enumerate(
        players
    ):
        player = entry.get(
            "player",
            {},
        )

        conn.execute(
            """
            INSERT INTO fixture_lineup_players (
                fixture_id,
                team_id,
                lineup_type,
                source_order,
                player_id,
                player_name,
                shirt_number,
                position,
                grid_position,
                raw_payload
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
                %s
            )
            """,
            (
                fixture_id,
                team_id,
                lineup_type,
                index,
                player.get(
                    "id"
                ),
                player.get(
                    "name"
                ),
                player.get(
                    "number"
                ),
                player.get(
                    "pos"
                ),
                player.get(
                    "grid"
                ),
                Jsonb(
                    entry
                ),
            ),
        )


def insert_lineups(
    conn,
    fixture_id,
    lineups,
):
    for lineup in lineups:
        team = lineup.get(
            "team",
            {},
        )

        coach = lineup.get(
            "coach",
            {},
        )

        team_id = team.get(
            "id"
        )

        if not team_id:
            continue

        upsert_team(
            conn,
            team,
        )

        conn.execute(
            """
            INSERT INTO fixture_lineups (
                fixture_id,
                team_id,
                formation,
                coach_id,
                coach_name,
                raw_payload,
                updated_at
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NOW()
            )
            ON CONFLICT (
                fixture_id,
                team_id
            )
            DO UPDATE SET
                formation = EXCLUDED.formation,
                coach_id = EXCLUDED.coach_id,
                coach_name = EXCLUDED.coach_name,
                raw_payload = EXCLUDED.raw_payload,
                updated_at = NOW()
            """,
            (
                fixture_id,
                team_id,
                lineup.get(
                    "formation"
                ),
                coach.get(
                    "id"
                ),
                coach.get(
                    "name"
                ),
                Jsonb(
                    lineup
                ),
            ),
        )

        insert_lineup_players(
            conn,
            fixture_id,
            team_id,
            "start_xi",
            lineup.get(
                "startXI",
                [],
            ),
        )

        insert_lineup_players(
            conn,
            fixture_id,
            team_id,
            "substitute",
            lineup.get(
                "substitutes",
                [],
            ),
        )


def insert_fixture_players(
    conn,
    fixture_id,
    team_blocks,
):
    for team_block in team_blocks:
        team = team_block.get(
            "team",
            {},
        )

        team_id = team.get(
            "id"
        )

        if not team_id:
            continue

        upsert_team(
            conn,
            team,
        )

        players = team_block.get(
            "players",
            [],
        )

        for player_block in players:
            player = player_block.get(
                "player",
                {},
            )

            player_id = player.get(
                "id"
            )

            if not player_id:
                continue

            statistics_list = (
                player_block.get(
                    "statistics",
                    [],
                )
            )

            if not statistics_list:
                continue

            statistics = (
                statistics_list[0]
            )

            games = statistics.get(
                "games",
                {},
            ) or {}

            shots = statistics.get(
                "shots",
                {},
            ) or {}

            goals = statistics.get(
                "goals",
                {},
            ) or {}

            passes = statistics.get(
                "passes",
                {},
            ) or {}

            tackles = statistics.get(
                "tackles",
                {},
            ) or {}

            duels = statistics.get(
                "duels",
                {},
            ) or {}

            dribbles = statistics.get(
                "dribbles",
                {},
            ) or {}

            fouls = statistics.get(
                "fouls",
                {},
            ) or {}

            cards = statistics.get(
                "cards",
                {},
            ) or {}

            penalty = statistics.get(
                "penalty",
                {},
            ) or {}

            penalties_committed = (
                penalty.get(
                    "committed"
                )
            )

            if penalties_committed is None:
                penalties_committed = (
                    penalty.get(
                        "commited"
                    )
                )

            conn.execute(
                """
                INSERT INTO fixture_player_statistics (
                    fixture_id,
                    team_id,
                    player_id,
                    player_name,
                    minutes,
                    shirt_number,
                    position,
                    rating,
                    captain,
                    substitute,
                    offsides,
                    shots_total,
                    shots_on_goal,
                    goals,
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
                    raw_payload,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, NOW()
                )
                ON CONFLICT (
                    fixture_id,
                    team_id,
                    player_id
                )
                DO UPDATE SET
                    player_name = EXCLUDED.player_name,
                    minutes = EXCLUDED.minutes,
                    shirt_number = EXCLUDED.shirt_number,
                    position = EXCLUDED.position,
                    rating = EXCLUDED.rating,
                    captain = EXCLUDED.captain,
                    substitute = EXCLUDED.substitute,
                    offsides = EXCLUDED.offsides,
                    shots_total = EXCLUDED.shots_total,
                    shots_on_goal = EXCLUDED.shots_on_goal,
                    goals = EXCLUDED.goals,
                    goals_conceded = EXCLUDED.goals_conceded,
                    assists = EXCLUDED.assists,
                    saves = EXCLUDED.saves,
                    passes_total = EXCLUDED.passes_total,
                    key_passes = EXCLUDED.key_passes,
                    pass_accuracy = EXCLUDED.pass_accuracy,
                    tackles_total = EXCLUDED.tackles_total,
                    blocks = EXCLUDED.blocks,
                    interceptions = EXCLUDED.interceptions,
                    duels_total = EXCLUDED.duels_total,
                    duels_won = EXCLUDED.duels_won,
                    dribbles_attempts = EXCLUDED.dribbles_attempts,
                    dribbles_success = EXCLUDED.dribbles_success,
                    dribbled_past = EXCLUDED.dribbled_past,
                    fouls_drawn = EXCLUDED.fouls_drawn,
                    fouls_committed = EXCLUDED.fouls_committed,
                    yellow_cards = EXCLUDED.yellow_cards,
                    yellow_red_cards = EXCLUDED.yellow_red_cards,
                    red_cards = EXCLUDED.red_cards,
                    penalties_won = EXCLUDED.penalties_won,
                    penalties_committed = EXCLUDED.penalties_committed,
                    penalties_scored = EXCLUDED.penalties_scored,
                    penalties_missed = EXCLUDED.penalties_missed,
                    penalties_saved = EXCLUDED.penalties_saved,
                    raw_payload = EXCLUDED.raw_payload,
                    updated_at = NOW()
                """,
                (
                    fixture_id,
                    team_id,
                    player_id,
                    player.get(
                        "name"
                    ),
                    games.get(
                        "minutes"
                    ),
                    games.get(
                        "number"
                    ),
                    games.get(
                        "position"
                    ),
                    parse_float(
                        games.get(
                            "rating"
                        )
                    ),
                    games.get(
                        "captain"
                    ),
                    games.get(
                        "substitute"
                    ),
                    statistics.get(
                        "offsides"
                    ),
                    shots.get(
                        "total"
                    ),
                    shots.get(
                        "on"
                    ),
                    goals.get(
                        "total"
                    ),
                    goals.get(
                        "conceded"
                    ),
                    goals.get(
                        "assists"
                    ),
                    goals.get(
                        "saves"
                    ),
                    passes.get(
                        "total"
                    ),
                    passes.get(
                        "key"
                    ),
                    parse_float(
                        passes.get(
                            "accuracy"
                        )
                    ),
                    tackles.get(
                        "total"
                    ),
                    tackles.get(
                        "blocks"
                    ),
                    tackles.get(
                        "interceptions"
                    ),
                    duels.get(
                        "total"
                    ),
                    duels.get(
                        "won"
                    ),
                    dribbles.get(
                        "attempts"
                    ),
                    dribbles.get(
                        "success"
                    ),
                    dribbles.get(
                        "past"
                    ),
                    fouls.get(
                        "drawn"
                    ),
                    fouls.get(
                        "committed"
                    ),
                    cards.get(
                        "yellow"
                    ),
                    cards.get(
                        "yellowred"
                    ),
                    cards.get(
                        "red"
                    ),
                    penalty.get(
                        "won"
                    ),
                    penalties_committed,
                    penalty.get(
                        "scored"
                    ),
                    penalty.get(
                        "missed"
                    ),
                    penalty.get(
                        "saved"
                    ),
                    Jsonb(
                        player_block
                    ),
                ),
            )


def clear_fixture_detail(
    conn,
    fixture_id,
):
    conn.execute(
        """
        DELETE FROM fixture_events
        WHERE fixture_id = %s
        """,
        (
            fixture_id,
        ),
    )

    conn.execute(
        """
        DELETE FROM fixture_lineup_players
        WHERE fixture_id = %s
        """,
        (
            fixture_id,
        ),
    )

    conn.execute(
        """
        DELETE FROM fixture_lineups
        WHERE fixture_id = %s
        """,
        (
            fixture_id,
        ),
    )

    conn.execute(
        """
        DELETE FROM fixture_player_statistics
        WHERE fixture_id = %s
        """,
        (
            fixture_id,
        ),
    )

    conn.execute(
        """
        DELETE FROM fixture_statistics
        WHERE fixture_id = %s
        """,
        (
            fixture_id,
        ),
    )


def import_fixture_detail(
    conn,
    item,
):
    fixture_id = upsert_fixture(
        conn,
        item,
    )

    if not fixture_id:
        return False

    clear_fixture_detail(
        conn,
        fixture_id,
    )

    insert_events(
        conn,
        fixture_id,
        item.get(
            "events",
            [],
        ) or [],
    )

    insert_lineups(
        conn,
        fixture_id,
        item.get(
            "lineups",
            [],
        ) or [],
    )

    insert_fixture_statistics(
        conn,
        fixture_id,
        item.get(
            "statistics",
            [],
        ) or [],
    )

    insert_fixture_players(
        conn,
        fixture_id,
        item.get(
            "players",
            [],
        ) or [],
    )

    save_raw_data(
        conn,
        fixture_id,
        "fixture_complete",
        item,
    )

    return True


def get_existing_complete_fixtures(
    conn,
    fixture_ids,
):
    if not fixture_ids:
        return set()

    rows = conn.execute(
        """
        SELECT fixture_id
        FROM fixture_raw_data
        WHERE
            source = 'api-football'
            AND data_type = 'fixture_complete'
            AND fixture_id = ANY(%s)
        """,
        (
            fixture_ids,
        ),
    ).fetchall()

    return {
        row[
            "fixture_id"
        ]
        for row in rows
    }


def should_load_detail(
    status,
):
    if not status:
        return False

    return (
        status
        not in NO_DETAIL_STATUSES
    )


def import_details(
    conn,
    client,
    fixture_ids,
    fixture_statuses,
    batch_size,
    resume,
):
    detail_ids = [
        fixture_id
        for fixture_id
        in fixture_ids
        if should_load_detail(
            fixture_statuses.get(
                fixture_id
            )
        )
    ]

    if resume:
        already_complete = (
            get_existing_complete_fixtures(
                conn,
                detail_ids,
            )
        )

        detail_ids = [
            fixture_id
            for fixture_id
            in detail_ids
            if fixture_id
            not in already_complete
        ]

        if already_complete:
            print(
                "resume: skipping "
                f"{len(already_complete)} "
                "already imported fixtures"
            )

    total = len(
        detail_ids
    )

    imported = 0

    if total == 0:
        return 0

    batch_list = list(
        chunks(
            detail_ids,
            batch_size,
        )
    )

    for batch_number, batch in enumerate(
        batch_list,
        start=1,
    ):
        ids_value = "-".join(
            str(
                fixture_id
            )
            for fixture_id
            in batch
        )

        print(
            f"  detail batch "
            f"{batch_number}/"
            f"{len(batch_list)} "
            f"({len(batch)} fixtures)"
        )

        data = client.get(
            "/fixtures",
            params={
                "ids": ids_value,
            },
        )

        response = data.get(
            "response",
            [],
        )

        with conn.transaction():
            for item in response:
                if import_fixture_detail(
                    conn,
                    item,
                ):
                    imported += 1

    return imported


def season_has_match_detail(
    season_info,
):
    coverage = season_info.get(
        "coverage",
        {},
    )

    return any(
        [
            coverage.get(
                "fixture_events",
                False,
            ),
            coverage.get(
                "fixture_lineups",
                False,
            ),
            coverage.get(
                "fixture_team_statistics",
                False,
            ),
            coverage.get(
                "fixture_player_statistics",
                False,
            ),
        ]
    )


def print_coverage(
    season_info,
):
    coverage = season_info.get(
        "coverage",
        {},
    )

    print(
        "  events: "
        f"{coverage.get('fixture_events')}"
    )

    print(
        "  lineups: "
        f"{coverage.get('fixture_lineups')}"
    )

    print(
        "  team stats: "
        f"{coverage.get('fixture_team_statistics')}"
    )

    print(
        "  player stats: "
        f"{coverage.get('fixture_player_statistics')}"
    )


def import_season(
    conn,
    client,
    audit,
    league_id,
    season_info,
    batch_size,
    resume,
):
    season = season_info[
        "year"
    ]

    label = season_info.get(
        "label",
        str(
            season
        ),
    )

    print()

    print(
        f"Importing {label}"
    )

    print_coverage(
        season_info
    )

    request_start = (
        client.request_count
    )

    with conn.transaction():
        ensure_league_and_season(
            conn,
            audit,
            league_id,
            season,
        )

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
        print(
            "  importing teams "
            "and venues..."
        )

        with conn.transaction():
            team_count = (
                import_teams_and_venues(
                    conn,
                    client,
                    league_id,
                    season,
                )
            )

        print(
            f"  teams: {team_count}"
        )

        print(
            "  importing fixture list..."
        )

        with conn.transaction():
            (
                fixture_ids,
                fixture_statuses,
            ) = import_fixture_list(
                conn,
                client,
                league_id,
                season,
            )

        rows_received = len(
            fixture_ids
        )

        rows_inserted = len(
            fixture_ids
        )

        print(
            "  fixtures: "
            f"{len(fixture_ids)}"
        )

        started_count = sum(
            1
            for fixture_id
            in fixture_ids
            if should_load_detail(
                fixture_statuses.get(
                    fixture_id
                )
            )
        )

        print(
            "  fixtures eligible "
            "for detail: "
            f"{started_count}"
        )

        detail_count = 0

        if season_has_match_detail(
            season_info
        ):
            detail_count = (
                import_details(
                    conn,
                    client,
                    fixture_ids,
                    fixture_statuses,
                    batch_size,
                    resume,
                )
            )

        print(
            "  detailed fixtures "
            "imported: "
            f"{detail_count}"
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
            "  api requests: "
            f"{api_requests}"
        )

        print(
            "  daily remaining: "
            f"{quota['daily']}"
        )

        print(
            "  minute remaining: "
            f"{quota['minute']}"
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

    if (
        args.batch_size < 1
        or args.batch_size > 20
    ):
        raise ValueError(
            "--batch-size must be "
            "between 1 and 20."
        )

    API_key = load_environment()

    audit = load_coverage()

    seasons = choose_seasons(
        audit,
        args,
    )

    if not seasons:
        raise RuntimeError(
            "No seasons selected."
        )

    print(
        "Premier League historical "
        "match importer"
    )

    print(
        "Selected seasons:"
    )

    for season in seasons:
        print(
            "  "
            f"{season['label']}"
        )

    print()

    print(
        "Batch size: "
        f"{args.batch_size}"
    )

    print(
        "Resume mode: "
        f"{args.resume}"
    )

    client = ApiClient(
        API_key,
        request_delay=(
            args.request_delay
        ),
    )

    with get_connection() as conn:
        for season_info in seasons:
            import_season(
                conn,
                client,
                audit,
                args.league_id,
                season_info,
                args.batch_size,
                args.resume,
            )

    print()

    print(
        "Historical match import "
        "completed."
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