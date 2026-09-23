CREATE TABLE leagues (
    league_id INT PRIMARY KEY,
    league_name VARCHAR(100) NOT NULL,
    country_name VARCHAR(100) NOT NULL
);

CREATE TABLE seasons (
    league_id INT NOT NULL,
    season INT NOT NULL,

    PRIMARY KEY (league_id, season),

    CONSTRAINT fk_seasons_league
        FOREIGN KEY (league_id)
        REFERENCES leagues(league_id)
);

INSERT INTO leagues (
    league_id,
    league_name,
    country_name
)
VALUES (
    39,
    'Premier League',
    'England'
);

INSERT INTO seasons (
    league_id,
    season
)
SELECT DISTINCT
    league_id,
    season
FROM fixtures;

ALTER TABLE fixtures
ADD CONSTRAINT fk_fixtures_league
FOREIGN KEY (league_id)
REFERENCES leagues(league_id);

ALTER TABLE fixtures
ADD CONSTRAINT fk_fixtures_season
FOREIGN KEY (league_id, season)
REFERENCES seasons(league_id, season);