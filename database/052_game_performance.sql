BEGIN;
SET LOCAL lock_timeout='5s';

-- Persist small result fields once per transition. The public view keeps its
-- contract, including abandoned games and expired games never polled again.
ALTER TABLE game_solo_runs
 ADD COLUMN result_eligible BOOLEAN GENERATED ALWAYS AS
   (NOT is_trial AND state->'rules'->>'format'='shootout') STORED,
 ADD COLUMN result_terminal BOOLEAN GENERATED ALWAYS AS
   (state->>'phase' IN ('FINISHED','ABANDONED')) STORED,
 ADD COLUMN result_won BOOLEAN GENERATED ALWAYS AS
   (CASE WHEN state->>'phase'='FINISHED' AND state->'rules'->>'format'='shootout'
     THEN game_shootout_winner(state)='player' ELSE false END) STORED,
 ADD COLUMN result_at_ms BIGINT GENERATED ALWAYS AS
   (CASE WHEN state->>'phase' IN ('FINISHED','ABANDONED') THEN (state->>'finished_at')::bigint
     ELSE (state->>'created_at')::bigint+(state->'rules'->>'max_run_ms')::bigint END) STORED;

CREATE INDEX game_solo_result_summary ON game_solo_runs(account_id,result_at_ms)
 INCLUDE(run_id,result_won,result_terminal) WHERE result_eligible;

CREATE OR REPLACE VIEW game_match_results AS
 SELECT run_id,account_id,result_won won,to_timestamp(result_at_ms/1000.0) finished_at
 FROM game_solo_runs WHERE result_eligible AND
   (result_terminal OR result_at_ms<=EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)*1000);

-- The old guard repeatedly extracted each question from a large toasted JSON
-- document. Compare whole frozen arrays first and inspect prefixes only when
-- appending; snapshot tampering, history edits and terminal edits still fail.
CREATE OR REPLACE FUNCTION game_mode_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE old_deck JSONB; new_deck JSONB; old_history JSONB; new_history JSONB;
BEGIN
 IF NEW.mode<>OLD.mode OR NEW.owner_id<>OLD.owner_id OR NEW.start_request_id<>OLD.start_request_id
    OR NEW.day IS DISTINCT FROM OLD.day OR NEW.invite IS DISTINCT FROM OLD.invite
    OR NEW.state->'rules' IS DISTINCT FROM OLD.state->'rules'
    OR NEW.state->'created_at' IS DISTINCT FROM OLD.state->'created_at'
    OR (OLD.state->>'phase' IN ('FINISHED','ABANDONED') AND NEW.state<>OLD.state) THEN
   RAISE EXCEPTION 'Game identity, resolved events and completed results are frozen';
 END IF;
 old_history:=OLD.state->'history'; new_history:=NEW.state->'history';
 IF new_history IS DISTINCT FROM old_history THEN
   IF jsonb_array_length(new_history)<jsonb_array_length(old_history) OR
      EXISTS(SELECT 1 FROM generate_series(0,jsonb_array_length(old_history)-1) n
             WHERE new_history->n IS DISTINCT FROM old_history->n) THEN
     RAISE EXCEPTION 'Resolved events are frozen';
   END IF;
 END IF;
 IF OLD.state->>'phase'<>'LOBBY' THEN
   old_deck:=OLD.state->'deck'; new_deck:=NEW.state->'deck';
   IF new_deck IS DISTINCT FROM old_deck THEN
     IF jsonb_array_length(new_deck)<jsonb_array_length(old_deck) OR
        EXISTS(SELECT 1 FROM generate_series(0,jsonb_array_length(old_deck)-1) n
               WHERE new_deck->n IS DISTINCT FROM old_deck->n) THEN
       RAISE EXCEPTION 'Question snapshots are frozen';
     END IF;
   END IF;
 END IF;
 RETURN NEW;
END $$;
COMMIT;
