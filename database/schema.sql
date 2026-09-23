CREATE TABLE fixtures (
    fixture_id BIGINT PRIMARY KEY,
    league_id INT NOT NULL,
    season INT NOT NULL,
    match_date TIMESTAMPTZ NOT NULL,
    status VARCHAR(20),

    home_team_id INT NOT NULL,
    home_team_name VARCHAR(100) NOT NULL,

    away_team_id INT NOT NULL,
    away_team_name VARCHAR(100) NOT NULL,

    home_goals INT,
    away_goals INT
);