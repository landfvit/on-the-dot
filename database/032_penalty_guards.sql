BEGIN;
ALTER TABLE pvp_matches ADD CONSTRAINT pvp_match_valid_state CHECK (
    state->>'phase' IN ('LOBBY','COUNTDOWN','ANSWERING','RESOLVED','FINISHED','ABANDONED')
    AND state->>'mode' IN ('solo','pvp')
);
CREATE OR REPLACE FUNCTION pvp_match_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.match_id<>OLD.match_id OR NEW.room_code<>OLD.room_code OR NEW.pack<>OLD.pack
       OR NEW.host_id<>OLD.host_id OR NEW.created_at<>OLD.created_at
       OR NEW.state->'deck' IS DISTINCT FROM OLD.state->'deck'
       OR NEW.state->'rules' IS DISTINCT FROM OLD.state->'rules'
       OR NEW.state->'mode' IS DISTINCT FROM OLD.state->'mode' THEN
        RAISE EXCEPTION 'Match identity, question pack and rules are frozen';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER pvp_match_frozen BEFORE UPDATE ON pvp_matches FOR EACH ROW EXECUTE FUNCTION pvp_match_guard();
CREATE INDEX pvp_matches_active ON pvp_matches(created_at) WHERE state->>'phase' NOT IN ('FINISHED','ABANDONED');
INSERT INTO trivia_schema_migrations(name) VALUES ('032_penalty_guards') ON CONFLICT DO NOTHING;
COMMIT;
