CREATE TABLE fixture_statistics (
    fixture_id BIGINT NOT NULL,
    team_id INT NOT NULL,
    shots_on_goal INT,
    shots_off_goal INT,
    total_shots INT,
    blocked_shots INT,
    shots_inside_box INT,
    shots_outside_box INT,
    fouls INT,
    corner_kicks INT,
    offsides INT,
    ball_possession NUMERIC(5, 2),
    yellow_cards INT,
    red_cards INT,
    goalkeeper_saves INT,
    total_passes INT,
    passes_accurate INT,
    passes_percentage NUMERIC(5, 2),
    PRIMARY KEY (fixture_id, team_id),
    CONSTRAINT fk_statistics_fixture
        FOREIGN KEY (fixture_id)
        REFERENCES fixtures(fixture_id),
    CONSTRAINT fk_statistics_team
        FOREIGN KEY (team_id)
        REFERENCES teams(team_id)
);