ALTER TABLE fixtures
ADD CONSTRAINT fk_fixtures_home_team
FOREIGN KEY (home_team_id)
REFERENCES teams(team_id);

ALTER TABLE fixtures
ADD CONSTRAINT fk_fixtures_away_team
FOREIGN KEY (away_team_id)
REFERENCES teams(team_id);