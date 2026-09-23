import argparse
import json
import os
import re
import time
from datetime import date
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
            "Import season-level historical data "
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
        help=(
            "Skip seasons with a successful "
            "season_history import run."
        ),
    )

    parser.add_argument(
        "--skip-team-statistics",
        action="store_true",
    )

    parser.add_argument(
        "--skip-injuries",
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
            "API_FOOTBALL_KEY is missing "
            "from .env"
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
    seasons = list(
        audit.get(
            "seasons",
            [],
        )
    )

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


def parse_date(value):
    if (
        not value
        or value
        in {
            "Unknown",
            "unknown",
            "N/A",
        }
    ):
        return None

    try:
        return date.fromisoformat(
            str(
                value
            )[:10]
        )

    except ValueError:
        return None


def parse_float(value):
    if (
        value is None
        or value == ""
    ):
        return None

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        return float(
            value
        )

    cleaned = (
        str(
            value
        )
        .replace(
            "%",
            "",
        )
        .strip()
    )

    try:
        return float(
            cleaned
        )

    except ValueError:
        return None


def parse_measurement(value):
    if value is None:
        return None

    match = re.search(
        r"-?\d+",
        str(
            value
        ),
    )

    if not match:
        return None

    return int(
        match.group()
    )


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
            'season_history',
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
            import_type = 'season_history'
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


def save_season_raw(
    conn,
    league_id,
    season,
    data_type,
    data_key,
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
            %s,
            %s,
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
            data_type,
            str(
                data_key
            ),
            Jsonb(
                payload
            ),
        ),
    )


def upsert_team(
    conn,
    team,
):
    if (
        not team
        or not team.get(
            "id"
        )
    ):
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
            team.get(
                "id"
            ),
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
    if (
        not player
        or not player.get(
            "id"
        )
    ):
        return

    birth = (
        player.get(
            "birth"
        )
        or {}
    )

    conn.execute(
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
            first_name = COALESCE(
                EXCLUDED.first_name,
                players.first_name
            ),
            last_name = COALESCE(
                EXCLUDED.last_name,
                players.last_name
            ),
            birth_date = COALESCE(
                EXCLUDED.birth_date,
                players.birth_date
            ),
            nationality = COALESCE(
                EXCLUDED.nationality,
                players.nationality
            ),
            height_cm = COALESCE(
                EXCLUDED.height_cm,
                players.height_cm
            ),
            weight_kg = COALESCE(
                EXCLUDED.weight_kg,
                players.weight_kg
            ),
            photo_url = COALESCE(
                EXCLUDED.photo_url,
                players.photo_url
            ),
            updated_at = NOW()
        """,
        (
            player.get(
                "id"
            ),
            player.get(
                "name"
            ),
            player.get(
                "firstname"
            ),
            player.get(
                "lastname"
            ),
            parse_date(
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
            ),
        ),
    )


def upsert_squad_membership(
    conn,
    league_id,
    season,
    team_id,
    player,
    games,
):
    conn.execute(
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
            squad_number = EXCLUDED.squad_number,
            position = EXCLUDED.position,
            age = EXCLUDED.age,
            photo_url = COALESCE(
                EXCLUDED.photo_url,
                squad_memberships.photo_url
            ),
            imported_at = NOW()
        """,
        (
            league_id,
            season,
            team_id,
            player.get(
                "id"
            ),
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
            ),
        ),
    )


def upsert_player_season_statistics(
    conn,
    league_id,
    season,
    player,
    statistics,
):
    league = (
        statistics.get(
            "league"
        )
        or {}
    )

    team = (
        statistics.get(
            "team"
        )
        or {}
    )

    games = (
        statistics.get(
            "games"
        )
        or {}
    )

    substitutes = (
        statistics.get(
            "substitutes"
        )
        or {}
    )

    shots = (
        statistics.get(
            "shots"
        )
        or {}
    )

    goals = (
        statistics.get(
            "goals"
        )
        or {}
    )

    passes = (
        statistics.get(
            "passes"
        )
        or {}
    )

    tackles = (
        statistics.get(
            "tackles"
        )
        or {}
    )

    duels = (
        statistics.get(
            "duels"
        )
        or {}
    )

    dribbles = (
        statistics.get(
            "dribbles"
        )
        or {}
    )

    fouls = (
        statistics.get(
            "fouls"
        )
        or {}
    )

    cards = (
        statistics.get(
            "cards"
        )
        or {}
    )

    penalty = (
        statistics.get(
            "penalty"
        )
        or {}
    )

    if league.get(
        "id"
    ) not in (
        None,
        league_id,
    ):
        return False

    team_id = team.get(
        "id"
    )

    if not team_id:
        return False

    upsert_team(
        conn,
        team,
    )

    appearances = games.get(
        "appearences"
    )

    if appearances is None:
        appearances = games.get(
            "appearances"
        )

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
            raw_payload,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
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
            appearances = EXCLUDED.appearances,
            lineups = EXCLUDED.lineups,
            minutes = EXCLUDED.minutes,
            squad_number = EXCLUDED.squad_number,
            position = EXCLUDED.position,
            rating = EXCLUDED.rating,
            captain = EXCLUDED.captain,
            substitutes_in = EXCLUDED.substitutes_in,
            substitutes_out = EXCLUDED.substitutes_out,
            substitutes_bench = EXCLUDED.substitutes_bench,
            shots_total = EXCLUDED.shots_total,
            shots_on_goal = EXCLUDED.shots_on_goal,
            goals_total = EXCLUDED.goals_total,
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
            league_id,
            season,
            team_id,
            player.get(
                "id"
            ),
            appearances,
            games.get(
                "lineups"
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
            substitutes.get(
                "in"
            ),
            substitutes.get(
                "out"
            ),
            substitutes.get(
                "bench"
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
                statistics
            ),
        ),
    )

    upsert_squad_membership(
        conn,
        league_id,
        season,
        team_id,
        player,
        games,
    )

    return True


def import_players(
    conn,
    client,
    league_id,
    season,
):
    page = 1
    total_pages = 1

    player_rows = 0
    stat_rows = 0

    while page <= total_pages:
        data = client.get(
            "/players",
            params={
                "league": league_id,
                "season": season,
                "page": page,
            },
        )

        paging = (
            data.get(
                "paging"
            )
            or {}
        )

        total_pages = int(
            paging.get(
                "total"
            )
            or 1
        )

        save_season_raw(
            conn,
            league_id,
            season,
            "players",
            f"page_{page}",
            data,
        )

        response = (
            data.get(
                "response"
            )
            or []
        )

        for entry in response:
            player = (
                entry.get(
                    "player"
                )
                or {}
            )

            if not player.get(
                "id"
            ):
                continue

            upsert_player(
                conn,
                player,
            )

            player_rows += 1

            for statistics in (
                entry.get(
                    "statistics"
                )
                or []
            ):
                if upsert_player_season_statistics(
                    conn,
                    league_id,
                    season,
                    player,
                    statistics,
                ):
                    stat_rows += 1

        print(
            f"    players page "
            f"{page}/{total_pages}: "
            f"{len(response)} rows"
        )

        page += 1

    return (
        player_rows,
        stat_rows,
    )


def upsert_standing(
    conn,
    league_id,
    season,
    row,
):
    team = (
        row.get(
            "team"
        )
        or {}
    )

    team_id = team.get(
        "id"
    )

    if not team_id:
        return False

    upsert_team(
        conn,
        team,
    )

    all_stats = (
        row.get(
            "all"
        )
        or {}
    )

    home = (
        row.get(
            "home"
        )
        or {}
    )

    away = (
        row.get(
            "away"
        )
        or {}
    )

    all_goals = (
        all_stats.get(
            "goals"
        )
        or {}
    )

    home_goals = (
        home.get(
            "goals"
        )
        or {}
    )

    away_goals = (
        away.get(
            "goals"
        )
        or {}
    )

    conn.execute(
        """
        INSERT INTO season_standings (
            league_id,
            season,
            team_id,
            group_name,
            league_rank,
            points,
            goals_difference,
            form,
            description,
            played_total,
            wins_total,
            draws_total,
            losses_total,
            goals_for_total,
            goals_against_total,
            played_home,
            wins_home,
            draws_home,
            losses_home,
            goals_for_home,
            goals_against_home,
            played_away,
            wins_away,
            draws_away,
            losses_away,
            goals_for_away,
            goals_against_away,
            raw_payload,
            updated_at
        )
        VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s,
            NOW()
        )
        ON CONFLICT (
            league_id,
            season,
            team_id
        )
        DO UPDATE SET
            group_name = EXCLUDED.group_name,
            league_rank = EXCLUDED.league_rank,
            points = EXCLUDED.points,
            goals_difference = EXCLUDED.goals_difference,
            form = EXCLUDED.form,
            description = EXCLUDED.description,
            played_total = EXCLUDED.played_total,
            wins_total = EXCLUDED.wins_total,
            draws_total = EXCLUDED.draws_total,
            losses_total = EXCLUDED.losses_total,
            goals_for_total = EXCLUDED.goals_for_total,
            goals_against_total = EXCLUDED.goals_against_total,
            played_home = EXCLUDED.played_home,
            wins_home = EXCLUDED.wins_home,
            draws_home = EXCLUDED.draws_home,
            losses_home = EXCLUDED.losses_home,
            goals_for_home = EXCLUDED.goals_for_home,
            goals_against_home = EXCLUDED.goals_against_home,
            played_away = EXCLUDED.played_away,
            wins_away = EXCLUDED.wins_away,
            draws_away = EXCLUDED.draws_away,
            losses_away = EXCLUDED.losses_away,
            goals_for_away = EXCLUDED.goals_for_away,
            goals_against_away = EXCLUDED.goals_against_away,
            raw_payload = EXCLUDED.raw_payload,
            updated_at = NOW()
        """,
        (
            league_id,
            season,
            team_id,
            row.get(
                "group"
            ),
            row.get(
                "rank"
            ),
            row.get(
                "points"
            ),
            row.get(
                "goalsDiff"
            ),
            row.get(
                "form"
            ),
            row.get(
                "description"
            ),
            all_stats.get(
                "played"
            ),
            all_stats.get(
                "win"
            ),
            all_stats.get(
                "draw"
            ),
            all_stats.get(
                "lose"
            ),
            all_goals.get(
                "for"
            ),
            all_goals.get(
                "against"
            ),
            home.get(
                "played"
            ),
            home.get(
                "win"
            ),
            home.get(
                "draw"
            ),
            home.get(
                "lose"
            ),
            home_goals.get(
                "for"
            ),
            home_goals.get(
                "against"
            ),
            away.get(
                "played"
            ),
            away.get(
                "win"
            ),
            away.get(
                "draw"
            ),
            away.get(
                "lose"
            ),
            away_goals.get(
                "for"
            ),
            away_goals.get(
                "against"
            ),
            Jsonb(
                row
            ),
        ),
    )

    return True


def import_standings(
    conn,
    client,
    league_id,
    season,
):
    data = client.get(
        "/standings",
        params={
            "league": league_id,
            "season": season,
        },
    )

    save_season_raw(
        conn,
        league_id,
        season,
        "standings",
        "all",
        data,
    )

    inserted = 0

    for competition in (
        data.get(
            "response"
        )
        or []
    ):
        league = (
            competition.get(
                "league"
            )
            or {}
        )

        for group in (
            league.get(
                "standings"
            )
            or []
        ):
            for row in group:
                if upsert_standing(
                    conn,
                    league_id,
                    season,
                    row,
                ):
                    inserted += 1

    return inserted


def get_season_team_ids(
    conn,
    league_id,
    season,
):
    rows = conn.execute(
        """
        SELECT DISTINCT team_id
        FROM (
            SELECT
                home_team_id AS team_id
            FROM fixtures
            WHERE
                league_id = %s
                AND season = %s

            UNION

            SELECT
                away_team_id AS team_id
            FROM fixtures
            WHERE
                league_id = %s
                AND season = %s
        ) season_teams
        WHERE team_id IS NOT NULL
        ORDER BY team_id
        """,
        (
            league_id,
            season,
            league_id,
            season,
        ),
    ).fetchall()

    return [
        row[
            "team_id"
        ]
        for row
        in rows
    ]


def import_one_team_statistics(
    conn,
    client,
    league_id,
    season,
    team_id,
):
    data = client.get(
        "/teams/statistics",
        params={
            "league": league_id,
            "season": season,
            "team": team_id,
        },
    )

    save_season_raw(
        conn,
        league_id,
        season,
        "team_statistics",
        f"team_{team_id}",
        data,
    )

    response = (
        data.get(
            "response"
        )
        or {}
    )

    if not response:
        return False

    team = (
        response.get(
            "team"
        )
        or {}
    )

    upsert_team(
        conn,
        team,
    )

    fixtures = (
        response.get(
            "fixtures"
        )
        or {}
    )

    goals = (
        response.get(
            "goals"
        )
        or {}
    )

    biggest = (
        response.get(
            "biggest"
        )
        or {}
    )

    clean_sheet = (
        response.get(
            "clean_sheet"
        )
        or {}
    )

    failed_to_score = (
        response.get(
            "failed_to_score"
        )
        or {}
    )

    penalty = (
        response.get(
            "penalty"
        )
        or {}
    )

    played = (
        fixtures.get(
            "played"
        )
        or {}
    )

    wins = (
        fixtures.get(
            "wins"
        )
        or {}
    )

    draws = (
        fixtures.get(
            "draws"
        )
        or {}
    )

    loses = (
        fixtures.get(
            "loses"
        )
        or {}
    )

    goals_for = (
        goals.get(
            "for"
        )
        or {}
    )

    goals_against = (
        goals.get(
            "against"
        )
        or {}
    )

    goals_for_total = (
        goals_for.get(
            "total"
        )
        or {}
    )

    goals_for_avg = (
        goals_for.get(
            "average"
        )
        or {}
    )

    goals_against_total = (
        goals_against.get(
            "total"
        )
        or {}
    )

    goals_against_avg = (
        goals_against.get(
            "average"
        )
        or {}
    )

    streak = (
        biggest.get(
            "streak"
        )
        or {}
    )

    biggest_wins = (
        biggest.get(
            "wins"
        )
        or {}
    )

    biggest_loses = (
        biggest.get(
            "loses"
        )
        or {}
    )

    penalty_scored = (
        penalty.get(
            "scored"
        )
        or {}
    )

    penalty_missed = (
        penalty.get(
            "missed"
        )
        or {}
    )

    conn.execute(
        """
        INSERT INTO team_season_api_statistics (
            league_id,
            season,
            team_id,
            form,
            fixtures_played_home,
            fixtures_played_away,
            fixtures_played_total,
            wins_home,
            wins_away,
            wins_total,
            draws_home,
            draws_away,
            draws_total,
            losses_home,
            losses_away,
            losses_total,
            goals_for_home,
            goals_for_away,
            goals_for_total,
            goals_against_home,
            goals_against_away,
            goals_against_total,
            goals_for_avg_home,
            goals_for_avg_away,
            goals_for_avg_total,
            goals_against_avg_home,
            goals_against_avg_away,
            goals_against_avg_total,
            biggest_winning_streak,
            biggest_drawing_streak,
            biggest_losing_streak,
            biggest_win_home,
            biggest_win_away,
            biggest_loss_home,
            biggest_loss_away,
            clean_sheets_home,
            clean_sheets_away,
            clean_sheets_total,
            failed_to_score_home,
            failed_to_score_away,
            failed_to_score_total,
            penalties_scored,
            penalties_missed,
            penalties_total,
            penalties_percentage,
            raw_payload,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s,
            NOW()
        )
        ON CONFLICT (
            league_id,
            season,
            team_id
        )
        DO UPDATE SET
            form = EXCLUDED.form,
            fixtures_played_home = EXCLUDED.fixtures_played_home,
            fixtures_played_away = EXCLUDED.fixtures_played_away,
            fixtures_played_total = EXCLUDED.fixtures_played_total,
            wins_home = EXCLUDED.wins_home,
            wins_away = EXCLUDED.wins_away,
            wins_total = EXCLUDED.wins_total,
            draws_home = EXCLUDED.draws_home,
            draws_away = EXCLUDED.draws_away,
            draws_total = EXCLUDED.draws_total,
            losses_home = EXCLUDED.losses_home,
            losses_away = EXCLUDED.losses_away,
            losses_total = EXCLUDED.losses_total,
            goals_for_home = EXCLUDED.goals_for_home,
            goals_for_away = EXCLUDED.goals_for_away,
            goals_for_total = EXCLUDED.goals_for_total,
            goals_against_home = EXCLUDED.goals_against_home,
            goals_against_away = EXCLUDED.goals_against_away,
            goals_against_total = EXCLUDED.goals_against_total,
            goals_for_avg_home = EXCLUDED.goals_for_avg_home,
            goals_for_avg_away = EXCLUDED.goals_for_avg_away,
            goals_for_avg_total = EXCLUDED.goals_for_avg_total,
            goals_against_avg_home = EXCLUDED.goals_against_avg_home,
            goals_against_avg_away = EXCLUDED.goals_against_avg_away,
            goals_against_avg_total = EXCLUDED.goals_against_avg_total,
            biggest_winning_streak = EXCLUDED.biggest_winning_streak,
            biggest_drawing_streak = EXCLUDED.biggest_drawing_streak,
            biggest_losing_streak = EXCLUDED.biggest_losing_streak,
            biggest_win_home = EXCLUDED.biggest_win_home,
            biggest_win_away = EXCLUDED.biggest_win_away,
            biggest_loss_home = EXCLUDED.biggest_loss_home,
            biggest_loss_away = EXCLUDED.biggest_loss_away,
            clean_sheets_home = EXCLUDED.clean_sheets_home,
            clean_sheets_away = EXCLUDED.clean_sheets_away,
            clean_sheets_total = EXCLUDED.clean_sheets_total,
            failed_to_score_home = EXCLUDED.failed_to_score_home,
            failed_to_score_away = EXCLUDED.failed_to_score_away,
            failed_to_score_total = EXCLUDED.failed_to_score_total,
            penalties_scored = EXCLUDED.penalties_scored,
            penalties_missed = EXCLUDED.penalties_missed,
            penalties_total = EXCLUDED.penalties_total,
            penalties_percentage = EXCLUDED.penalties_percentage,
            raw_payload = EXCLUDED.raw_payload,
            updated_at = NOW()
        """,
        (
            league_id,
            season,
            team_id,
            response.get(
                "form"
            ),
            played.get(
                "home"
            ),
            played.get(
                "away"
            ),
            played.get(
                "total"
            ),
            wins.get(
                "home"
            ),
            wins.get(
                "away"
            ),
            wins.get(
                "total"
            ),
            draws.get(
                "home"
            ),
            draws.get(
                "away"
            ),
            draws.get(
                "total"
            ),
            loses.get(
                "home"
            ),
            loses.get(
                "away"
            ),
            loses.get(
                "total"
            ),
            goals_for_total.get(
                "home"
            ),
            goals_for_total.get(
                "away"
            ),
            goals_for_total.get(
                "total"
            ),
            goals_against_total.get(
                "home"
            ),
            goals_against_total.get(
                "away"
            ),
            goals_against_total.get(
                "total"
            ),
            parse_float(
                goals_for_avg.get(
                    "home"
                )
            ),
            parse_float(
                goals_for_avg.get(
                    "away"
                )
            ),
            parse_float(
                goals_for_avg.get(
                    "total"
                )
            ),
            parse_float(
                goals_against_avg.get(
                    "home"
                )
            ),
            parse_float(
                goals_against_avg.get(
                    "away"
                )
            ),
            parse_float(
                goals_against_avg.get(
                    "total"
                )
            ),
            streak.get(
                "wins"
            ),
            streak.get(
                "draws"
            ),
            streak.get(
                "loses"
            ),
            biggest_wins.get(
                "home"
            ),
            biggest_wins.get(
                "away"
            ),
            biggest_loses.get(
                "home"
            ),
            biggest_loses.get(
                "away"
            ),
            clean_sheet.get(
                "home"
            ),
            clean_sheet.get(
                "away"
            ),
            clean_sheet.get(
                "total"
            ),
            failed_to_score.get(
                "home"
            ),
            failed_to_score.get(
                "away"
            ),
            failed_to_score.get(
                "total"
            ),
            penalty_scored.get(
                "total"
            ),
            penalty_missed.get(
                "total"
            ),
            penalty.get(
                "total"
            ),
            parse_float(
                penalty_scored.get(
                    "percentage"
                )
            ),
            Jsonb(
                response
            ),
        ),
    )

    return True


def import_team_statistics(
    conn,
    client,
    league_id,
    season,
):
    team_ids = (
        get_season_team_ids(
            conn,
            league_id,
            season,
        )
    )

    inserted = 0

    for (
        index,
        team_id,
    ) in enumerate(
        team_ids,
        start=1,
    ):
        if import_one_team_statistics(
            conn,
            client,
            league_id,
            season,
            team_id,
        ):
            inserted += 1

        print(
            "    team statistics "
            f"{index}/{len(team_ids)} "
            f"(team_id={team_id})"
        )

    return inserted


def import_injuries(
    conn,
    client,
    league_id,
    season,
):
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

    page = 1
    total_pages = 1

    inserted = 0

    while page <= total_pages:
        data = client.get(
            "/injuries",
            params={
                "league": league_id,
                "season": season,
                "page": page,
            },
        )

        paging = (
            data.get(
                "paging"
            )
            or {}
        )

        total_pages = int(
            paging.get(
                "total"
            )
            or 1
        )

        save_season_raw(
            conn,
            league_id,
            season,
            "injuries",
            f"page_{page}",
            data,
        )

        response = (
            data.get(
                "response"
            )
            or []
        )

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

            if team.get(
                "id"
            ):
                upsert_team(
                    conn,
                    team,
                )

            if player.get(
                "id"
            ):
                upsert_player(
                    conn,
                    {
                        "id": player.get(
                            "id"
                        ),
                        "name": player.get(
                            "name"
                        ),
                        "photo": player.get(
                            "photo"
                        ),
                    },
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

            conn.execute(
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

            inserted += 1

        print(
            f"    injuries page "
            f"{page}/{total_pages}: "
            f"{len(response)} rows"
        )

        page += 1

    return inserted


def import_season(
    conn,
    client,
    league_id,
    season_info,
    args,
):
    season = season_info[
        "year"
    ]

    coverage = (
        season_info.get(
            "coverage"
        )
        or {}
    )

    if (
        args.resume
        and season_already_imported(
            conn,
            league_id,
            season,
        )
    ):
        print(
            f"{season_label(season)}: "
            "already imported, skipping"
        )

        return

    print()

    print(
        "Importing season data "
        f"{season_label(season)}"
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
        if coverage.get(
            "players"
        ):
            print(
                "  importing players "
                "and player-season statistics..."
            )

            with conn.transaction():
                (
                    player_rows,
                    player_stat_rows,
                ) = import_players(
                    conn,
                    client,
                    league_id,
                    season,
                )

            rows_received += (
                player_rows
            )

            rows_inserted += (
                player_stat_rows
            )

            print(
                f"  players: "
                f"{player_rows}"
            )

            print(
                "  player-season "
                "statistic rows: "
                f"{player_stat_rows}"
            )

        else:
            print(
                "  players: coverage "
                "unavailable, skipping"
            )

        if coverage.get(
            "standings"
        ):
            print(
                "  importing standings..."
            )

            with conn.transaction():
                standing_rows = (
                    import_standings(
                        conn,
                        client,
                        league_id,
                        season,
                    )
                )

            rows_received += (
                standing_rows
            )

            rows_inserted += (
                standing_rows
            )

            print(
                f"  standing rows: "
                f"{standing_rows}"
            )

        else:
            print(
                "  standings: coverage "
                "unavailable, skipping"
            )

        if not args.skip_team_statistics:
            print(
                "  importing team "
                "season statistics..."
            )

            with conn.transaction():
                team_stat_rows = (
                    import_team_statistics(
                        conn,
                        client,
                        league_id,
                        season,
                    )
                )

            rows_received += (
                team_stat_rows
            )

            rows_inserted += (
                team_stat_rows
            )

            print(
                "  team season statistic "
                f"rows: {team_stat_rows}"
            )

        if (
            coverage.get(
                "injuries"
            )
            and not args.skip_injuries
        ):
            print(
                "  importing injuries..."
            )

            with conn.transaction():
                injury_rows = (
                    import_injuries(
                        conn,
                        client,
                        league_id,
                        season,
                    )
                )

            rows_received += (
                injury_rows
            )

            rows_inserted += (
                injury_rows
            )

            print(
                f"  injury rows: "
                f"{injury_rows}"
            )

        else:
            print(
                "  injuries: unavailable "
                "or skipped"
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
            f"  api requests: "
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
        "Premier League season "
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

    print(
        f"Resume mode: "
        f"{args.resume}"
    )

    print(
        f"Request delay: "
        f"{args.request_delay}s"
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
                args.league_id,
                season_info,
                args,
            )

    print()

    print(
        "Season history import "
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