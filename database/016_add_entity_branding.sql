CREATE TABLE IF NOT EXISTS countries (
    country_code VARCHAR(20) PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    flag_url TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_countries_name_lower
ON countries (
    LOWER(country_name)
);


ALTER TABLE teams
ADD COLUMN IF NOT EXISTS team_code VARCHAR(20);

ALTER TABLE teams
ADD COLUMN IF NOT EXISTS country_name VARCHAR(100);

ALTER TABLE teams
ADD COLUMN IF NOT EXISTS country_code VARCHAR(20);

ALTER TABLE teams
ADD COLUMN IF NOT EXISTS logo_url TEXT;


ALTER TABLE leagues
ADD COLUMN IF NOT EXISTS logo_url TEXT;

ALTER TABLE leagues
ADD COLUMN IF NOT EXISTS country_code VARCHAR(20);

ALTER TABLE leagues
ADD COLUMN IF NOT EXISTS country_flag_url TEXT;


CREATE INDEX IF NOT EXISTS idx_teams_team_name_lower
ON teams (
    LOWER(team_name)
);


CREATE INDEX IF NOT EXISTS idx_teams_country_name
ON teams (
    country_name
);


CREATE INDEX IF NOT EXISTS idx_teams_country_code
ON teams (
    country_code
);


CREATE INDEX IF NOT EXISTS idx_leagues_league_name_lower
ON leagues (
    LOWER(league_name)
);


CREATE INDEX IF NOT EXISTS idx_leagues_country_code
ON leagues (
    country_code
);