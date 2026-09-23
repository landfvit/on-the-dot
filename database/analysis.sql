-- average team statistics

SELECT
    t.team_name,
    COUNT(*) AS matches_with_stats,
    ROUND(AVG(s.total_shots), 2) AS avg_shots,
    ROUND(AVG(s.shots_on_goal), 2) AS avg_shots_on_goal,
    ROUND(AVG(s.ball_possession), 2) AS avg_possession,
    ROUND(AVG(s.corner_kicks), 2) AS avg_corners,
    ROUND(AVG(s.passes_percentage), 2) AS avg_pass_accuracy
FROM fixture_statistics s
JOIN teams t
    ON s.team_id = t.team_id
GROUP BY
    t.team_id,
    t.team_name
ORDER BY
    avg_shots DESC;


-- match result distribution

SELECT
    COUNT(*) AS matches,

    COUNT(*) FILTER (
        WHERE home_goals > away_goals
    ) AS home_wins,

    COUNT(*) FILTER (
        WHERE home_goals = away_goals
    ) AS draws,

    COUNT(*) FILTER (
        WHERE home_goals < away_goals
    ) AS away_wins,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE home_goals > away_goals
        ) / COUNT(*),
        2
    ) AS home_win_percentage,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE home_goals = away_goals
        ) / COUNT(*),
        2
    ) AS draw_percentage,

    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE home_goals < away_goals
        ) / COUNT(*),
        2
    ) AS away_win_percentage

FROM fixtures
WHERE status = 'FT';

-- team form from last 5 matches

WITH team_matches AS (

    SELECT
        fixture_id,
        match_date,
        home_team_id AS team_id,

        CASE
            WHEN home_goals > away_goals THEN 3
            WHEN home_goals = away_goals THEN 1
            ELSE 0
        END AS points

    FROM fixtures
    WHERE status = 'FT'

    UNION ALL

    SELECT
        fixture_id,
        match_date,
        away_team_id AS team_id,

        CASE
            WHEN away_goals > home_goals THEN 3
            WHEN away_goals = home_goals THEN 1
            ELSE 0
        END AS points

    FROM fixtures
    WHERE status = 'FT'
),

team_form AS (

    SELECT
        fixture_id,
        team_id,
        match_date,
        points,

        SUM(points) OVER (
            PARTITION BY team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS points_last_5

    FROM team_matches
)

SELECT
    t.team_name,
    tf.match_date,
    tf.points,
    tf.points_last_5

FROM team_form tf

JOIN teams t
    ON tf.team_id = t.team_id

ORDER BY
    t.team_name,
    tf.match_date;

-- match features with team form

WITH team_matches AS (

    SELECT
        fixture_id,
        match_date,
        home_team_id AS team_id,
        'home' AS side,

        CASE
            WHEN home_goals > away_goals THEN 3
            WHEN home_goals = away_goals THEN 1
            ELSE 0
        END AS points

    FROM fixtures
    WHERE status = 'FT'

    UNION ALL

    SELECT
        fixture_id,
        match_date,
        away_team_id AS team_id,
        'away' AS side,

        CASE
            WHEN away_goals > home_goals THEN 3
            WHEN away_goals = home_goals THEN 1
            ELSE 0
        END AS points

    FROM fixtures
    WHERE status = 'FT'
),

team_form AS (

    SELECT
        fixture_id,
        team_id,
        side,
        match_date,

        SUM(points) OVER (
            PARTITION BY team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS points_last_5

    FROM team_matches
)

SELECT
    f.fixture_id,
    f.match_date,

    home.team_name AS home_team,
    away.team_name AS away_team,

    home_form.points_last_5 AS home_points_last_5,
    away_form.points_last_5 AS away_points_last_5,

    f.home_goals,
    f.away_goals

FROM fixtures f

JOIN teams home
    ON f.home_team_id = home.team_id

JOIN teams away
    ON f.away_team_id = away.team_id

LEFT JOIN team_form home_form
    ON f.fixture_id = home_form.fixture_id
    AND f.home_team_id = home_form.team_id

LEFT JOIN team_form away_form
    ON f.fixture_id = away_form.fixture_id
    AND f.away_team_id = away_form.team_id

WHERE f.status = 'FT'

ORDER BY f.match_date;

-- match features with team form and result

WITH team_matches AS (

    SELECT
        fixture_id,
        match_date,
        home_team_id AS team_id,
        'home' AS side,

        CASE
            WHEN home_goals > away_goals THEN 3
            WHEN home_goals = away_goals THEN 1
            ELSE 0
        END AS points

    FROM fixtures
    WHERE status = 'FT'

    UNION ALL

    SELECT
        fixture_id,
        match_date,
        away_team_id AS team_id,
        'away' AS side,

        CASE
            WHEN away_goals > home_goals THEN 3
            WHEN away_goals = home_goals THEN 1
            ELSE 0
        END AS points

    FROM fixtures
    WHERE status = 'FT'
),

team_form AS (

    SELECT
        fixture_id,
        team_id,
        side,
        match_date,

        SUM(points) OVER (
            PARTITION BY team_id
            ORDER BY match_date
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS points_last_5

    FROM team_matches
)

SELECT
    f.fixture_id,
    f.match_date,

    home.team_name AS home_team,
    away.team_name AS away_team,

    home_form.points_last_5 AS home_points_last_5,
    away_form.points_last_5 AS away_points_last_5,

    f.home_goals,
    f.away_goals,

    CASE
        WHEN f.home_goals > f.away_goals THEN 'H'
        WHEN f.home_goals = f.away_goals THEN 'D'
        ELSE 'A'
    END AS result

FROM fixtures f

JOIN teams home
    ON f.home_team_id = home.team_id

JOIN teams away
    ON f.away_team_id = away.team_id

LEFT JOIN team_form home_form
    ON f.fixture_id = home_form.fixture_id
    AND f.home_team_id = home_form.team_id

LEFT JOIN team_form away_form
    ON f.fixture_id = away_form.fixture_id
    AND f.away_team_id = away_form.team_id

WHERE f.status = 'FT'

ORDER BY f.match_date;