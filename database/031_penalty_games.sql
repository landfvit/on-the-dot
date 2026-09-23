BEGIN;
CREATE TABLE IF NOT EXISTS pvp_rate_limits (
    key TEXT NOT NULL, bucket_start TIMESTAMPTZ NOT NULL, count INTEGER NOT NULL,
    PRIMARY KEY(key,bucket_start)
);
CREATE TABLE IF NOT EXISTS pvp_players (
    player_id UUID PRIMARY KEY,
    token_hash TEXT UNIQUE NOT NULL CHECK(length(token_hash)=64),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '30 days'
);
CREATE TABLE IF NOT EXISTS pvp_matches (
    match_id UUID PRIMARY KEY,
    room_code TEXT UNIQUE NOT NULL,
    host_id UUID NOT NULL REFERENCES pvp_players,
    pack TEXT NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS pvp_matches_host_time ON pvp_matches(host_id,created_at);
CREATE TABLE IF NOT EXISTS pvp_penalties (
    match_id UUID NOT NULL REFERENCES pvp_matches,
    penalty_id INTEGER NOT NULL,
    snapshot JSONB NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(match_id,penalty_id)
);
CREATE TABLE IF NOT EXISTS pvp_answers (
    match_id UUID NOT NULL REFERENCES pvp_matches,
    penalty_id INTEGER NOT NULL,
    player_id UUID NOT NULL REFERENCES pvp_players,
    request_id UUID NOT NULL,
    answer JSONB NOT NULL,
    PRIMARY KEY(match_id,penalty_id,player_id),
    UNIQUE(match_id,player_id,request_id)
);
CREATE OR REPLACE FUNCTION pvp_immutable() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Penalty audit records are immutable'; END $$;
CREATE TRIGGER pvp_answer_frozen BEFORE UPDATE OR DELETE ON pvp_answers FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
CREATE TRIGGER pvp_penalty_frozen BEFORE UPDATE OR DELETE ON pvp_penalties FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
INSERT INTO trivia_schema_migrations(name) VALUES ('031_penalty_games') ON CONFLICT DO NOTHING;
COMMIT;
