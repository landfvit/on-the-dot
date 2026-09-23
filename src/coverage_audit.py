import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_URL = "https://v3.football.api-sports.io"

DEFAULT_LEAGUE_ID = 39

DEFAULT_OUTPUT = Path(
    "data/audits/premier_league_coverage.json"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Audit API-Football coverage "
            "for every season of a league."
        )
    )

    parser.add_argument(
        "--league-id",
        type=int,
        default=DEFAULT_LEAGUE_ID,
        help=(
            "API-Football league ID. "
            "Default: 39 (Premier League)."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Path where the normalized "
            "coverage JSON will be saved."
        ),
    )

    return parser.parse_args()


def get_api_key():
    load_dotenv()

    API_key = os.getenv(
        "API_FOOTBALL_KEY"
    )

    if not API_key:
        raise RuntimeError(
            "API_FOOTBALL_KEY is missing "
            "from the .env file."
        )

    return API_key


def api_get(
    endpoint,
    API_key,
    params=None,
):
    url = (
        f"{BASE_URL}{endpoint}"
    )

    response = requests.get(
        url,
        headers={
            "x-apisports-key": API_key,
        },
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    errors = data.get(
        "errors"
    )

    if errors:
        raise RuntimeError(
            "API-Football returned "
            f"errors: {errors}"
        )

    return (
        data,
        response.headers,
    )


def yes_no(value):
    if value:
        return "YES"

    return "no"


def season_label(year):
    return (
        f"{year}/"
        f"{str(year + 1)[-2:]}"
    )


def normalize_season(
    season,
):
    coverage = (
        season.get(
            "coverage"
        )
        or {}
    )

    fixtures = (
        coverage.get(
            "fixtures"
        )
        or {}
    )

    return {
        "year": season.get(
            "year"
        ),

        "label": season_label(
            season["year"]
        ),

        "start": season.get(
            "start"
        ),

        "end": season.get(
            "end"
        ),

        "current": bool(
            season.get(
                "current"
            )
        ),

        "coverage": {
            "fixture_events": bool(
                fixtures.get(
                    "events"
                )
            ),

            "fixture_lineups": bool(
                fixtures.get(
                    "lineups"
                )
            ),

            "fixture_team_statistics": bool(
                fixtures.get(
                    "statistics_fixtures"
                )
            ),

            "fixture_player_statistics": bool(
                fixtures.get(
                    "statistics_players"
                )
            ),

            "standings": bool(
                coverage.get(
                    "standings"
                )
            ),

            "players": bool(
                coverage.get(
                    "players"
                )
            ),

            "top_scorers": bool(
                coverage.get(
                    "top_scorers"
                )
            ),

            "top_assists": bool(
                coverage.get(
                    "top_assists"
                )
            ),

            "top_cards": bool(
                coverage.get(
                    "top_cards"
                )
            ),

            "injuries": bool(
                coverage.get(
                    "injuries"
                )
            ),

            "predictions": bool(
                coverage.get(
                    "predictions"
                )
            ),

            "odds": bool(
                coverage.get(
                    "odds"
                )
            ),
        },

        "raw_coverage": coverage,
    }


def print_table(
    seasons,
):
    columns = [
        (
            "Season",
            10,
        ),
        (
            "Events",
            8,
        ),
        (
            "Lineups",
            8,
        ),
        (
            "TeamStat",
            9,
        ),
        (
            "PlayerStat",
            11,
        ),
        (
            "Standings",
            10,
        ),
        (
            "Players",
            8,
        ),
        (
            "Injuries",
            9,
        ),
        (
            "Predict",
            8,
        ),
        (
            "Odds",
            6,
        ),
    ]

    header = " ".join(
        title.ljust(
            width
        )
        for (
            title,
            width,
        )
        in columns
    )

    print()

    print(
        header
    )

    print(
        "-" * len(
            header
        )
    )

    for season in seasons:
        coverage = (
            season[
                "coverage"
            ]
        )

        values = [
            season[
                "label"
            ],

            yes_no(
                coverage[
                    "fixture_events"
                ]
            ),

            yes_no(
                coverage[
                    "fixture_lineups"
                ]
            ),

            yes_no(
                coverage[
                    "fixture_team_statistics"
                ]
            ),

            yes_no(
                coverage[
                    "fixture_player_statistics"
                ]
            ),

            yes_no(
                coverage[
                    "standings"
                ]
            ),

            yes_no(
                coverage[
                    "players"
                ]
            ),

            yes_no(
                coverage[
                    "injuries"
                ]
            ),

            yes_no(
                coverage[
                    "predictions"
                ]
            ),

            yes_no(
                coverage[
                    "odds"
                ]
            ),
        ]

        print(
            " ".join(
                str(
                    value
                ).ljust(
                    width
                )
                for (
                    value,
                    (
                        _,
                        width,
                    ),
                )
                in zip(
                    values,
                    columns,
                )
            )
        )

    print()


def print_full_coverage_summary(
    seasons,
):
    fully_covered = []

    for season in seasons:
        coverage = (
            season[
                "coverage"
            ]
        )

        has_core_match_data = all(
            [
                coverage[
                    "fixture_events"
                ],

                coverage[
                    "fixture_lineups"
                ],

                coverage[
                    "fixture_team_statistics"
                ],

                coverage[
                    "fixture_player_statistics"
                ],
            ]
        )

        if has_core_match_data:
            fully_covered.append(
                season[
                    "label"
                ]
            )

    print(
        "Seasons with full core "
        "match coverage:"
    )

    print(
        "events + lineups + "
        "team stats + player stats"
    )

    if not fully_covered:
        print(
            "  none"
        )

        return

    for label in fully_covered:
        print(
            f"  {label}"
        )


def get_quota_info(
    headers,
):
    return {
        "daily_limit": headers.get(
            "x-ratelimit-requests-limit"
        ),

        "daily_remaining": headers.get(
            "x-ratelimit-requests-remaining"
        ),

        "minute_limit": (
            headers.get(
                "X-RateLimit-Limit"
            )
            or headers.get(
                "x-ratelimit-limit"
            )
        ),

        "minute_remaining": (
            headers.get(
                "X-RateLimit-Remaining"
            )
            or headers.get(
                "x-ratelimit-remaining"
            )
        ),
    }


def save_audit(
    output_path,
    league,
    country,
    seasons,
    quota,
):
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "generated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "source": (
            "API-Football"
        ),

        "league": {
            "id": league.get(
                "id"
            ),

            "name": league.get(
                "name"
            ),

            "type": league.get(
                "type"
            ),

            "logo": league.get(
                "logo"
            ),
        },

        "country": country,

        "quota_after_request": (
            quota
        ),

        "season_count": len(
            seasons
        ),

        "seasons": seasons,
    }

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main():
    args = parse_args()

    API_key = get_api_key()

    data, headers = api_get(
        "/leagues",
        API_key,
        params={
            "id": args.league_id,
        },
    )

    response_items = data.get(
        "response",
        [],
    )

    if not response_items:
        raise RuntimeError(
            "No league found for "
            f"ID {args.league_id}."
        )

    league_data = (
        response_items[0]
    )

    league = league_data.get(
        "league",
        {},
    )

    country = league_data.get(
        "country",
        {},
    )

    raw_seasons = league_data.get(
        "seasons",
        [],
    )

    seasons = [
        normalize_season(
            season
        )
        for season
        in raw_seasons
    ]

    seasons.sort(
        key=lambda item: (
            item["year"]
        ),
        reverse=True,
    )

    quota = get_quota_info(
        headers
    )

    print()

    print(
        f"{league.get('name')} "
        f"(league_id="
        f"{league.get('id')})"
    )

    print(
        "Country: "
        f"{country.get('name')}"
    )

    print(
        "Available seasons: "
        f"{len(seasons)}"
    )

    print_table(
        seasons
    )

    print_full_coverage_summary(
        seasons
    )

    print()

    print(
        "Quota after request:"
    )

    print(
        "  daily remaining: "
        f"{quota['daily_remaining']} "
        "or 'unknown'}"
    )

    print(
        "  minute remaining: "
        f"{quota['minute_remaining']} "
        "or 'unknown'}"
    )

    save_audit(
        args.output,
        league,
        country,
        seasons,
        quota,
    )

    print()

    print(
        "Saved audit to: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()