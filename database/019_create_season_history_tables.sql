BEGIN;


-- keep the original season player payload as well

ALTER TABLE player_season_statistics
ADD COLUMN IF NOT EXISTS raw_payload JSONB;


-- generic raw storage for season-level API responses

CREATE TABLE IF NOT EXISTS season_raw_data (
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,

    data_type VARCHAR(50) NOT NULL,
    data_key VARCHAR(100) NOT NULL DEFAULT 'all',

    source VARCHAR(50) NOT NULL DEFAULT 'api-football',

    payload JSONB NOT NULL,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        league_id,
        season,
        data_type,
        data_key,
        source
    ),

    CONSTRAINT season_raw_data_league_fkey
        FOREIGN KEY (
            league_id
        )
        REFERENCES leagues (
            league_id
        )
        ON DELETE CASCADE,

    CONSTRAINT season_raw_data_season_fkey
        FOREIGN KEY (
            league_id,
            season
        )
        REFERENCES seasons (
            league_id,
            season
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_season_raw_data_type
ON season_raw_data (
    data_type
);


CREATE INDEX IF NOT EXISTS idx_season_raw_data_season
ON season_raw_data (
    league_id,
    season
);


-- final / current standings returned by API-Football

CREATE TABLE IF NOT EXISTS season_standings (
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    team_id INTEGER NOT NULL,

    group_name VARCHAR(150),

    league_rank INTEGER,
    points INTEGER,
    goals_difference INTEGER,

    form VARCHAR(100),
    description TEXT,

    played_total INTEGER,
    wins_total INTEGER,
    draws_total INTEGER,
    losses_total INTEGER,
    goals_for_total INTEGER,
    goals_against_total INTEGER,

    played_home INTEGER,
    wins_home INTEGER,
    draws_home INTEGER,
    losses_home INTEGER,
    goals_for_home INTEGER,
    goals_against_home INTEGER,

    played_away INTEGER,
    wins_away INTEGER,
    draws_away INTEGER,
    losses_away INTEGER,
    goals_for_away INTEGER,
    goals_against_away INTEGER,

    raw_payload JSONB,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        league_id,
        season,
        team_id
    ),

    CONSTRAINT season_standings_league_fkey
        FOREIGN KEY (
            league_id
        )
        REFERENCES leagues (
            league_id
        )
        ON DELETE CASCADE,

    CONSTRAINT season_standings_season_fkey
        FOREIGN KEY (
            league_id,
            season
        )
        REFERENCES seasons (
            league_id,
            season
        )
        ON DELETE CASCADE,

    CONSTRAINT season_standings_team_fkey
        FOREIGN KEY (
            team_id
        )
        REFERENCES teams (
            team_id
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_season_standings_rank
ON season_standings (
    league_id,
    season,
    league_rank
);


CREATE INDEX IF NOT EXISTS idx_season_standings_team
ON season_standings (
    team_id,
    season
);


-- richer /teams/statistics response
-- raw_payload keeps minute distributions, over/under data,
-- formations and other nested fields

CREATE TABLE IF NOT EXISTS team_season_api_statistics (
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    team_id INTEGER NOT NULL,

    form VARCHAR(100),

    fixtures_played_home INTEGER,
    fixtures_played_away INTEGER,
    fixtures_played_total INTEGER,

    wins_home INTEGER,
    wins_away INTEGER,
    wins_total INTEGER,

    draws_home INTEGER,
    draws_away INTEGER,
    draws_total INTEGER,

    losses_home INTEGER,
    losses_away INTEGER,
    losses_total INTEGER,

    goals_for_home INTEGER,
    goals_for_away INTEGER,
    goals_for_total INTEGER,

    goals_against_home INTEGER,
    goals_against_away INTEGER,
    goals_against_total INTEGER,

    goals_for_avg_home NUMERIC(8, 3),
    goals_for_avg_away NUMERIC(8, 3),
    goals_for_avg_total NUMERIC(8, 3),

    goals_against_avg_home NUMERIC(8, 3),
    goals_against_avg_away NUMERIC(8, 3),
    goals_against_avg_total NUMERIC(8, 3),

    biggest_winning_streak INTEGER,
    biggest_drawing_streak INTEGER,
    biggest_losing_streak INTEGER,

    biggest_win_home VARCHAR(50),
    biggest_win_away VARCHAR(50),

    biggest_loss_home VARCHAR(50),
    biggest_loss_away VARCHAR(50),

    clean_sheets_home INTEGER,
    clean_sheets_away INTEGER,
    clean_sheets_total INTEGER,

    failed_to_score_home INTEGER,
    failed_to_score_away INTEGER,
    failed_to_score_total INTEGER,

    penalties_scored INTEGER,
    penalties_missed INTEGER,
    penalties_total INTEGER,
    penalties_percentage NUMERIC(8, 3),

    raw_payload JSONB NOT NULL,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        league_id,
        season,
        team_id
    ),

    CONSTRAINT team_season_api_stats_league_fkey
        FOREIGN KEY (
            league_id
        )
        REFERENCES leagues (
            league_id
        )
        ON DELETE CASCADE,

    CONSTRAINT team_season_api_stats_season_fkey
        FOREIGN KEY (
            league_id,
            season
        )
        REFERENCES seasons (
            league_id,
            season
        )
        ON DELETE CASCADE,

    CONSTRAINT team_season_api_stats_team_fkey
        FOREIGN KEY (
            team_id
        )
        REFERENCES teams (
            team_id
        )
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_team_season_api_stats_team
ON team_season_api_statistics (
    team_id,
    season
);


-- injuries / suspensions tied to league-season and often a fixture

CREATE TABLE IF NOT EXISTS season_injuries (
    injury_record_id BIGSERIAL PRIMARY KEY,

    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,

    fixture_id BIGINT,

    team_id INTEGER,
    player_id BIGINT,

    player_name VARCHAR(200),

    injury_type VARCHAR(100),
    reason TEXT,

    fixture_date TIMESTAMPTZ,

    raw_payload JSONB NOT NULL,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_season_injuries_unique
ON season_injuries (
    league_id,
    season,
    COALESCE(
        fixture_id,
        0
    ),
    COALESCE(
        team_id,
        0
    ),
    COALESCE(
        player_id,
        0
    ),
    COALESCE(
        injury_type,
        ''
    ),
    COALESCE(
        reason,
        ''
    )
);


CREATE INDEX IF NOT EXISTS idx_season_injuries_player
ON season_injuries (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_season_injuries_team
ON season_injuries (
    team_id
);


CREATE INDEX IF NOT EXISTS idx_season_injuries_fixture
ON season_injuries (
    fixture_id
);


CREATE INDEX IF NOT EXISTS idx_season_injuries_season
ON season_injuries (
    league_id,
    season
);


-- complete historical injury / suspension timeline from /sidelined

CREATE TABLE IF NOT EXISTS player_sidelined (
    sidelined_id BIGSERIAL PRIMARY KEY,

    player_id BIGINT NOT NULL,

    sidelined_type VARCHAR(200),

    start_date DATE,
    end_date DATE,

    start_date_raw VARCHAR(100),
    end_date_raw VARCHAR(100),

    raw_payload JSONB NOT NULL,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_player_sidelined_unique
ON player_sidelined (
    player_id,
    COALESCE(
        sidelined_type,
        ''
    ),
    COALESCE(
        start_date_raw,
        ''
    ),
    COALESCE(
        end_date_raw,
        ''
    )
);


CREATE INDEX IF NOT EXISTS idx_player_sidelined_player
ON player_sidelined (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_player_sidelined_dates
ON player_sidelined (
    start_date,
    end_date
);


-- transfer history

CREATE TABLE IF NOT EXISTS player_transfers (
    transfer_id BIGSERIAL PRIMARY KEY,

    player_id BIGINT NOT NULL,
    player_name VARCHAR(200),

    transfer_date DATE,
    transfer_date_raw VARCHAR(100),

    transfer_type VARCHAR(200),

    team_out_id INTEGER,
    team_out_name VARCHAR(200),

    team_in_id INTEGER,
    team_in_name VARCHAR(200),

    raw_payload JSONB NOT NULL,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_player_transfers_unique
ON player_transfers (
    player_id,
    COALESCE(
        transfer_date_raw,
        ''
    ),
    COALESCE(
        team_out_id,
        0
    ),
    COALESCE(
        team_in_id,
        0
    ),
    COALESCE(
        transfer_type,
        ''
    )
);


CREATE INDEX IF NOT EXISTS idx_player_transfers_player
ON player_transfers (
    player_id
);


CREATE INDEX IF NOT EXISTS idx_player_transfers_team_out
ON player_transfers (
    team_out_id
);


CREATE INDEX IF NOT EXISTS idx_player_transfers_team_in
ON player_transfers (
    team_in_id
);


CREATE INDEX IF NOT EXISTS idx_player_transfers_date
ON player_transfers (
    transfer_date
);


-- coach master data

CREATE TABLE IF NOT EXISTS coaches (
    coach_id BIGINT PRIMARY KEY,

    coach_name VARCHAR(200),
    first_name VARCHAR(150),
    last_name VARCHAR(150),

    age INTEGER,

    birth_date DATE,
    birth_place VARCHAR(150),
    birth_country VARCHAR(100),

    nationality VARCHAR(100),

    height VARCHAR(50),
    weight VARCHAR(50),

    photo_url TEXT,

    current_team_id INTEGER,
    current_team_name VARCHAR(200),

    raw_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_coaches_name
ON coaches (
    LOWER(coach_name)
);


CREATE INDEX IF NOT EXISTS idx_coaches_current_team
ON coaches (
    current_team_id
);


-- historical coaching career returned by /coachs

CREATE TABLE IF NOT EXISTS coach_careers (
    coach_career_id BIGSERIAL PRIMARY KEY,

    coach_id BIGINT NOT NULL,

    team_id INTEGER,
    team_name VARCHAR(200),

    start_date DATE,
    end_date DATE,

    start_date_raw VARCHAR(100),
    end_date_raw VARCHAR(100),

    raw_payload JSONB NOT NULL,

    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT coach_careers_coach_fkey
        FOREIGN KEY (
            coach_id
        )
        REFERENCES coaches (
            coach_id
        )
        ON DELETE CASCADE
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_coach_careers_unique
ON coach_careers (
    coach_id,
    COALESCE(
        team_id,
        0
    ),
    COALESCE(
        start_date_raw,
        ''
    ),
    COALESCE(
        end_date_raw,
        ''
    )
);


CREATE INDEX IF NOT EXISTS idx_coach_careers_team
ON coach_careers (
    team_id
);


CREATE INDEX IF NOT EXISTS idx_coach_careers_coach
ON coach_careers (
    coach_id
);


COMMIT;