BEGIN;
SET LOCAL lock_timeout = '5s';

-- Existing quizzes keep their frozen rules and ten-question contracts.
ALTER TABLE game_solo_runs DROP CONSTRAINT game_solo_runs_state_check;
ALTER TABLE game_solo_runs ADD CONSTRAINT game_solo_deck_size CHECK (
  CASE WHEN state->'rules'->>'format'='shootout' THEN
    jsonb_array_length(state->'deck')>=10 AND jsonb_array_length(state->'deck')%2=0
  ELSE jsonb_array_length(state->'deck')=10 END);
ALTER TABLE game_solo_answers DROP CONSTRAINT game_solo_answers_position_check;
ALTER TABLE game_solo_answers ADD CONSTRAINT game_solo_answers_position_check CHECK(position>=1);
ALTER TABLE game_question_history DROP CONSTRAINT game_question_history_position_check;
ALTER TABLE game_question_history ADD CONSTRAINT game_question_history_position_check CHECK(position>=1);
ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_ledger_slot_check;
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_ledger_slot_check CHECK(slot>=0);
ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_amount;
ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_slot_amount;
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_amount CHECK(amount>0);
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_slot_amount CHECK(
  (slot=0 AND reason='perfect_bonus') OR
  (slot>0 AND reason='correct_answer' AND amount IN (10,20,30)));

CREATE FUNCTION game_shootout_winner(s JSONB) RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE p INTEGER:=0; o INTEGER:=0; pk INTEGER:=0; ok INTEGER:=0; a RECORD;
BEGIN
  FOR a IN SELECT value,ordinality n FROM jsonb_array_elements(s->'history') WITH ORDINALITY LOOP
    IF a.n%2=1 THEN pk:=pk+1; p:=p+(a.value->>'correct')::boolean::integer;
    ELSE ok:=ok+1; o:=o+(NOT (a.value->>'correct')::boolean)::integer; END IF;
  END LOOP;
  IF greatest(pk,ok)<=5 THEN
    IF p>o+5-ok THEN RETURN 'player'; END IF;
    IF o>p+5-pk THEN RETURN 'opponent'; END IF;
  ELSIF pk=ok AND p<>o THEN
    RETURN CASE WHEN p>o THEN 'player' ELSE 'opponent' END;
  END IF;
  RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION game_run_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE old_count INTEGER:=jsonb_array_length(OLD.state->'deck'); extending BOOLEAN;
BEGIN
  extending:=OLD.state->'deck' IS DISTINCT FROM NEW.state->'deck';
  IF extending AND NOT (
    OLD.state->'rules'->>'format'='shootout' AND OLD.state->>'phase'='REVIEW'
    AND NEW.state->>'phase'='ANSWERING' AND (OLD.state->>'position')::integer=old_count
    AND jsonb_array_length(OLD.state->'history')=old_count
    AND game_shootout_winner(OLD.state) IS NULL
    AND NEW.state->'history'=OLD.state->'history'
    AND jsonb_array_length(NEW.state->'deck')=old_count+2
    AND NOT EXISTS(SELECT 1 FROM generate_series(0,old_count-1) n
      WHERE NEW.state->'deck'->n IS DISTINCT FROM OLD.state->'deck'->n)) THEN
    RAISE EXCEPTION 'Only a fresh sudden-death pair may extend a frozen deck';
  END IF;
  IF NEW.account_id<>OLD.account_id OR NEW.start_request_id<>OLD.start_request_id
    OR NEW.state->'rules' IS DISTINCT FROM OLD.state->'rules'
    OR NEW.state->'difficulty' IS DISTINCT FROM OLD.state->'difficulty'
    OR NEW.state->'category' IS DISTINCT FROM OLD.state->'category'
    OR NEW.state->'created_at' IS DISTINCT FROM OLD.state->'created_at'
    OR (OLD.state->>'phase' IN ('FINISHED','ABANDONED') AND NEW.state<>OLD.state) THEN
    RAISE EXCEPTION 'Solo identity, content, rules and completed results are frozen';
  END IF;
  IF NEW.state->'rules'->>'format'='shootout' AND NEW.state->>'phase'='FINISHED'
     AND game_shootout_winner(NEW.state) IS NULL THEN
    RAISE EXCEPTION 'A shootout cannot finish before there is a winner';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION game_allocate_questions() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE allocated_day DATE; q RECORD; previous_count INTEGER:=0;
BEGIN
  IF TG_OP='UPDATE' THEN previous_count:=jsonb_array_length(OLD.state->'deck'); END IF;
  FOR q IN SELECT item,position::integer FROM jsonb_array_elements(NEW.state->'deck') WITH ORDINALITY q(item,position)
           WHERE position>previous_count LOOP
    allocated_day:=(to_timestamp(COALESCE(q.item->>'allocated_at',NEW.state->>'created_at')::bigint/1000.0) AT TIME ZONE 'UTC')::date;
    INSERT INTO game_question_history VALUES(NEW.account_id,
      allocated_day-(EXTRACT(ISODOW FROM allocated_day)::integer-1),allocated_day,
      (q.item->>'question_id')::uuid,(q.item->>'release_id')::uuid,NEW.run_id,q.position);
  END LOOP;
  RETURN NEW;
END $$;
CREATE TRIGGER game_allocate_extra_questions AFTER UPDATE ON game_solo_runs
FOR EACH ROW EXECUTE FUNCTION game_allocate_questions();

CREATE OR REPLACE FUNCTION game_question_history_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE r game_solo_runs; expected_day DATE; q JSONB;
BEGIN
  SELECT * INTO STRICT r FROM game_solo_runs WHERE run_id=NEW.run_id;
  q:=r.state->'deck'->(NEW.position-1);
  expected_day:=(to_timestamp(COALESCE(q->>'allocated_at',r.state->>'created_at')::bigint/1000.0) AT TIME ZONE 'UTC')::date;
  IF NEW.account_id IS DISTINCT FROM r.account_id OR NEW.day IS DISTINCT FROM expected_day
    OR NEW.question_id IS DISTINCT FROM (q->>'question_id')::uuid
    OR NEW.release_id IS DISTINCT FROM (q->>'release_id')::uuid THEN
    RAISE EXCEPTION 'Question allocation must match the frozen shootout';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION game_reward_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE s JSONB; trial BOOLEAN; per_answer INTEGER; multiplier INTEGER; total INTEGER; completed BOOLEAN;
BEGIN
  SELECT state,is_trial INTO s,trial FROM game_solo_runs WHERE run_id=NEW.run_id;
  IF trial THEN RAISE EXCEPTION 'Trials cannot earn saved XP or streak credit'; END IF;
  per_answer:=(s->'rules'->>'xp_per_correct')::integer;
  multiplier:=(s->'rules'->'perfect_multipliers'->>(s->>'difficulty'))::integer;
  total:=CASE WHEN s->'rules'->>'format'='shootout' THEN jsonb_array_length(s->'history') ELSE 10 END;
  completed:=s->>'phase'='FINISHED' AND jsonb_array_length(s->'history')=total AND total>0;
  IF s->'rules'->>'format'='shootout' THEN completed:=completed AND game_shootout_winner(s) IS NOT NULL; END IF;
  IF TG_TABLE_NAME='game_daily_activity' THEN
    IF NOT completed OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'option_id' IS NULL)
      OR NEW.day<>(to_timestamp((s->>'finished_at')::bigint/1000.0) AT TIME ZONE 'UTC')::date THEN
      RAISE EXCEPTION 'Daily activity requires a completed game with all answers submitted';
    END IF;
  ELSIF NEW.slot>0 THEN
    IF NEW.amount IS DISTINCT FROM per_answer OR NOT EXISTS(
      SELECT 1 FROM game_solo_answers WHERE run_id=NEW.run_id AND position=NEW.slot AND correct) THEN
      RAISE EXCEPTION 'Answer XP must match the persisted correct answer';
    END IF;
  ELSE
    IF NOT completed OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'correct'<>'true')
      OR NEW.amount IS DISTINCT FROM total*per_answer*(multiplier-1) THEN
      RAISE EXCEPTION 'Perfect bonus must match the actual completed game';
    END IF;
  END IF;
  RETURN NEW;
END $$;
COMMIT;
