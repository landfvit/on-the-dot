CREATE TABLE IF NOT EXISTS player_season_statistics (

    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,

    team_id INTEGER NOT NULL,
    player_id BIGINT NOT NULL,

    appearances INTEGER,
    lineups INTEGER,
    minutes INTEGER,

    squad_number INTEGER,
    position VARCHAR(50),

    rating NUMERIC(5, 2),
    captain BOOLEAN,

    substitutes_in INTEGER,
    substitutes_out INTEGER,
    substitutes_bench INTEGER,

    shots_total INTEGER,
    shots_on_goal INTEGER,

    goals_total INTEGER,
    goals_conceded INTEGER,
    assists INTEGER,
    saves INTEGER,

    passes_total INTEGER,
    key_passes INTEGER,
    pass_accuracy NUMERIC(5, 2),

    tackles_total INTEGER,
    blocks INTEGER,
    interceptions INTEGER,

    duels_total INTEGER,
    duels_won INTEGER,

    dribbles_attempts INTEGER,
    dribbles_success INTEGER,
    dribbled_past INTEGER,

    fouls_drawn INTEGER,
    fouls_committed INTEGER,

    yellow_cards INTEGER,
    yellow_red_cards INTEGER,
    red_cards INTEGER,

    penalties_won INTEGER,
    penalties_committed INTEGER,
    penalties_scored INTEGER,
    penalties_missed INTEGER,
    penalties_saved INTEGER,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        league_id,
        season,
        team_id,
        player_id
    ),

    FOREIGN KEY (
        league_id,
        season
    )
        REFERENCES seasons (
            league_id,
            season
        )
        ON DELETE CASCADE,

    FOREIGN KEY (
        team_id
    )
        REFERENCES teams (
            team_id
        )
        ON DELETE CASCADE,

    FOREIGN KEY (
        player_id
    )
        REFERENCES players (
            player_id
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_player_season_statistics_team
ON player_season_statistics (
    league_id,
    season,
    team_id
);


CREATE INDEX IF NOT EXISTS idx_player_season_statistics_player
ON player_season_statistics (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_player_season_statistics_appearances
ON player_season_statistics (
    league_id,
    season,
    team_id,
    appearances
);