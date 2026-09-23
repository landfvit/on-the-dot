CREATE OR REPLACE VIEW league_standings AS

WITH team_matches AS (

    SELECT
        f.league_id,
        f.season,
        f.fixture_id,
        f.home_team_id AS team_id,

        f.home_goals AS goals_for,
        f.away_goals AS goals_against,

        CASE
            WHEN f.home_goals > f.away_goals THEN 1
            ELSE 0
        END AS win,

        CASE
            WHEN f.home_goals = f.away_goals THEN 1
            ELSE 0
        END AS draw,

        CASE
            WHEN f.home_goals < f.away_goals THEN 1
            ELSE 0
        END AS loss

    FROM fixtures f

    WHERE f.status = 'FT'
      AND f.home_goals IS NOT NULL
      AND f.away_goals IS NOT NULL


    UNION ALL


    SELECT
        f.league_id,
        f.season,
        f.fixture_id,
        f.away_team_id AS team_id,

        f.away_goals AS goals_for,
        f.home_goals AS goals_against,

        CASE
            WHEN f.away_goals > f.home_goals THEN 1
            ELSE 0
        END AS win,

        CASE
            WHEN f.away_goals = f.home_goals THEN 1
            ELSE 0
        END AS draw,

        CASE
            WHEN f.away_goals < f.home_goals THEN 1
            ELSE 0
        END AS loss

    FROM fixtures f

    WHERE f.status = 'FT'
      AND f.home_goals IS NOT NULL
      AND f.away_goals IS NOT NULL

),


team_totals AS (

    SELECT
        tm.league_id,
        tm.season,
        tm.team_id,

        COUNT(*) AS played,

        SUM(tm.win) AS wins,
        SUM(tm.draw) AS draws,
        SUM(tm.loss) AS losses,

        SUM(tm.goals_for) AS goals_for,
        SUM(tm.goals_against) AS goals_against,

        SUM(tm.goals_for)
            - SUM(tm.goals_against)
            AS goal_difference,

        SUM(
            tm.win * 3
            + tm.draw
        ) AS points

    FROM team_matches tm

    GROUP BY
        tm.league_id,
        tm.season,
        tm.team_id

),


ranked_standings AS (

    SELECT
        tt.league_id,
        tt.season,
        tt.team_id,
        t.team_name,

        tt.played,
        tt.wins,
        tt.draws,
        tt.losses,

        tt.goals_for,
        tt.goals_against,
        tt.goal_difference,
        tt.points,

        ROW_NUMBER() OVER (
            PARTITION BY
                tt.league_id,
                tt.season

            ORDER BY
                tt.points DESC,
                tt.goal_difference DESC,
                tt.goals_for DESC,
                t.team_name
        ) AS position

    FROM team_totals tt

    JOIN teams t
        ON tt.team_id = t.team_id

)


SELECT
    league_id,
    season,
    position,
    team_id,
    team_name,

    played,
    wins,
    draws,
    losses,

    goals_for,
    goals_against,
    goal_difference,
    points

FROM ranked_standings;