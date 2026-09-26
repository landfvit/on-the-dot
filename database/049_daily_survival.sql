BEGIN;
SET LOCAL lock_timeout='5s';

-- Existing shootouts keep their full question snapshots and frozen rules.
-- A v1 daily pool may be extended once, preserving every original question.
ALTER TABLE game_daily_pools DROP CONSTRAINT game_daily_pools_deck_check;
ALTER TABLE game_daily_pools ADD CONSTRAINT game_daily_pools_deck_check CHECK(jsonb_array_length(deck)>0);
ALTER TABLE game_daily_pools ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK(version IN (1,2));
DROP TRIGGER frozen ON game_daily_pools;
CREATE FUNCTION game_daily_pool_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Daily pools are immutable'; END IF;
 IF OLD.version<>1 OR NEW.version<>2 OR NEW.day<>OLD.day OR NEW.created_at<>OLD.created_at
    OR jsonb_array_length(NEW.deck)<jsonb_array_length(OLD.deck)
    OR EXISTS(SELECT 1 FROM generate_series(0,jsonb_array_length(OLD.deck)-1) n
              WHERE NEW.deck->n IS DISTINCT FROM OLD.deck->n) THEN
   RAISE EXCEPTION 'Only the one-time survival pool extension is allowed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON game_daily_pools FOR EACH ROW EXECUTE FUNCTION game_daily_pool_guard();

-- Reserve the ranked attempt when it starts, not when it finishes. Closing a
-- tab, forfeiting, retrying a POST or changing devices cannot buy another try.
CREATE TABLE game_daily_attempts (
 account_id UUID NOT NULL REFERENCES game_accounts,
 day DATE NOT NULL REFERENCES game_daily_pools,
 run_id UUID NOT NULL UNIQUE REFERENCES game_mode_runs,
 PRIMARY KEY(account_id,day)
);
CREATE TABLE game_daily_scores (
 run_id UUID PRIMARY KEY REFERENCES game_daily_attempts(run_id),
 account_id UUID NOT NULL REFERENCES game_accounts,
 day DATE NOT NULL,
 goals INTEGER NOT NULL CHECK(goals>=0),
 penalties INTEGER NOT NULL CHECK(penalties>=goals),
 recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(account_id,day),
 FOREIGN KEY(account_id,day) REFERENCES game_daily_attempts
);
CREATE INDEX game_daily_scores_best ON game_daily_scores(account_id,goals DESC);
CREATE FUNCTION game_daily_survival_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE r game_mode_runs; actual INTEGER;
BEGIN
 SELECT * INTO STRICT r FROM game_mode_runs WHERE run_id=NEW.run_id;
 IF r.mode<>'daily' OR r.owner_id<>NEW.account_id OR r.day<>NEW.day
    OR r.state#>>'{rules,format}' IS DISTINCT FROM 'daily_survival'
    OR r.state#>>'{rules,ranked}' IS DISTINCT FROM 'true'
    OR NOT EXISTS(SELECT 1 FROM game_accounts WHERE account_id=NEW.account_id AND NOT is_guest) THEN
   RAISE EXCEPTION 'A ranked Daily attempt requires its registered owner';
 END IF;
 IF TG_TABLE_NAME='game_daily_scores' THEN
   SELECT count(*) INTO actual FROM jsonb_array_elements(r.state->'history') a WHERE (a->>'correct')::boolean;
   IF r.state->>'phase' NOT IN ('FINISHED','ABANDONED') OR NEW.goals<>actual
      OR NEW.penalties<>jsonb_array_length(r.state->'history')
      OR NOT EXISTS(SELECT 1 FROM game_daily_attempts WHERE run_id=NEW.run_id AND account_id=NEW.account_id AND day=NEW.day) THEN
     RAISE EXCEPTION 'Daily score must match the frozen ranked result';
   END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ranked_attempt BEFORE INSERT ON game_daily_attempts FOR EACH ROW EXECUTE FUNCTION game_daily_survival_guard();
CREATE TRIGGER ranked_score BEFORE INSERT ON game_daily_scores FOR EACH ROW EXECUTE FUNCTION game_daily_survival_guard();
CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON game_daily_attempts FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON game_daily_scores FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
COMMIT;
