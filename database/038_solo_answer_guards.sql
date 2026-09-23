BEGIN;
CREATE FUNCTION game_solo_answer_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE s JSONB; q JSONB; a JSONB;
BEGIN
    SELECT state INTO s FROM game_solo_runs WHERE run_id=NEW.run_id;
    q:=s->'deck'->(NEW.position-1);
    a:=s->'history'->(NEW.position-1);
    IF a IS NULL OR q IS NULL
       OR NEW.release_id IS DISTINCT FROM (q->>'release_id')::uuid
       OR NEW.question_id IS DISTINCT FROM (q->>'question_id')::uuid
       OR NEW.difficulty_revision IS DISTINCT FROM (q->>'difficulty_revision')::bigint
       OR NEW.option_id IS DISTINCT FROM a->>'option_id'
       OR NEW.request_id IS DISTINCT FROM (a->>'request_id')::uuid
       OR NEW.correct IS DISTINCT FROM (a->>'correct')::boolean
       OR NEW.correct IS DISTINCT FROM (NEW.option_id IS NOT NULL AND NEW.option_id=q->>'correct')
       OR NEW.elapsed_ms IS DISTINCT FROM (a->>'elapsed_ms')::integer
       OR NEW.answered_at IS DISTINCT FROM to_timestamp((a->>'answered_at')::bigint/1000.0)
       OR (NEW.option_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(q->'options') o WHERE o->>'id'=NEW.option_id)) THEN
        RAISE EXCEPTION 'Solo answer must match the frozen question and resolved event';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_answer_valid BEFORE INSERT ON game_solo_answers FOR EACH ROW EXECUTE FUNCTION game_solo_answer_guard();
CREATE FUNCTION game_history_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF jsonb_array_length(NEW.state->'history')<jsonb_array_length(OLD.state->'history')
       OR EXISTS(SELECT 1 FROM generate_series(0,jsonb_array_length(OLD.state->'history')-1) n
                 WHERE NEW.state->'history'->n IS DISTINCT FROM OLD.state->'history'->n) THEN
        RAISE EXCEPTION 'Resolved solo events cannot be rewritten';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_history_frozen BEFORE UPDATE ON game_solo_runs FOR EACH ROW EXECUTE FUNCTION game_history_guard();
COMMIT;
