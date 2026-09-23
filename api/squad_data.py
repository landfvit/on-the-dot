SEASON_ROSTER_CTE = """
WITH season_roster AS (
    SELECT league_id, season, team_id, player_id FROM squad_memberships
    UNION
    SELECT league_id, season, team_id, player_id FROM player_season_statistics
)
"""
