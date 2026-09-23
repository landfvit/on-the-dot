CREATE OR REPLACE VIEW team_season_statistics AS

WITH complete_stat_fixtures AS (

    SELECT
        fixture_id

    FROM fixture_statistics

    GROUP BY fixture_id

    HAVING COUNT(DISTINCT team_id) = 2

),


team_stat_averages AS (

    SELECT
        f.league_id,
        f.season,
        s.team_id,

        COUNT(
            DISTINCT f.fixture_id
        ) AS matches_with_stats,

        AVG(
            s.ball_possession
        ) AS avg_ball_possession,

        AVG(
            s.total_shots
        ) AS avg_total_shots,

        AVG(
            s.shots_on_goal
        ) AS avg_shots_on_goal,

        AVG(
            s.shots_off_goal
        ) AS avg_shots_off_goal,

        AVG(
            s.blocked_shots
        ) AS avg_blocked_shots,

        AVG(
            s.shots_inside_box
        ) AS avg_shots_inside_box,

        AVG(
            s.shots_outside_box
        ) AS avg_shots_outside_box,

        AVG(
            s.corner_kicks
        ) AS avg_corner_kicks,

        AVG(
            s.fouls
        ) AS avg_fouls,

        AVG(
            s.offsides
        ) AS avg_offsides,

        SUM(
            COALESCE(
                s.yellow_cards,
                0
            )
        ) AS total_yellow_cards,

        AVG(
            COALESCE(
                s.yellow_cards,
                0
            )
        ) AS avg_yellow_cards,

        SUM(
            COALESCE(
                s.red_cards,
                0
            )
        ) AS total_red_cards,

        AVG(
            COALESCE(
                s.red_cards,
                0
            )
        ) AS avg_red_cards,

        AVG(
            s.goalkeeper_saves
        ) AS avg_goalkeeper_saves,

        AVG(
            s.total_passes
        ) AS avg_total_passes,

        AVG(
            s.passes_accurate
        ) AS avg_passes_accurate,

        AVG(
            s.passes_percentage
        ) AS avg_passes_percentage

    FROM fixture_statistics s

    JOIN fixtures f
        ON s.fixture_id = f.fixture_id

    JOIN complete_stat_fixtures csf
        ON f.fixture_id = csf.fixture_id

    WHERE f.status = 'FT'

    GROUP BY
        f.league_id,
        f.season,
        s.team_id

),


team_data AS (

    SELECT
        ls.league_id,
        ls.season,

        ls.team_id,
        ls.team_name,

        ls.position AS league_position,

        ls.played AS matches_played,
        ls.wins,
        ls.draws,
        ls.losses,

        ls.goals_for,
        ls.goals_against,
        ls.goal_difference,
        ls.points,

        COALESCE(
            tsa.matches_with_stats,
            0
        ) AS matches_with_stats,

        tsa.avg_ball_possession,

        tsa.avg_total_shots,
        tsa.avg_shots_on_goal,
        tsa.avg_shots_off_goal,
        tsa.avg_blocked_shots,

        tsa.avg_shots_inside_box,
        tsa.avg_shots_outside_box,

        tsa.avg_corner_kicks,
        tsa.avg_fouls,
        tsa.avg_offsides,

        tsa.total_yellow_cards,
        tsa.avg_yellow_cards,

        tsa.total_red_cards,
        tsa.avg_red_cards,

        tsa.avg_goalkeeper_saves,

        tsa.avg_total_passes,
        tsa.avg_passes_accurate,
        tsa.avg_passes_percentage

    FROM league_standings ls

    LEFT JOIN team_stat_averages tsa
        ON ls.league_id = tsa.league_id
        AND ls.season = tsa.season
        AND ls.team_id = tsa.team_id

),


ranked_data AS (

    SELECT
        td.*,

        COUNT(*) OVER (
            PARTITION BY
                td.league_id,
                td.season
        ) AS league_team_count,


        CASE
            WHEN td.avg_ball_possession IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_ball_possession DESC NULLS LAST
            )
        END AS ball_possession_rank,


        CASE
            WHEN td.avg_total_shots IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_total_shots DESC NULLS LAST
            )
        END AS total_shots_rank,


        CASE
            WHEN td.avg_shots_on_goal IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_shots_on_goal DESC NULLS LAST
            )
        END AS shots_on_goal_rank,


        CASE
            WHEN td.avg_shots_off_goal IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_shots_off_goal DESC NULLS LAST
            )
        END AS shots_off_goal_rank,


        CASE
            WHEN td.avg_blocked_shots IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_blocked_shots DESC NULLS LAST
            )
        END AS blocked_shots_rank,


        CASE
            WHEN td.avg_shots_inside_box IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_shots_inside_box DESC NULLS LAST
            )
        END AS shots_inside_box_rank,


        CASE
            WHEN td.avg_shots_outside_box IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_shots_outside_box DESC NULLS LAST
            )
        END AS shots_outside_box_rank,


        CASE
            WHEN td.avg_corner_kicks IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_corner_kicks DESC NULLS LAST
            )
        END AS corner_kicks_rank,


        CASE
            WHEN td.avg_fouls IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_fouls DESC NULLS LAST
            )
        END AS fouls_rank,


        CASE
            WHEN td.avg_offsides IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_offsides DESC NULLS LAST
            )
        END AS offsides_rank,


        CASE
            WHEN td.avg_yellow_cards IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_yellow_cards DESC NULLS LAST
            )
        END AS yellow_cards_rank,


        CASE
            WHEN td.avg_red_cards IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_red_cards DESC NULLS LAST
            )
        END AS red_cards_rank,


        CASE
            WHEN td.avg_goalkeeper_saves IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_goalkeeper_saves DESC NULLS LAST
            )
        END AS goalkeeper_saves_rank,


        CASE
            WHEN td.avg_total_passes IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_total_passes DESC NULLS LAST
            )
        END AS total_passes_rank,


        CASE
            WHEN td.avg_passes_accurate IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_passes_accurate DESC NULLS LAST
            )
        END AS passes_accurate_rank,


        CASE
            WHEN td.avg_passes_percentage IS NOT NULL
            THEN RANK() OVER (
                PARTITION BY
                    td.league_id,
                    td.season

                ORDER BY
                    td.avg_passes_percentage DESC NULLS LAST
            )
        END AS passes_percentage_rank

    FROM team_data td

)


SELECT
    league_id,
    season,

    team_id,
    team_name,

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


    ROUND(
        avg_ball_possession,
        2
    ) AS avg_ball_possession,

    ball_possession_rank,


    ROUND(
        avg_total_shots,
        2
    ) AS avg_total_shots,

    total_shots_rank,


    ROUND(
        avg_shots_on_goal,
        2
    ) AS avg_shots_on_goal,

    shots_on_goal_rank,


    ROUND(
        avg_shots_off_goal,
        2
    ) AS avg_shots_off_goal,

    shots_off_goal_rank,


    ROUND(
        avg_blocked_shots,
        2
    ) AS avg_blocked_shots,

    blocked_shots_rank,


    ROUND(
        avg_shots_inside_box,
        2
    ) AS avg_shots_inside_box,

    shots_inside_box_rank,


    ROUND(
        avg_shots_outside_box,
        2
    ) AS avg_shots_outside_box,

    shots_outside_box_rank,


    ROUND(
        avg_corner_kicks,
        2
    ) AS avg_corner_kicks,

    corner_kicks_rank,


    ROUND(
        avg_fouls,
        2
    ) AS avg_fouls,

    fouls_rank,


    ROUND(
        avg_offsides,
        2
    ) AS avg_offsides,

    offsides_rank,


    ROUND(
        avg_yellow_cards,
        2
    ) AS avg_yellow_cards,

    yellow_cards_rank,


    ROUND(
        avg_red_cards,
        2
    ) AS avg_red_cards,

    red_cards_rank,


    ROUND(
        avg_goalkeeper_saves,
        2
    ) AS avg_goalkeeper_saves,

    goalkeeper_saves_rank,


    ROUND(
        avg_total_passes,
        2
    ) AS avg_total_passes,

    total_passes_rank,


    ROUND(
        avg_passes_accurate,
        2
    ) AS avg_passes_accurate,

    passes_accurate_rank,


    ROUND(
        avg_passes_percentage,
        2
    ) AS avg_passes_percentage,

    passes_percentage_rank,

    total_yellow_cards,
    total_red_cards

FROM ranked_data;