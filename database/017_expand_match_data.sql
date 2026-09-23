BEGIN;


-- venues

CREATE TABLE IF NOT EXISTS venues (
    venue_id BIGINT PRIMARY KEY,

    venue_name VARCHAR(200),
    address TEXT,
    city VARCHAR(150),
    country_name VARCHAR(100),

    capacity INTEGER,
    surface VARCHAR(100),
    image_url TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        capacity IS NULL
        OR capacity >= 0
    )
);


CREATE INDEX IF NOT EXISTS idx_venues_name
ON venues (
    LOWER(venue_name)
);


CREATE INDEX IF NOT EXISTS idx_venues_city
ON venues (
    LOWER(city)
);


-- expand fixtures

ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS round VARCHAR(100);


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS referee VARCHAR(200);


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS timezone VARCHAR(100);


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS venue_id BIGINT;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS halftime_home INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS halftime_away INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS fulltime_home INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS fulltime_away INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS extratime_home INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS extratime_away INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS penalty_home INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS penalty_away INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS attendance INTEGER;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS attendance_source VARCHAR(100);


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS attendance_verified_at TIMESTAMPTZ;


ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS last_api_sync_at TIMESTAMPTZ;


DO $$
BEGIN

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fixtures_venue_id_fkey'
    ) THEN

        ALTER TABLE fixtures

        ADD CONSTRAINT fixtures_venue_id_fkey
        FOREIGN KEY (
            venue_id
        )
        REFERENCES venues (
            venue_id
        )
        ON DELETE SET NULL;

    END IF;

END
$$;


CREATE INDEX IF NOT EXISTS idx_fixtures_league_season_date
ON fixtures (
    league_id,
    season,
    match_date
);


CREATE INDEX IF NOT EXISTS idx_fixtures_home_team_date
ON fixtures (
    home_team_id,
    match_date
);


CREATE INDEX IF NOT EXISTS idx_fixtures_away_team_date
ON fixtures (
    away_team_id,
    match_date
);


CREATE INDEX IF NOT EXISTS idx_fixtures_venue
ON fixtures (
    venue_id
);


-- fixture events
-- goals, cards, substitutions, var, etc.

CREATE TABLE IF NOT EXISTS fixture_events (
    fixture_event_id BIGSERIAL PRIMARY KEY,

    fixture_id BIGINT NOT NULL,

    source_order INTEGER NOT NULL,

    team_id INTEGER,

    elapsed_minute INTEGER,
    extra_minute INTEGER,

    player_id BIGINT,
    player_name VARCHAR(200),

    assist_player_id BIGINT,
    assist_player_name VARCHAR(200),

    event_type VARCHAR(100),
    event_detail VARCHAR(200),

    comments TEXT,

    raw_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fixture_events_fixture_fkey
        FOREIGN KEY (
            fixture_id
        )
        REFERENCES fixtures (
            fixture_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fixture_events_team_fkey
        FOREIGN KEY (
            team_id
        )
        REFERENCES teams (
            team_id
        )
        ON DELETE SET NULL,

    CONSTRAINT fixture_events_unique_order
        UNIQUE (
            fixture_id,
            source_order
        ),

    CHECK (
        elapsed_minute IS NULL
        OR elapsed_minute >= 0
    ),

    CHECK (
        extra_minute IS NULL
        OR extra_minute >= 0
    )
);


CREATE INDEX IF NOT EXISTS idx_fixture_events_fixture
ON fixture_events (
    fixture_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_events_team
ON fixture_events (
    team_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_events_player
ON fixture_events (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_events_assist_player
ON fixture_events (
    assist_player_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_events_type
ON fixture_events (
    event_type
);


-- fixture lineups
-- one row per team in a fixture

CREATE TABLE IF NOT EXISTS fixture_lineups (
    fixture_id BIGINT NOT NULL,
    team_id INTEGER NOT NULL,

    formation VARCHAR(50),

    coach_id BIGINT,
    coach_name VARCHAR(200),

    raw_payload JSONB,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        fixture_id,
        team_id
    ),

    CONSTRAINT fixture_lineups_fixture_fkey
        FOREIGN KEY (
            fixture_id
        )
        REFERENCES fixtures (
            fixture_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fixture_lineups_team_fkey
        FOREIGN KEY (
            team_id
        )
        REFERENCES teams (
            team_id
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_fixture_lineups_team
ON fixture_lineups (
    team_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_lineups_coach
ON fixture_lineups (
    coach_id
);


-- players listed in the starting XI and substitutes

CREATE TABLE IF NOT EXISTS fixture_lineup_players (
    fixture_id BIGINT NOT NULL,
    team_id INTEGER NOT NULL,

    lineup_type VARCHAR(30) NOT NULL,

    source_order INTEGER NOT NULL,

    player_id BIGINT,
    player_name VARCHAR(200),

    shirt_number INTEGER,

    position VARCHAR(50),
    grid_position VARCHAR(50),

    raw_payload JSONB,

    PRIMARY KEY (
        fixture_id,
        team_id,
        lineup_type,
        source_order
    ),

    CONSTRAINT fixture_lineup_players_fixture_fkey
        FOREIGN KEY (
            fixture_id
        )
        REFERENCES fixtures (
            fixture_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fixture_lineup_players_team_fkey
        FOREIGN KEY (
            team_id
        )
        REFERENCES teams (
            team_id
        )
        ON DELETE CASCADE,

    CHECK (
        lineup_type IN (
            'start_xi',
            'substitute'
        )
    )
);


CREATE INDEX IF NOT EXISTS idx_fixture_lineup_players_player
ON fixture_lineup_players (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_lineup_players_team
ON fixture_lineup_players (
    team_id
);


-- extend existing team-level fixture statistics

ALTER TABLE fixture_statistics
ADD COLUMN IF NOT EXISTS raw_payload JSONB;


ALTER TABLE fixture_statistics
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();


-- individual player performance in one fixture

CREATE TABLE IF NOT EXISTS fixture_player_statistics (
    fixture_id BIGINT NOT NULL,
    team_id INTEGER NOT NULL,
    player_id BIGINT NOT NULL,

    player_name VARCHAR(200),

    minutes INTEGER,
    shirt_number INTEGER,
    position VARCHAR(50),

    rating NUMERIC(6, 2),

    captain BOOLEAN,
    substitute BOOLEAN,

    offsides INTEGER,

    shots_total INTEGER,
    shots_on_goal INTEGER,

    goals INTEGER,
    goals_conceded INTEGER,

    assists INTEGER,
    saves INTEGER,

    passes_total INTEGER,
    key_passes INTEGER,
    pass_accuracy NUMERIC(6, 2),

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

    raw_payload JSONB,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        fixture_id,
        team_id,
        player_id
    ),

    CONSTRAINT fixture_player_statistics_fixture_fkey
        FOREIGN KEY (
            fixture_id
        )
        REFERENCES fixtures (
            fixture_id
        )
        ON DELETE CASCADE,

    CONSTRAINT fixture_player_statistics_team_fkey
        FOREIGN KEY (
            team_id
        )
        REFERENCES teams (
            team_id
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_fixture_player_stats_player
ON fixture_player_statistics (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_player_stats_team
ON fixture_player_statistics (
    team_id
);


CREATE INDEX IF NOT EXISTS idx_fixture_player_stats_fixture
ON fixture_player_statistics (
    fixture_id
);


-- raw API responses
-- keeps original provider data even when we do not yet have
-- a dedicated relational column for a field

CREATE TABLE IF NOT EXISTS fixture_raw_data (
    fixture_id BIGINT NOT NULL,

    data_type VARCHAR(50) NOT NULL,

    source VARCHAR(50) NOT NULL DEFAULT 'api-football',

    payload JSONB NOT NULL,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        fixture_id,
        data_type,
        source
    ),

    CONSTRAINT fixture_raw_data_fixture_fkey
        FOREIGN KEY (
            fixture_id
        )
        REFERENCES fixtures (
            fixture_id
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_fixture_raw_data_type
ON fixture_raw_data (
    data_type
);


CREATE INDEX IF NOT EXISTS idx_fixture_raw_data_fixture
ON fixture_raw_data (
    fixture_id
);


COMMIT;