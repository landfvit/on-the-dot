BEGIN;
SET LOCAL lock_timeout='5s';

-- A local football-ID catalogue, independent of user-facing names and avatars.
CREATE TABLE game_clubs(team_id INTEGER PRIMARY KEY, name TEXT NOT NULL, season INTEGER NOT NULL);
INSERT INTO game_clubs
SELECT team_id,teams.team_name,season FROM (
  SELECT home_team_id team_id,season FROM fixtures
  WHERE league_id=39 AND season=(SELECT max(season) FROM fixtures WHERE league_id=39)
  UNION
  SELECT away_team_id,season FROM fixtures
  WHERE league_id=39 AND season=(SELECT max(season) FROM fixtures WHERE league_id=39)
) members JOIN teams USING(team_id);
ALTER TABLE game_accounts ADD COLUMN club_id INTEGER REFERENCES game_clubs(team_id);

-- Only real shootouts have a sporting win/loss. Old fixed quizzes retain XP,
-- but are not retroactively labelled wins. Closing the tab cannot avoid a loss:
-- expired active runs count at their frozen expiry even before the next request.
CREATE VIEW game_match_results AS
SELECT run_id,account_id,
  state->>'phase'='FINISHED' AND game_shootout_winner(state)='player' won,
  CASE WHEN state->>'phase' IN ('FINISHED','ABANDONED') THEN
    to_timestamp((state->>'finished_at')::bigint/1000.0)
  ELSE to_timestamp(((state->>'created_at')::bigint+(state->'rules'->>'max_run_ms')::bigint)/1000.0) END finished_at
FROM game_solo_runs
WHERE NOT is_trial AND state->'rules'->>'format'='shootout'
  AND (state->>'phase' IN ('FINISHED','ABANDONED') OR
       (state->>'created_at')::bigint+(state->'rules'->>'max_run_ms')::bigint <= EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)*1000);

ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_ledger_reason_check;
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_ledger_reason_check CHECK(reason IN ('correct_answer','perfect_bonus','win_bonus'));
ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_slot_amount;
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_slot_amount CHECK(
 (slot=0 AND reason IN ('perfect_bonus','win_bonus')) OR
 (slot>0 AND reason='correct_answer' AND amount IN (10,20,30)));

CREATE OR REPLACE FUNCTION game_reward_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE s JSONB; trial BOOLEAN; per_answer INTEGER; multiplier INTEGER; total INTEGER; completed BOOLEAN; win_mode BOOLEAN;
BEGIN
 SELECT state,is_trial INTO s,trial FROM game_solo_runs WHERE run_id=NEW.run_id;
 IF trial THEN RAISE EXCEPTION 'Trials cannot earn saved XP or streak credit'; END IF;
 per_answer:=(s->'rules'->>'xp_per_correct')::integer;
 win_mode:=COALESCE(s->'rules'->>'bonus_mode'='win',false);
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
 ELSIF win_mode THEN
   multiplier:=(s->'rules'->'win_multipliers'->>(s->>'difficulty'))::integer;
   SELECT count(*) INTO total FROM jsonb_array_elements(s->'history') a WHERE (a->>'correct')::boolean;
   IF NOT completed OR game_shootout_winner(s) IS DISTINCT FROM 'player' OR NEW.reason<>'win_bonus'
      OR NEW.amount IS DISTINCT FROM total*per_answer*(multiplier-1) THEN
     RAISE EXCEPTION 'Win bonus requires a won shootout and its frozen multiplier';
   END IF;
 ELSE
   multiplier:=(s->'rules'->'perfect_multipliers'->>(s->>'difficulty'))::integer;
   IF NOT completed OR NEW.reason<>'perfect_bonus' OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'correct'<>'true')
      OR NEW.amount IS DISTINCT FROM total*per_answer*(multiplier-1) THEN
     RAISE EXCEPTION 'Perfect bonus must match the actual completed legacy game';
   END IF;
 END IF;
 RETURN NEW;
END $$;
COMMIT;
