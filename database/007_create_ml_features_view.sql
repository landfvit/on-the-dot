CREATE OR REPLACE VIEW ml_match_features AS

WITH team_matches AS (

    SELECT
        fixture_id,
        league_id,
        season,
        match_date,
        home_team_id AS team_id,

        CASE
            WHEN home_goals > away_goals THEN 3
            WHEN home_goals = away_goals THEN 1
            ELSE 0
        END AS points,

        home_goals AS goals_scored,
        away_goals AS goals_conceded

    FROM fixtures
    WHERE status = 'FT'

    UNION ALL

    SELECT
        fixture_id,
        league_id,
        season,
        match_date,
        away_team_id AS team_id,

        CASE
            WHEN away_goals > home_goals THEN 3
            WHEN away_goals = home_goals THEN 1
            ELSE 0
        END AS points,

        away_goals AS goals_scored,
        home_goals AS goals_conceded

    FROM fixtures
    WHERE status = 'FT'
),

team_features AS (

    SELECT
        fixture_id,
        league_id,
        season,
        team_id,
        match_date,

        SUM(points) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS points_last_5,

        SUM(goals_scored) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS goals_scored_last_5,

        SUM(goals_conceded) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS goals_conceded_last_5,

        COUNT(*) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS matches_last_5,

        SUM(points) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS season_points,

        COUNT(*) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS season_matches_played,

        SUM(goals_scored) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS season_goals_scored,

        SUM(goals_conceded) OVER (
            PARTITION BY league_id, season, team_id
            ORDER BY match_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS season_goals_conceded

    FROM team_matches
),

season_teams AS (

    SELECT DISTINCT
        league_id,
        season,
        home_team_id AS team_id
    FROM fixtures

    UNION

    SELECT DISTINCT
        league_id,
        season,
        away_team_id AS team_id
    FROM fixtures
),

standings_before_fixture AS (

    SELECT
        f.fixture_id,
        st.team_id,

        COALESCE(
            SUM(
                CASE
                    WHEN previous.home_team_id = st.team_id
                         AND previous.home_goals > previous.away_goals
                        THEN 3

                    WHEN previous.away_team_id = st.team_id
                         AND previous.away_goals > previous.home_goals
                        THEN 3

                    WHEN previous.home_goals = previous.away_goals
                        THEN 1

                    ELSE 0
                END
            ),
            0
        ) AS points,

        COALESCE(
            SUM(
                CASE
                    WHEN previous.home_team_id = st.team_id
                        THEN previous.home_goals

                    WHEN previous.away_team_id = st.team_id
                        THEN previous.away_goals

                    ELSE 0
                END
            ),
            0
        ) AS goals_scored,

        COALESCE(
            SUM(
                CASE
                    WHEN previous.home_team_id = st.team_id
                        THEN previous.away_goals

                    WHEN previous.away_team_id = st.team_id
                        THEN previous.home_goals

                    ELSE 0
                END
            ),
            0
        ) AS goals_conceded

    FROM fixtures f

    JOIN season_teams st
        ON f.league_id = st.league_id
        AND f.season = st.season

    LEFT JOIN fixtures previous
        ON previous.league_id = f.league_id
        AND previous.season = f.season
        AND previous.status = 'FT'
        AND previous.match_date < f.match_date
        AND (
            previous.home_team_id = st.team_id
            OR previous.away_team_id = st.team_id
        )

    WHERE f.status = 'FT'

    GROUP BY
        f.fixture_id,
        st.team_id
),

league_positions AS (

    SELECT
        fixture_id,
        team_id,

        RANK() OVER (
            PARTITION BY fixture_id
            ORDER BY
                points DESC,
                (goals_scored - goals_conceded) DESC,
                goals_scored DESC
        ) AS league_position

    FROM standings_before_fixture
)

SELECT
    f.fixture_id,
    f.match_date,

    f.home_team_id,
    f.away_team_id,

    home.team_name AS home_team,
    away.team_name AS away_team,

    home_features.points_last_5 AS home_points_last_5,
    away_features.points_last_5 AS away_points_last_5,

    CASE
        WHEN f.home_goals > f.away_goals THEN 'H'
        WHEN f.home_goals = f.away_goals THEN 'D'
        ELSE 'A'
    END AS result,

    home_features.goals_scored_last_5
        AS home_goals_scored_last_5,

    away_features.goals_scored_last_5
        AS away_goals_scored_last_5,

    home_features.goals_conceded_last_5
        AS home_goals_conceded_last_5,

    away_features.goals_conceded_last_5
        AS away_goals_conceded_last_5,

    home_features.season_points
        AS home_season_points,

    away_features.season_points
        AS away_season_points,

    home_features.season_matches_played
        AS home_matches_played,

    away_features.season_matches_played
        AS away_matches_played,

    ROUND(
        home_features.season_points::numeric
        / NULLIF(home_features.season_matches_played, 0),
        3
    ) AS home_points_per_game,

    ROUND(
        away_features.season_points::numeric
        / NULLIF(away_features.season_matches_played, 0),
        3
    ) AS away_points_per_game,

    home_features.season_goals_scored
        - home_features.season_goals_conceded
        AS home_goal_difference,

    away_features.season_goals_scored
        - away_features.season_goals_conceded
        AS away_goal_difference,

    home_position.league_position
        AS home_league_position,

    away_position.league_position
        AS away_league_position

FROM fixtures f

JOIN teams home
    ON f.home_team_id = home.team_id

JOIN teams away
    ON f.away_team_id = away.team_id

JOIN team_features home_features
    ON f.fixture_id = home_features.fixture_id
    AND f.home_team_id = home_features.team_id

JOIN team_features away_features
    ON f.fixture_id = away_features.fixture_id
    AND f.away_team_id = away_features.team_id

JOIN league_positions home_position
    ON f.fixture_id = home_position.fixture_id
    AND f.home_team_id = home_position.team_id

JOIN league_positions away_position
    ON f.fixture_id = away_position.fixture_id
    AND f.away_team_id = away_position.team_id

WHERE f.status = 'FT'
  AND home_features.matches_last_5 = 5
  AND away_features.matches_last_5 = 5;