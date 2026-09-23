BEGIN;

CREATE TABLE IF NOT EXISTS team_venue_snapshots (
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    venue_id BIGINT NOT NULL REFERENCES venues(venue_id),
    source TEXT NOT NULL DEFAULT 'API-Football /teams',
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (league_id, season, team_id)
);

COMMIT;
