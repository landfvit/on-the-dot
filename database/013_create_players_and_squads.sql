CREATE TABLE IF NOT EXISTS players (

    player_id BIGINT PRIMARY KEY,

    player_name VARCHAR(255) NOT NULL,

    first_name VARCHAR(255),
    last_name VARCHAR(255),

    birth_date DATE,

    nationality VARCHAR(100),

    height_cm INTEGER,
    weight_kg INTEGER,

    photo_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

);


CREATE TABLE IF NOT EXISTS squad_memberships (

    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,

    team_id INTEGER NOT NULL,
    player_id BIGINT NOT NULL,

    squad_number INTEGER,
    position VARCHAR(50),

    age INTEGER,

    photo_url TEXT,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

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


CREATE INDEX IF NOT EXISTS idx_squad_memberships_team_season
ON squad_memberships (
    team_id,
    league_id,
    season
);


CREATE INDEX IF NOT EXISTS idx_squad_memberships_player
ON squad_memberships (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_squad_memberships_position
ON squad_memberships (
    position
);