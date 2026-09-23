from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.database import fetch_all, fetch_one
from api.lineups import router as lineups_router
from api.profile_enrichment import router as profile_enrichment_router
from api.squad_data import SEASON_ROSTER_CTE
from api.team_context import router as team_context_router
from api.trivia import router as trivia_router
from api.trivia_access import require_editor
from api.match_context import router as match_context_router
from api.player_history import router as player_history_router


BASE_DIR = Path(__file__).resolve().parent.parent

WEB_DIR = BASE_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
PUBLIC_STATIC_DIR = WEB_DIR / "static"


app = FastAPI(
    title="Premier League Analytics API",
    version="0.1.0"
)


class PublicWebFiles(StaticFiles):
    async def get_response(self, path, scope):
        if path == 'templates' or path.startswith('templates/'):
            raise HTTPException(404, 'Not found')
        return await super().get_response(path, scope)


@app.middleware('http')
async def private_trivia_cache_policy(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(('/api/trivia/', '/internal/trivia')):
        response.headers['Cache-Control'] = 'no-store'
    return response


app.mount(
    "/static",
    PublicWebFiles(directory=WEB_DIR),
    name="static"
)

app.mount(
    "/assets",
    StaticFiles(directory=PUBLIC_STATIC_DIR),
    name="assets"
)


templates = Jinja2Templates(
    directory=TEMPLATES_DIR
)


app.include_router(
    lineups_router
)
app.include_router(profile_enrichment_router)
app.include_router(team_context_router)
app.include_router(trivia_router)
app.include_router(match_context_router)
app.include_router(player_history_router)


@app.get('/trivia', response_class=HTMLResponse, include_in_schema=False)
def trivia_page(request: Request):
    return templates.TemplateResponse(request=request, name='trivia_play.html',
                                      context={'sport': 'football', 'active_page': 'trivia'})


@app.get('/internal/trivia', response_class=HTMLResponse, include_in_schema=False,
         dependencies=[Depends(require_editor)])
def trivia_editor_page(request: Request):
    return templates.TemplateResponse(request=request, name='trivia.html',
                                      context={'sport': 'football', 'active_page': 'trivia'},
                                      headers={'Cache-Control': 'no-store'})


@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False
)
def home(request: Request):
    data = get_competition(39)
    season = data["seasons"][0] if data["seasons"] else None
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "sport": "football",
            "active_page": "home",
            "competition": data["competition"],
            "season": season,
            "season_label": f"{season}/{str(season + 1)[-2:]}" if season else "",
        }
    )


@app.get(
    "/matches/{fixture_id}",
    response_class=HTMLResponse,
    include_in_schema=False
)
def match_page(
    request: Request,
    fixture_id: int
):
    return templates.TemplateResponse(
        request=request,
        name="match.html",
        context={
            "sport": "football",
            "active_page": "scores",
            "fixture_id": fixture_id
        }
    )


@app.get(
    "/teams/{team_id}",
    response_class=HTMLResponse,
    include_in_schema=False
)
def team_page(
    request: Request,
    team_id: int,
    season: int = 2024
):
    return templates.TemplateResponse(
        request=request,
        name="team.html",
        context={
            "sport": "football",
            "active_page": "scores",
            "team_id": team_id,
            "season": season
        }
    )


@app.get(
    "/players/{player_id}",
    response_class=HTMLResponse,
    include_in_schema=False
)
def player_page(
    request: Request,
    player_id: int,
    season: int = 2024
):
    return templates.TemplateResponse(
        request=request,
        name="player.html",
        context={
            "sport": "football",
            "active_page": "players",
            "player_id": player_id,
            "season": season
        }
    )


@app.get(
    "/competitions/{league_id}",
    response_class=HTMLResponse,
    include_in_schema=False
)
def competition_page(
    request: Request,
    league_id: int,
    season: int | None = None
):
    return templates.TemplateResponse(
        request=request,
        name="competition.html",
        context={
            "sport": "football",
            "active_page": "scores",
            "league_id": league_id,
            "season": season
        }
    )


@app.get(
    "/admin",
    include_in_schema=False
)
def admin_dashboard():
    return FileResponse(
        WEB_DIR / "admin.html"
    )


@app.get("/api/health")
def health():
    return {
        "name": "Premier League Analytics API",
        "status": "running"
    }


@app.get("/api/search")
def global_search(
    q: str = Query(
        default="",
        max_length=100
    )
):
    search_term = q.strip()

    if len(search_term) < 2:
        return {
            "query": search_term,
            "count": 0,
            "results": [],
            "groups": {
                "competitions": [],
                "teams": [],
                "athletes": []
            }
        }

    search_pattern = (
        f"%{search_term}%"
    )

    starts_with = (
        f"{search_term}%"
    )

    competitions = fetch_all(
        """
        SELECT
            l.league_id,
            l.league_name,
            l.country_name,
            l.country_code,
            l.logo_url,

            COALESCE(
                l.country_flag_url,
                c.flag_url
            ) AS flag_url,

            (
                SELECT MAX(
                    s.season
                )
                FROM seasons s
                WHERE s.league_id = l.league_id
            ) AS season

        FROM leagues l

        LEFT JOIN countries c
            ON c.country_code = l.country_code

        WHERE
            l.league_name ILIKE %s
            OR l.country_name ILIKE %s

        ORDER BY
            CASE
                WHEN LOWER(
                    l.league_name
                ) = LOWER(%s)
                THEN 0

                WHEN l.league_name ILIKE %s
                THEN 1

                ELSE 2
            END,

            l.league_name

        LIMIT 5;
        """,
        (
            search_pattern,
            search_pattern,
            search_term,
            starts_with
        )
    )

    teams = fetch_all(
        """
        SELECT
            t.team_id,
            t.team_name,
            t.team_code,
            t.country_name,
            t.country_code,
            t.logo_url,
            c.flag_url,

            (
                SELECT MAX(ts.season)
                FROM team_season_statistics ts
                WHERE ts.team_id = t.team_id AND ts.league_id = 39
            ) AS season

        FROM teams t

        LEFT JOIN countries c
            ON c.country_code = t.country_code

        WHERE EXISTS (
            SELECT 1 FROM team_season_statistics ts
            WHERE ts.team_id = t.team_id AND ts.league_id = 39
        ) AND (
            t.team_name ILIKE %s
            OR t.team_code ILIKE %s
            OR t.country_name ILIKE %s
        )

        ORDER BY
            CASE
                WHEN LOWER(
                    t.team_name
                ) = LOWER(%s)
                THEN 0

                WHEN t.team_name ILIKE %s
                THEN 1

                ELSE 2
            END,

            t.team_name

        LIMIT 8;
        """,
        (
            search_pattern,
            search_pattern,
            search_pattern,
            search_term,
            starts_with
        )
    )

    athletes = fetch_all(
        SEASON_ROSTER_CTE + """
        , latest_player_seasons AS (
            SELECT
                player_id,
                MAX(season) AS season
            FROM season_roster
            GROUP BY player_id
        ),

        latest_player_teams AS (
            SELECT
                pss.player_id,
                pss.season,

                JSONB_AGG(
                    DISTINCT JSONB_BUILD_OBJECT(
                        'team_id',
                        t.team_id,
                        'team_name',
                        t.team_name,
                        'logo_url',
                        t.logo_url
                    )
                ) AS teams

            FROM season_roster pss

            JOIN latest_player_seasons latest
                ON latest.player_id = pss.player_id
                AND latest.season = pss.season

            JOIN teams t
                ON t.team_id = pss.team_id

            GROUP BY
                pss.player_id,
                pss.season
        )

        SELECT
            p.player_id,
            p.player_name,
            p.first_name,
            p.last_name,
            p.nationality,
            p.photo_url,

            c.country_code,
            c.flag_url,

            latest.season,

            COALESCE(
                latest.teams,
                '[]'::jsonb
            ) AS teams

        FROM players p

        LEFT JOIN latest_player_teams latest
            ON latest.player_id = p.player_id

        LEFT JOIN countries c
            ON LOWER(
                c.country_name
            ) = LOWER(
                p.nationality
            )

        WHERE
            p.player_name ILIKE %s
            OR p.first_name ILIKE %s
            OR p.last_name ILIKE %s
            OR p.nationality ILIKE %s
            OR CONCAT_WS(' ', p.first_name, p.last_name) ILIKE %s
            OR CONCAT_WS(' ', SPLIT_PART(p.first_name, ' ', 1), p.last_name) ILIKE %s
            OR CONCAT_WS(' ', SPLIT_PART(p.first_name, ' ', 1), REGEXP_REPLACE(p.player_name, '^[^.]+[.][[:space:]]*', '')) ILIKE %s

        ORDER BY
            CASE
                WHEN LOWER(
                    p.player_name
                ) = LOWER(%s)
                THEN 0

                WHEN LOWER(
                    p.first_name
                ) = LOWER(%s)
                THEN 1

                WHEN LOWER(
                    p.last_name
                ) = LOWER(%s)
                THEN 1

                WHEN p.player_name ILIKE %s
                THEN 2

                WHEN p.first_name ILIKE %s
                THEN 2

                WHEN p.last_name ILIKE %s
                THEN 2

                ELSE 3
            END,

            p.player_name

        LIMIT 12;
        """,
        (
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,
            search_term,
            search_term,
            search_term,
            starts_with,
            starts_with,
            starts_with
        )
    )

    competition_results = []

    for competition in competitions:
        season = competition[
            "season"
        ]

        if season is not None:
            url = (
                f"/competitions/"
                f"{competition['league_id']}"
                f"?season={season}"
            )

        else:
            url = (
                f"/competitions/"
                f"{competition['league_id']}"
            )

        competition_results.append(
            {
                "type": "competition",
                "sport": "football",
                "sport_name": "Football",
                "id": competition[
                    "league_id"
                ],
                "name": competition[
                    "league_name"
                ],
                "country_name": competition[
                    "country_name"
                ],
                "country_code": competition[
                    "country_code"
                ],
                "flag_url": competition[
                    "flag_url"
                ],
                "image_url": competition[
                    "logo_url"
                ],
                "season": season,
                "teams": [],
                "url": url
            }
        )

    team_results = []

    for team in teams:
        season = team[
            "season"
        ]

        if season is None:
            season = 2024

        team_results.append(
            {
                "type": "team",
                "sport": "football",
                "sport_name": "Football",
                "id": team[
                    "team_id"
                ],
                "name": team[
                    "team_name"
                ],
                "code": team[
                    "team_code"
                ],
                "country_name": team[
                    "country_name"
                ],
                "country_code": team[
                    "country_code"
                ],
                "flag_url": team[
                    "flag_url"
                ],
                "image_url": team[
                    "logo_url"
                ],
                "season": season,
                "teams": [],
                "url": (
                    f"/teams/"
                    f"{team['team_id']}"
                    f"?season={season}"
                )
            }
        )

    athlete_results = []

    for athlete in athletes:
        season = athlete[
            "season"
        ]

        if season is None:
            season = 2024

        athlete_results.append(
            {
                "type": "athlete",
                "sport": "football",
                "sport_name": "Football",
                "id": athlete[
                    "player_id"
                ],
                "name": athlete[
                    "player_name"
                ],
                "country_name": athlete[
                    "nationality"
                ],
                "country_code": athlete[
                    "country_code"
                ],
                "flag_url": athlete[
                    "flag_url"
                ],
                "image_url": athlete[
                    "photo_url"
                ],
                "season": season,
                "teams": athlete[
                    "teams"
                ],
                "url": (
                    f"/players/"
                    f"{athlete['player_id']}"
                    f"?season={season}"
                )
            }
        )

    results = (
        athlete_results
        + team_results
        + competition_results
    )

    return {
        "query": search_term,
        "count": len(results),
        "results": results,
        "groups": {
            "competitions": (
                competition_results
            ),
            "teams": (
                team_results
            ),
            "athletes": (
                athlete_results
            )
        }
    }


@app.get("/api/branding")
def get_branding():
    teams = fetch_all("""
        SELECT team_id AS id, team_name AS name, team_code AS code,
               country_name, country_code, logo_url
        FROM teams;
    """)
    competitions = fetch_all("""
        SELECT league_id AS id, league_name AS name,
               country_name, country_code, country_flag_url, logo_url
        FROM leagues;
    """)
    countries = fetch_all("""
        SELECT country_code AS code, country_name AS name, flag_url
        FROM countries;
    """)
    return {
        "sports": {"football": {
            "teams": {str(row["id"]): row for row in teams},
            "competitions": {str(row["id"]): row for row in competitions},
        }},
        "countries": {row["code"]: row for row in countries},
    }


@app.get("/api/competitions/{league_id}")
def get_competition(
    league_id: int
):
    competition = fetch_one(
        """
        SELECT
            league_id,
            league_name,
            country_name,
            country_code,
            country_flag_url,
            logo_url
        FROM leagues
        WHERE league_id = %s;
        """,
        (
            league_id,
        )
    )

    if competition is None:
        raise HTTPException(
            status_code=404,
            detail="Competition not found"
        )

    season_rows = fetch_all(
        """
        SELECT
            season
        FROM seasons
        WHERE league_id = %s
        ORDER BY season DESC;
        """,
        (
            league_id,
        )
    )

    seasons = [
        row["season"]
        for row in season_rows
    ]

    return {
        "competition": competition,
        "seasons": seasons
    }


@app.get("/api/data/seasons")
def get_season_data():
    rows = fetch_all(
        """
        SELECT
            league_id,
            league_name,
            season,
            teams,
            total_fixtures,
            finished_fixtures,
            fixtures_with_complete_stats,
            fixtures_with_partial_stats,
            fixtures_without_stats,
            statistics_coverage_percentage,
            first_match_date,
            last_match_date
        FROM season_data_summary
        ORDER BY season;
        """
    )

    return {
        "count": len(rows),
        "seasons": rows
    }


@app.get("/api/data/imports")
def get_imports(
    limit: int = Query(
        default=20,
        ge=1,
        le=100
    )
):
    rows = fetch_all(
        """
        SELECT
            import_run_id,
            import_type,
            league_id,
            season,
            started_at,
            finished_at,
            status,
            rows_received,
            rows_inserted,
            api_requests,
            error_message
        FROM import_runs
        ORDER BY started_at DESC
        LIMIT %s;
        """,
        (
            limit,
        )
    )

    return {
        "count": len(rows),
        "imports": rows
    }


@app.get("/api/data/quality")
def get_data_quality():
    checks = []

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixtures f

        LEFT JOIN teams home
            ON f.home_team_id = home.team_id

        LEFT JOIN teams away
            ON f.away_team_id = away.team_id

        WHERE home.team_id IS NULL
           OR away.team_id IS NULL;
        """
    )

    checks.append(
        {
            "name": "fixtures_without_valid_teams",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixtures
        WHERE status = 'FT'
          AND (
              home_goals IS NULL
              OR away_goals IS NULL
          );
        """
    )

    checks.append(
        {
            "name": "finished_fixtures_without_goals",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixture_data_status
        WHERE data_status = 'partial';
        """
    )

    checks.append(
        {
            "name": "fixtures_with_partial_statistics",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixture_statistics
        WHERE ball_possession < 0
           OR ball_possession > 100;
        """
    )

    checks.append(
        {
            "name": "invalid_possession_values",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixture_statistics
        WHERE passes_percentage < 0
           OR passes_percentage > 100;
        """
    )

    checks.append(
        {
            "name": "invalid_pass_percentage_values",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
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

    checks.append(
        {
            "name": "negative_statistics_values",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixture_statistics
        WHERE passes_accurate > total_passes;
        """
    )

    checks.append(
        {
            "name": "accurate_passes_greater_than_total",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM fixture_statistics
        WHERE shots_on_goal > total_shots;
        """
    )

    checks.append(
        {
            "name": "shots_on_goal_greater_than_total",
            "issues": row["count"]
        }
    )

    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM import_runs
        WHERE status = 'running';
        """
    )

    checks.append(
        {
            "name": "unfinished_import_runs",
            "issues": row["count"]
        }
    )

    total_issues = sum(
        check["issues"]
        for check in checks
    )

    return {
        "status": (
            "ok"
            if total_issues == 0
            else "issues_found"
        ),
        "total_issues": total_issues,
        "checks": checks
    }


@app.get("/api/standings")
def get_standings(
    season: int,
    league_id: int = 39
):
    rows = fetch_all(
        """
        SELECT
            ls.league_id,
            ls.season,
            ls.position,
            ls.team_id,
            ls.team_name,
            t.team_code,
            t.country_name,
            t.country_code,
            t.logo_url AS team_logo_url,
            ls.played,
            ls.wins,
            ls.draws,
            ls.losses,
            ls.goals_for,
            ls.goals_against,
            ls.goal_difference,
            ls.points
        FROM league_standings ls

        LEFT JOIN teams t
            ON t.team_id = ls.team_id

        WHERE ls.league_id = %s
          AND ls.season = %s
        ORDER BY ls.position;
        """,
        (
            league_id,
            season
        )
    )

    return {
        "league_id": league_id,
        "season": season,
        "count": len(rows),
        "standings": rows
    }


@app.get("/api/teams")
def get_teams():
    rows = fetch_all(
        """
        SELECT
            t.team_id,
            t.team_name,

            COUNT(
                DISTINCT f.fixture_id
            ) AS fixtures

        FROM teams t

        LEFT JOIN fixtures f
            ON t.team_id = f.home_team_id
            OR t.team_id = f.away_team_id

        GROUP BY
            t.team_id,
            t.team_name

        ORDER BY
            t.team_name;
        """
    )

    return {
        "count": len(rows),
        "teams": rows
    }


@app.get("/api/teams/{team_id}")
def get_team_detail(
    team_id: int,
    season: int,
    league_id: int = 39
):
    team = fetch_one(
        """
        SELECT
            league_id,
            season,
            team_id,
            team_name,
            (
                SELECT t.team_code
                FROM teams t
                WHERE t.team_id = team_season_statistics.team_id
            ) AS team_code,
            (
                SELECT t.country_name
                FROM teams t
                WHERE t.team_id = team_season_statistics.team_id
            ) AS country_name,
            (
                SELECT t.country_code
                FROM teams t
                WHERE t.team_id = team_season_statistics.team_id
            ) AS country_code,
            (
                SELECT t.logo_url
                FROM teams t
                WHERE t.team_id = team_season_statistics.team_id
            ) AS team_logo_url,
            league_position,
            league_team_count,
            matches_played,
            matches_with_stats,
            wins,
            draws,
            losses,
            goals_for,
            goals_against,
            goal_difference,
            points,
            avg_ball_possession,
            ball_possession_rank,
            season_total_shots,
            avg_total_shots,
            total_shots_rank,
            season_total_shots_on_goal,
            avg_shots_on_goal,
            shots_on_goal_rank,
            season_total_shots_off_goal,
            avg_shots_off_goal,
            shots_off_goal_rank,
            season_total_blocked_shots,
            avg_blocked_shots,
            blocked_shots_rank,
            season_total_shots_inside_box,
            avg_shots_inside_box,
            shots_inside_box_rank,
            season_total_shots_outside_box,
            avg_shots_outside_box,
            shots_outside_box_rank,
            season_total_corner_kicks,
            avg_corner_kicks,
            corner_kicks_rank,
            season_total_fouls,
            avg_fouls,
            fouls_rank,
            season_total_offsides,
            avg_offsides,
            offsides_rank,
            total_yellow_cards,
            avg_yellow_cards,
            yellow_cards_rank,
            total_red_cards,
            avg_red_cards,
            red_cards_rank,
            season_total_goalkeeper_saves,
            avg_goalkeeper_saves,
            goalkeeper_saves_rank,
            season_total_passes,
            avg_total_passes,
            total_passes_rank,
            season_total_passes_accurate,
            avg_passes_accurate,
            passes_accurate_rank,
            avg_passes_percentage,
            passes_percentage_rank
        FROM team_season_statistics
        WHERE league_id = %s
          AND season = %s
          AND team_id = %s;
        """,
        (
            league_id,
            season,
            team_id
        )
    )

    if team is None:
        raise HTTPException(
            status_code=404,
            detail="Team not found for this season"
        )

    recent_matches = fetch_all(
        """
        SELECT
            fds.fixture_id,
            fds.league_id,
            fds.season,
            fds.match_date,
            f.home_team_id,
            fds.home_team,
            home.logo_url AS home_team_logo_url,
            f.away_team_id,
            fds.away_team,
            away.logo_url AS away_team_logo_url,
            fds.status,
            fds.home_goals,
            fds.away_goals,
            fds.statistics_rows,
            fds.data_status
        FROM fixture_data_status fds

        JOIN fixtures f
            ON fds.fixture_id = f.fixture_id

        LEFT JOIN teams home
            ON home.team_id = f.home_team_id

        LEFT JOIN teams away
            ON away.team_id = f.away_team_id

        WHERE fds.league_id = %s
          AND fds.season <= %s
          AND fds.status IN ('FT', 'AET', 'PEN')
          AND fds.match_date <= CURRENT_TIMESTAMP
          AND (
              f.home_team_id = %s
              OR f.away_team_id = %s
          )

        ORDER BY fds.match_date DESC, fds.fixture_id DESC
        LIMIT 10;
        """,
        (
            league_id,
            season,
            team_id,
            team_id
        )
    )

    upcoming_matches = fetch_all(
        """
        SELECT f.fixture_id, f.league_id, f.season, f.match_date, f.status,
               f.home_team_id, home.team_name AS home_team,
               home.logo_url AS home_team_logo_url,
               f.away_team_id, away.team_name AS away_team,
               away.logo_url AS away_team_logo_url
        FROM fixtures f
        LEFT JOIN teams home ON home.team_id = f.home_team_id
        LEFT JOIN teams away ON away.team_id = f.away_team_id
        WHERE f.league_id = %s AND f.season = %s
          AND (f.home_team_id = %s OR f.away_team_id = %s)
          AND f.status IN ('NS', 'TBD')
          AND f.match_date >= CURRENT_TIMESTAMP
        ORDER BY f.match_date, f.fixture_id;
        """,
        (league_id, season, team_id, team_id)
    )

    return {
        "team": team,
        "recent_matches": recent_matches,
        "upcoming_matches": upcoming_matches
    }


@app.get("/api/teams/{team_id}/players")
def get_team_players(
    team_id: int,
    season: int,
    league_id: int = 39
):
    team = fetch_one(
        """
        SELECT
            team_id,
            team_name
        FROM teams
        WHERE team_id = %s;
        """,
        (
            team_id,
        )
    )

    if team is None:
        raise HTTPException(
            status_code=404,
            detail="Team not found"
        )

    players = fetch_all(
        SEASON_ROSTER_CTE + """
        SELECT
            p.player_id,
            p.player_name,
            p.first_name,
            p.last_name,
            p.birth_date,
            p.nationality,
            p.height_cm,
            p.weight_kg,

            COALESCE(
                p.photo_url,
                sm.photo_url
            ) AS photo_url,

            COALESCE(
                pss.squad_number,
                sm.squad_number
            ) AS squad_number,

            COALESCE(
                pss.position,
                sm.position
            ) AS position,

            sm.age,
            (pss.player_id IS NOT NULL) AS statistics_available,
            pss.appearances,
            pss.lineups,
            pss.minutes,
            pss.rating,
            pss.goals_total,
            pss.assists,
            pss.shots_total,
            pss.shots_on_goal,
            pss.passes_total,
            pss.key_passes,
            pss.pass_accuracy,
            pss.tackles_total,
            pss.blocks,
            pss.interceptions,
            pss.duels_total,
            pss.duels_won,
            pss.yellow_cards,
            pss.red_cards
        FROM season_roster r
        JOIN players p ON p.player_id = r.player_id
        LEFT JOIN player_season_statistics pss
            ON pss.player_id = r.player_id AND pss.team_id = r.team_id
            AND pss.league_id = r.league_id AND pss.season = r.season
        LEFT JOIN squad_memberships sm
            ON sm.player_id = r.player_id AND sm.team_id = r.team_id
            AND sm.league_id = r.league_id AND sm.season = r.season
        WHERE r.league_id = %s AND r.season = %s AND r.team_id = %s

        ORDER BY
            CASE
                WHEN COALESCE(
                    pss.position,
                    sm.position
                ) = 'Goalkeeper'
                THEN 1

                WHEN COALESCE(
                    pss.position,
                    sm.position
                ) = 'Defender'
                THEN 2

                WHEN COALESCE(
                    pss.position,
                    sm.position
                ) = 'Midfielder'
                THEN 3

                WHEN COALESCE(
                    pss.position,
                    sm.position
                ) = 'Attacker'
                THEN 4

                ELSE 5
            END,

            pss.minutes DESC NULLS LAST,
            p.player_name;
        """,
        (
            league_id,
            season,
            team_id
        )
    )

    return {
        "league_id": league_id,
        "season": season,
        "team": team,
        "count": len(players),
        "players": players
    }


@app.get("/api/competitions/{league_id}/leaders")
def get_competition_leaders(
    league_id: int,
    season: int,
    leader_type: str = Query(
        default="scorers",
        alias="type",
        pattern="^(scorers|rating|goalkeepers)$"
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100
    ),
    min_minutes: int = Query(
        default=600,
        ge=0,
        le=10000
    )
):
    base_query = """
        WITH player_totals AS (
            SELECT
                pss.player_id,
                p.player_name,
                p.photo_url,
                p.nationality,

                STRING_AGG(
                    DISTINCT t.team_name,
                    ', '
                    ORDER BY t.team_name
                ) AS teams,

                MAX(pss.position) AS position,

                SUM(
                    COALESCE(
                        pss.appearances,
                        0
                    )
                ) AS appearances,

                SUM(
                    COALESCE(
                        pss.minutes,
                        0
                    )
                ) AS minutes,

                SUM(
                    COALESCE(
                        pss.goals_total,
                        0
                    )
                ) AS goals,

                SUM(
                    COALESCE(
                        pss.assists,
                        0
                    )
                ) AS assists,

                SUM(
                    COALESCE(
                        pss.saves,
                        0
                    )
                ) AS saves,

                SUM(
                    COALESCE(
                        pss.goals_conceded,
                        0
                    )
                ) AS goals_conceded,

                ROUND(
                    (
                        SUM(
                            CASE
                                WHEN pss.rating IS NOT NULL
                                THEN
                                    pss.rating
                                    * GREATEST(
                                        COALESCE(
                                            pss.minutes,
                                            0
                                        ),
                                        1
                                    )
                                ELSE 0
                            END
                        )
                        /
                        NULLIF(
                            SUM(
                                CASE
                                    WHEN pss.rating IS NOT NULL
                                    THEN GREATEST(
                                        COALESCE(
                                            pss.minutes,
                                            0
                                        ),
                                        1
                                    )
                                    ELSE 0
                                END
                            ),
                            0
                        )
                    )::numeric,
                    2
                ) AS provider_rating

            FROM player_season_statistics pss

            JOIN players p
                ON p.player_id = pss.player_id

            JOIN teams t
                ON t.team_id = pss.team_id

            WHERE
                pss.league_id = %s
                AND pss.season = %s
                AND COALESCE(
                    pss.appearances,
                    0
                ) > 0

            GROUP BY
                pss.player_id,
                p.player_name,
                p.photo_url,
                p.nationality
        )

        SELECT
            player_id,
            player_name,
            photo_url,
            nationality,
            teams,
            position,
            appearances,
            minutes,
            goals,
            assists,
            goals + assists AS goal_contributions,
            saves,
            goals_conceded,
            provider_rating,

            CASE
                WHEN minutes > 0
                THEN ROUND(
                    (
                        saves::numeric
                        * 90
                        / minutes
                    ),
                    2
                )
                ELSE NULL
            END AS saves_per_90

        FROM player_totals
    """

    params = [
        league_id,
        season
    ]

    if leader_type == "scorers":
        base_query += """
            ORDER BY
                goals DESC,
                assists DESC,
                minutes ASC,
                player_name
            LIMIT %s;
        """

        params.append(
            limit
        )

    elif leader_type == "rating":
        base_query += """
            WHERE
                minutes >= %s
                AND provider_rating IS NOT NULL

            ORDER BY
                provider_rating DESC,
                minutes DESC,
                player_name
            LIMIT %s;
        """

        params.extend(
            [
                min_minutes,
                limit
            ]
        )

    else:
        base_query += """
            WHERE
                LOWER(
                    COALESCE(
                        position,
                        ''
                    )
                ) = 'goalkeeper'
                AND minutes > 0

            ORDER BY
                provider_rating DESC NULLS LAST,
                saves DESC,
                minutes DESC,
                player_name
            LIMIT %s;
        """

        params.append(
            limit
        )

    rows = fetch_all(
        base_query,
        tuple(params)
    )

    leaders = []

    for index, row in enumerate(
        rows,
        start=1
    ):
        leaders.append(
            {
                **row,
                "rank": index
            }
        )

    return {
        "league_id": league_id,
        "season": season,
        "type": leader_type,
        "rating_source": "provider",
        "min_minutes": (
            min_minutes
            if leader_type == "rating"
            else None
        ),
        "count": len(leaders),
        "leaders": leaders
    }


@app.get("/api/players")
def get_players(
    season: int,
    league_id: int = 39,
    search: str | None = None,
    limit: int = Query(
        default=50,
        ge=1,
        le=200
    )
):
    query = SEASON_ROSTER_CTE + """
        SELECT
            p.player_id,
            p.player_name,
            p.nationality,
            p.birth_date,

            MAX(
                COALESCE(
                    p.photo_url,
                    sm.photo_url
                )
            ) AS photo_url,

            STRING_AGG(
                DISTINCT t.team_name,
                ', '
                ORDER BY t.team_name
            ) AS teams,

            MAX(
                COALESCE(
                    pss.position,
                    sm.position
                )
            ) AS position,

            SUM(pss.appearances) AS appearances,
            SUM(pss.minutes) AS minutes,
            SUM(pss.goals_total) AS goals,
            SUM(pss.assists) AS assists
        FROM season_roster r
        JOIN players p ON p.player_id = r.player_id
        JOIN teams t ON t.team_id = r.team_id
        LEFT JOIN player_season_statistics pss
            ON pss.player_id = r.player_id AND pss.team_id = r.team_id
            AND pss.league_id = r.league_id AND pss.season = r.season
        LEFT JOIN squad_memberships sm
            ON sm.player_id = r.player_id AND sm.team_id = r.team_id
            AND sm.league_id = r.league_id AND sm.season = r.season
        WHERE r.league_id = %s AND r.season = %s
    """

    params = [
        league_id,
        season
    ]

    search_term = None

    if search:
        search_term = search.strip()

        if search_term:
            search_pattern = (
                f"%{search_term}%"
            )

            query += """
                AND (
                    p.player_name ILIKE %s
                    OR p.first_name ILIKE %s
                    OR p.last_name ILIKE %s
                )
            """

            params.extend(
                [
                    search_pattern,
                    search_pattern,
                    search_pattern
                ]
            )

    query += """
        GROUP BY
            p.player_id,
            p.player_name,
            p.first_name,
            p.last_name,
            p.nationality,
            p.birth_date
    """

    if search_term:
        starts_with = (
            f"{search_term}%"
        )

        query += """
            ORDER BY
                CASE
                    WHEN LOWER(
                        p.player_name
                    ) = LOWER(%s)
                    THEN 0

                    WHEN LOWER(
                        p.first_name
                    ) = LOWER(%s)
                    THEN 1

                    WHEN LOWER(
                        p.last_name
                    ) = LOWER(%s)
                    THEN 1

                    WHEN p.player_name ILIKE %s
                    THEN 2

                    WHEN p.first_name ILIKE %s
                    THEN 2

                    WHEN p.last_name ILIKE %s
                    THEN 2

                    ELSE 3
                END,

                p.player_name,

                SUM(
                    COALESCE(
                        pss.minutes,
                        0
                    )
                ) DESC
        """

        params.extend(
            [
                search_term,
                search_term,
                search_term,
                starts_with,
                starts_with,
                starts_with
            ]
        )

    else:
        query += """
            ORDER BY
                SUM(
                    COALESCE(
                        pss.minutes,
                        0
                    )
                ) DESC,

                p.player_name
        """

    query += """
        LIMIT %s;
    """

    params.append(
        limit
    )

    players = fetch_all(
        query,
        tuple(params)
    )

    return {
        "league_id": league_id,
        "season": season,
        "search": search_term,
        "count": len(players),
        "players": players
    }


@app.get("/api/players/{player_id}")
def get_player_detail(
    player_id: int,
    season: int,
    league_id: int = 39
):
    player = fetch_one(
        """
        SELECT
            player_id,
            player_name,
            first_name,
            last_name,
            birth_date,
            nationality,
            height_cm,
            weight_kg,
            photo_url
        FROM players
        WHERE player_id = %s;
        """,
        (
            player_id,
        )
    )

    if player is None:
        raise HTTPException(
            status_code=404,
            detail="Player not found"
        )

    statistics = fetch_all(
        SEASON_ROSTER_CTE + """
        SELECT
            r.league_id,
            r.season,
            r.team_id,
            t.team_name,
            (pss.player_id IS NOT NULL) AS statistics_available,

            COALESCE(
                pss.squad_number,
                sm.squad_number
            ) AS squad_number,

            COALESCE(
                pss.position,
                sm.position
            ) AS position,

            pss.appearances,
            pss.lineups,
            pss.minutes,
            pss.rating,
            pss.captain,
            pss.substitutes_in,
            pss.substitutes_out,
            pss.substitutes_bench,
            pss.shots_total,
            pss.shots_on_goal,
            pss.goals_total,
            pss.goals_conceded,
            pss.assists,
            pss.saves,
            pss.passes_total,
            pss.key_passes,
            pss.pass_accuracy,
            pss.tackles_total,
            pss.blocks,
            pss.interceptions,
            pss.duels_total,
            pss.duels_won,
            pss.dribbles_attempts,
            pss.dribbles_success,
            pss.dribbled_past,
            pss.fouls_drawn,
            pss.fouls_committed,
            pss.yellow_cards,
            pss.yellow_red_cards,
            pss.red_cards,
            pss.penalties_won,
            pss.penalties_committed,
            pss.penalties_scored,
            pss.penalties_missed,
            pss.penalties_saved
        FROM season_roster r
        JOIN teams t ON t.team_id = r.team_id
        LEFT JOIN player_season_statistics pss
            ON pss.player_id = r.player_id AND pss.team_id = r.team_id
            AND pss.league_id = r.league_id AND pss.season = r.season
        LEFT JOIN squad_memberships sm
            ON sm.player_id = r.player_id AND sm.team_id = r.team_id
            AND sm.league_id = r.league_id AND sm.season = r.season
        WHERE r.player_id = %s AND r.league_id = %s AND r.season = %s

        ORDER BY
            pss.minutes DESC NULLS LAST,
            t.team_name;
        """,
        (
            player_id,
            league_id,
            season
        )
    )

    summary = fetch_one(
        """
        SELECT
            COUNT(*) AS team_records,

            COALESCE(
                SUM(
                    COALESCE(
                        appearances,
                        0
                    )
                ),
                0
            ) AS appearances,

            COALESCE(
                SUM(
                    COALESCE(
                        lineups,
                        0
                    )
                ),
                0
            ) AS lineups,

            COALESCE(
                SUM(
                    COALESCE(
                        minutes,
                        0
                    )
                ),
                0
            ) AS minutes,

            COALESCE(
                SUM(
                    COALESCE(
                        goals_total,
                        0
                    )
                ),
                0
            ) AS goals,

            COALESCE(
                SUM(
                    COALESCE(
                        assists,
                        0
                    )
                ),
                0
            ) AS assists,

            COALESCE(
                SUM(
                    COALESCE(
                        shots_total,
                        0
                    )
                ),
                0
            ) AS shots,

            COALESCE(
                SUM(
                    COALESCE(
                        shots_on_goal,
                        0
                    )
                ),
                0
            ) AS shots_on_goal,

            COALESCE(
                SUM(
                    COALESCE(
                        key_passes,
                        0
                    )
                ),
                0
            ) AS key_passes,

            COALESCE(
                SUM(
                    COALESCE(
                        tackles_total,
                        0
                    )
                ),
                0
            ) AS tackles,

            COALESCE(
                SUM(
                    COALESCE(
                        interceptions,
                        0
                    )
                ),
                0
            ) AS interceptions,

            COALESCE(
                SUM(
                    COALESCE(
                        duels_total,
                        0
                    )
                ),
                0
            ) AS duels,

            COALESCE(
                SUM(
                    COALESCE(
                        duels_won,
                        0
                    )
                ),
                0
            ) AS duels_won,

            COALESCE(
                SUM(
                    COALESCE(
                        yellow_cards,
                        0
                    )
                ),
                0
            ) AS yellow_cards,

            COALESCE(
                SUM(
                    COALESCE(
                        red_cards,
                        0
                    )
                ),
                0
            ) AS red_cards
        FROM player_season_statistics
        WHERE player_id = %s
          AND league_id = %s
          AND season = %s;
        """,
        (
            player_id,
            league_id,
            season
        )
    )

    return {
        "player": player,
        "league_id": league_id,
        "season": season,
        "summary": summary,
        "statistics": statistics
    }


@app.get("/api/fixtures/{fixture_id}")
def get_fixture_detail(
    fixture_id: int
):
    fixture = fetch_one(
        """
        SELECT
            f.fixture_id,
            f.league_id,
            f.season,
            f.match_date,
            f.status,
            f.home_team_id,
            home.team_name AS home_team,
            home.logo_url AS home_team_logo_url,
            f.away_team_id,
            away.team_name AS away_team,
            away.logo_url AS away_team_logo_url,
            l.league_name,
            l.logo_url AS league_logo_url,
            l.country_name AS league_country_name,
            l.country_code AS league_country_code,
            l.country_flag_url AS league_country_flag_url,
            f.home_goals,
            f.away_goals
        FROM fixtures f

        JOIN teams home
            ON f.home_team_id = home.team_id

        JOIN teams away
            ON f.away_team_id = away.team_id

        LEFT JOIN leagues l
            ON l.league_id = f.league_id

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

    statistics = fetch_all(
        """
        SELECT
            s.team_id,
            t.team_name,
            t.logo_url AS team_logo_url,
            s.shots_on_goal,
            s.shots_off_goal,
            s.total_shots,
            s.blocked_shots,
            s.shots_inside_box,
            s.shots_outside_box,
            s.fouls,
            s.corner_kicks,
            s.offsides,
            s.ball_possession,
            s.yellow_cards,
            s.red_cards,
            s.goalkeeper_saves,
            s.total_passes,
            s.passes_accurate,
            s.passes_percentage
        FROM fixture_statistics s

        JOIN teams t
            ON s.team_id = t.team_id

        WHERE s.fixture_id = %s

        ORDER BY
            CASE
                WHEN s.team_id = %s
                THEN 0
                ELSE 1
            END;
        """,
        (
            fixture_id,
            fixture["home_team_id"]
        )
    )

    return {
        "fixture": fixture,
        "statistics": statistics,
        "statistics_count": len(statistics)
    }


@app.get("/api/fixtures")
def get_fixtures(
    league_id: int = 39,
    season: int | None = None,
    status: str | None = None,
    data_status: str | None = None,
    team: str | None = None,
    limit: int = Query(
        default=30,
        ge=1,
        le=500
    )
):
    query = """
        SELECT
            fds.fixture_id,
            fds.league_id,
            fds.season,
            fds.match_date,
            f.home_team_id,
            fds.home_team,
            home.logo_url AS home_team_logo_url,
            f.away_team_id,
            fds.away_team,
            away.logo_url AS away_team_logo_url,
            fds.status,
            fds.home_goals,
            fds.away_goals,
            fds.statistics_rows,
            fds.data_status
        FROM fixture_data_status fds

        JOIN fixtures f
            ON f.fixture_id = fds.fixture_id

        LEFT JOIN teams home
            ON home.team_id = f.home_team_id

        LEFT JOIN teams away
            ON away.team_id = f.away_team_id

        WHERE fds.league_id = %s
    """

    params = [
        league_id
    ]

    if season is not None:
        query += """
            AND fds.season = %s
        """

        params.append(
            season
        )

    if status is not None:
        query += """
            AND fds.status = %s
        """

        params.append(
            status
        )

    if data_status is not None:
        query += """
            AND fds.data_status = %s
        """

        params.append(
            data_status
        )

    if team is not None:
        query += """
            AND (
                fds.home_team = %s
                OR fds.away_team = %s
            )
        """

        params.extend(
            [
                team,
                team
            ]
        )

    query += """
        ORDER BY
            fds.match_date DESC

        LIMIT %s;
    """

    params.append(
        limit
    )

    rows = fetch_all(
        query,
        tuple(params)
    )

    return {
        "league_id": league_id,
        "count": len(rows),
        "fixtures": rows
    }
