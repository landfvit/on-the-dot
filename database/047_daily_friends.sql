BEGIN;
SET LOCAL lock_timeout='5s';

CREATE TABLE game_daily_pools (
 day DATE PRIMARY KEY,
 deck JSONB NOT NULL CHECK(jsonb_array_length(deck)=50),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE game_mode_runs (
 run_id UUID PRIMARY KEY,
 mode TEXT NOT NULL CHECK(mode IN ('daily','friend')),
 owner_id UUID NOT NULL REFERENCES game_accounts,
 start_request_id UUID NOT NULL,
 day DATE REFERENCES game_daily_pools,
 invite TEXT UNIQUE,
 state JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(owner_id,start_request_id),
 CHECK((mode='daily' AND day IS NOT NULL AND invite IS NULL) OR
       (mode='friend' AND day IS NULL AND invite IS NOT NULL AND length(invite)>=32))
);
CREATE TABLE game_mode_members (
 run_id UUID NOT NULL REFERENCES game_mode_runs,
 account_id UUID NOT NULL REFERENCES game_accounts,
 seat INTEGER NOT NULL CHECK(seat IN (0,1)),
 active BOOLEAN NOT NULL DEFAULT TRUE,
 PRIMARY KEY(run_id,account_id), UNIQUE(run_id,seat)
);
CREATE UNIQUE INDEX game_one_active_mode ON game_mode_members(account_id) WHERE active;
CREATE TABLE game_mode_seen (
 account_id UUID NOT NULL,
 week_start DATE NOT NULL,
 day DATE NOT NULL,
 question_id UUID NOT NULL,
 release_id UUID NOT NULL,
 run_id UUID NOT NULL,
 position INTEGER NOT NULL CHECK(position>0),
 PRIMARY KEY(account_id,week_start,question_id),
 UNIQUE(account_id,run_id,position),
 FOREIGN KEY(run_id,account_id) REFERENCES game_mode_members,
 FOREIGN KEY(release_id,question_id) REFERENCES penalty_bank_questions,
 CHECK(week_start=day-(EXTRACT(ISODOW FROM day)::INTEGER-1))
);
-- Solo allocations retain their existing semantics. New modes add only opened
-- questions, and the union is the shared no-repeat filter for every mode.
CREATE VIEW game_used_questions AS
 SELECT account_id,week_start,day,question_id,release_id,run_id,position FROM game_question_history
 UNION ALL
 SELECT account_id,week_start,day,question_id,release_id,run_id,position FROM game_mode_seen;
CREATE TABLE game_mode_xp (
 account_id UUID NOT NULL,
 run_id UUID NOT NULL,
 slot INTEGER NOT NULL CHECK(slot>=0),
 amount INTEGER NOT NULL CHECK(amount>0),
 reason TEXT NOT NULL CHECK(reason='correct_answer'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(run_id,account_id,slot),
 FOREIGN KEY(run_id,account_id) REFERENCES game_mode_members
);
CREATE INDEX game_mode_xp_account ON game_mode_xp(account_id);
CREATE VIEW game_all_xp AS SELECT * FROM game_xp_ledger UNION ALL SELECT * FROM game_mode_xp;
CREATE TABLE game_mode_activity (
 account_id UUID NOT NULL,
 day DATE NOT NULL,
 run_id UUID NOT NULL,
 PRIMARY KEY(account_id,day),
 FOREIGN KEY(run_id,account_id) REFERENCES game_mode_members
);
CREATE VIEW game_all_activity AS
 SELECT account_id,day FROM game_daily_activity UNION SELECT account_id,day FROM game_mode_activity;
CREATE TABLE game_daily_wins (
 account_id UUID NOT NULL,
 day DATE NOT NULL REFERENCES game_daily_pools,
 run_id UUID NOT NULL UNIQUE,
 won_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(account_id,day),
 FOREIGN KEY(run_id,account_id) REFERENCES game_mode_members
);

CREATE FUNCTION game_mode_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.mode<>OLD.mode OR NEW.owner_id<>OLD.owner_id OR NEW.start_request_id<>OLD.start_request_id
    OR NEW.day IS DISTINCT FROM OLD.day OR NEW.invite IS DISTINCT FROM OLD.invite
    OR NEW.state->'rules' IS DISTINCT FROM OLD.state->'rules'
    OR NEW.state->'created_at' IS DISTINCT FROM OLD.state->'created_at'
    OR (OLD.state->>'phase' IN ('FINISHED','ABANDONED') AND NEW.state<>OLD.state)
    OR jsonb_array_length(NEW.state->'history')<jsonb_array_length(OLD.state->'history')
    OR EXISTS(SELECT 1 FROM generate_series(0,jsonb_array_length(OLD.state->'history')-1) n
              WHERE NEW.state->'history'->n IS DISTINCT FROM OLD.state->'history'->n)
    OR (OLD.state->>'phase'<>'LOBBY' AND EXISTS(
       SELECT 1 FROM generate_series(0,jsonb_array_length(OLD.state->'deck')-1) n
       WHERE NEW.state->'deck'->n IS DISTINCT FROM OLD.state->'deck'->n)) THEN
   RAISE EXCEPTION 'Game identity, resolved events and completed results are frozen';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER game_mode_frozen BEFORE UPDATE ON game_mode_runs FOR EACH ROW EXECUTE FUNCTION game_mode_guard();

CREATE FUNCTION game_daily_win_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE r game_mode_runs;
BEGIN
 SELECT * INTO STRICT r FROM game_mode_runs WHERE run_id=NEW.run_id;
 IF r.mode<>'daily' OR r.owner_id<>NEW.account_id OR r.day<>NEW.day OR r.state->>'phase'<>'FINISHED'
    OR (game_shootout_winner(r.state)='player' OR
      (game_shootout_winner(r.state) IS NULL AND r.state->>'end_reason'='daily_pool_exhausted' AND jsonb_array_length(r.state->'history')>0
       AND jsonb_array_length(r.state->'history')=jsonb_array_length(r.state->'deck'))) IS NOT TRUE THEN
   RAISE EXCEPTION 'Daily win requires a finished, won challenge';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER game_daily_win_valid BEFORE INSERT ON game_daily_wins FOR EACH ROW EXECUTE FUNCTION game_daily_win_guard();

CREATE FUNCTION game_mode_xp_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE r game_mode_runs; a JSONB; q JSONB; expected INTEGER;
BEGIN
 SELECT * INTO STRICT r FROM game_mode_runs WHERE run_id=NEW.run_id;
 IF r.mode='daily' AND NEW.slot>0 THEN
   q:=r.state->'deck'->(NEW.slot-1);
   a:=r.state->'history'->(NEW.slot-1);
   expected:=CASE q->>'difficulty' WHEN 'easy' THEN 10 WHEN 'medium' THEN 20 WHEN 'hard' THEN 30 END;
   IF a IS NULL OR (a->>'correct')::boolean IS DISTINCT FROM TRUE OR NEW.amount IS DISTINCT FROM expected
      OR NEW.reason<>'correct_answer' OR NEW.account_id<>r.owner_id THEN
      RAISE EXCEPTION 'XP requires a frozen correct answer'; END IF;
 ELSE
   RAISE EXCEPTION 'Friend Duels never award XP';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER game_mode_xp_valid BEFORE INSERT ON game_mode_xp FOR EACH ROW EXECUTE FUNCTION game_mode_xp_guard();
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['game_daily_pools','game_mode_seen','game_mode_xp','game_mode_activity','game_daily_wins'] LOOP
   EXECUTE format('CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION pvp_immutable()',t);
 END LOOP;
END $$;
COMMIT;
