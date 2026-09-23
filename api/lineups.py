from fastapi import APIRouter, HTTPException

from api.database import fetch_all, fetch_one


router = APIRouter()


def coerce_int(value):
    if value is None:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError
    ):
        return value


def extract_fixture_lineups(
    payload,
    fixture_id: int
):
    if not isinstance(
        payload,
        dict
    ):
        return []

    if isinstance(
        payload.get("lineups"),
        list
    ):
        return payload.get(
            "lineups"
        ) or []

    response = payload.get(
        "response"
    )

    if isinstance(
        response,
        dict
    ):
        if isinstance(
            response.get("lineups"),
            list
        ):
            return response.get(
                "lineups"
            ) or []

    if isinstance(
        response,
        list
    ):
        for item in response:
            if not isinstance(
                item,
                dict
            ):
                continue

            item_fixture = (
                item.get(
                    "fixture"
                )
                or {}
            )

            if (
                item_fixture.get(
                    "id"
                )
                not in {
                    None,
                    fixture_id
                }
            ):
                continue

            if isinstance(
                item.get("lineups"),
                list
            ):
                return item.get(
                    "lineups"
                ) or []

        if (
            response
            and all(
                isinstance(
                    item,
                    dict
                )
                and "team" in item
                for item in response
            )
        ):
            return response

    return []


def normalize_lineup_player(
    item,
    starter: bool
):
    player = (
        item.get(
            "player"
        )
        if isinstance(
            item,
            dict
        )
        else {}
    ) or {}

    return {
        "player_id": coerce_int(
            player.get("id")
        ),
        "photo_url": player.get("photo"),
        "player_name": player.get(
            "name"
        ),
        "number": player.get(
            "number"
        ),
        "position": (
            player.get(
                "pos"
            )
            or player.get(
                "position"
            )
        ),
        "grid": player.get(
            "grid"
        ),
        "starter": starter
    }


def normalize_fixture_lineup(
    lineup
):
    team = (
        lineup.get(
            "team"
        )
        or {}
    )

    coach = (
        lineup.get(
            "coach"
        )
        or {}
    )

    starting_xi = [
        normalize_lineup_player(
            item,
            True
        )
        for item in (
            lineup.get(
                "startXI"
            )
            or lineup.get(
                "starting_xi"
            )
            or []
        )
    ]

    substitutes = [
        normalize_lineup_player(
            item,
            False
        )
        for item in (
            lineup.get(
                "substitutes"
            )
            or []
        )
    ]

    return {
        "team_id": coerce_int(
            team.get(
                "id"
            )
        ),
        "team_name": team.get(
            "name"
        ),
        "team_logo_url": team.get(
            "logo"
        ),
        "formation": lineup.get(
            "formation"
        ),
        "coach": {
            "coach_id": coach.get(
                "id"
            ),
            "name": coach.get(
                "name"
            ),
            "photo_url": coach.get(
                "photo"
            )
        },
        "starting_xi": starting_xi,
        "substitutes": substitutes
    }


@router.get(
    "/api/fixtures/{fixture_id}/lineups"
)
def get_fixture_lineups(
    fixture_id: int
):
    fixture = fetch_one(
        """
        SELECT
            f.fixture_id,
            f.league_id,
            f.season,
            f.home_team_id,
            home.team_name AS home_team,
            home.logo_url AS home_team_logo_url,
            f.away_team_id,
            away.team_name AS away_team,
            away.logo_url AS away_team_logo_url
        FROM fixtures f

        JOIN teams home
            ON home.team_id = f.home_team_id

        JOIN teams away
            ON away.team_id = f.away_team_id

        WHERE f.fixture_id = %s;
        """,
        (
            fixture_id,
        )
    )

    if fixture is None:
        raise HTTPException(
            status_code=404,
            detail="Fixture not found"
        )

    raw_rows = fetch_all(
        """
        SELECT
            data_type,
            payload
        FROM fixture_raw_data
        WHERE fixture_id = %s
          AND source = 'api-football'
          AND data_type IN (
              'lineups_direct',
              'fixture_complete',
              'fixture_base'
          )
        ORDER BY
            CASE data_type
                WHEN 'lineups_direct'
                THEN 1

                WHEN 'fixture_complete'
                THEN 2

                ELSE 3
            END;
        """,
        (
            fixture_id,
        )
    )

    raw_lineups = []

    for raw_row in raw_rows:
        raw_lineups = (
            extract_fixture_lineups(
                raw_row.get(
                    "payload"
                ),
                fixture_id
            )
        )

        if raw_lineups:
            break

    lineups = [
        normalize_fixture_lineup(
            lineup
        )
        for lineup in raw_lineups
        if isinstance(
            lineup,
            dict
        )
    ]

    team_fallbacks = {
        fixture[
            "home_team_id"
        ]: {
            "team_name": fixture[
                "home_team"
            ],
            "team_logo_url": fixture[
                "home_team_logo_url"
            ]
        },

        fixture[
            "away_team_id"
        ]: {
            "team_name": fixture[
                "away_team"
            ],
            "team_logo_url": fixture[
                "away_team_logo_url"
            ]
        }
    }

    for lineup in lineups:
        fallback = team_fallbacks.get(
            lineup.get(
                "team_id"
            )
        )

        if not fallback:
            continue

        lineup[
            "team_name"
        ] = (
            lineup.get(
                "team_name"
            )
            or fallback[
                "team_name"
            ]
        )

        lineup[
            "team_logo_url"
        ] = (
            lineup.get(
                "team_logo_url"
            )
            or fallback[
                "team_logo_url"
            ]
        )

    team_order = {
        fixture[
            "home_team_id"
        ]: 0,

        fixture[
            "away_team_id"
        ]: 1
    }

    player_ids = {
        player["player_id"]
        for lineup in lineups
        for player in lineup["starting_xi"] + lineup["substitutes"]
        if isinstance(player["player_id"], int)
    }

    if player_ids:
        photos = fetch_all(
            """
            SELECT p.player_id, sm.team_id,
                   COALESCE(p.photo_url, sm.photo_url) AS photo_url
            FROM players p
            LEFT JOIN squad_memberships sm
                ON sm.player_id = p.player_id
                AND sm.league_id = %s
                AND sm.season = %s
                AND sm.team_id IN (%s, %s)
            WHERE p.player_id = ANY(%s);
            """,
            (
                fixture["league_id"], fixture["season"],
                fixture["home_team_id"], fixture["away_team_id"],
                list(player_ids),
            ),
        )
        photo_lookup = {
            (row["player_id"], row["team_id"]): row["photo_url"]
            for row in photos
        }
        for lineup in lineups:
            for player in lineup["starting_xi"] + lineup["substitutes"]:
                player["photo_url"] = (
                    photo_lookup.get((player["player_id"], lineup["team_id"]))
                    or photo_lookup.get((player["player_id"], None))
                    or player["photo_url"]
                )

    lineups.sort(
        key=lambda lineup: (
            team_order.get(
                lineup.get(
                    "team_id"
                ),
                2
            )
        )
    )

    return {
        "fixture_id": fixture_id,
        "league_id": fixture[
            "league_id"
        ],
        "season": fixture[
            "season"
        ],
        "available": (
            len(lineups) > 0
        ),
        "home_team_id": fixture[
            "home_team_id"
        ],
        "away_team_id": fixture[
            "away_team_id"
        ],
        "lineups": lineups
    }
