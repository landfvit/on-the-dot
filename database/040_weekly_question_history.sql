BEGIN;

LOCK TABLE game_solo_runs IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE IF NOT EXISTS game_question_history (
    account_id UUID NOT NULL,
    week_start DATE NOT NULL,
    day DATE NOT NULL,
    question_id UUID NOT NULL,
    release_id UUID NOT NULL,
    run_id UUID NOT NULL,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 10),
    PRIMARY KEY (account_id, week_start, question_id),
    UNIQUE (run_id, position),
    FOREIGN KEY (run_id, account_id) REFERENCES game_solo_runs(run_id, account_id),
    FOREIGN KEY (release_id, question_id) REFERENCES penalty_bank_questions(release_id, question_id),
    CHECK (week_start = day - (EXTRACT(ISODOW FROM day)::INTEGER - 1))
);

-- Legacy repeats retain their first allocation each week; frozen runs retain all evidence.
INSERT INTO game_question_history(account_id, week_start, day, question_id, release_id, run_id, position)
SELECT DISTINCT ON (account_id, week_start, question_id)
    account_id, week_start, day, question_id, release_id, run_id, position
FROM (
    SELECT r.account_id, r.run_id, q.position::INTEGER,
        (q.item->>'question_id')::UUID question_id,
        (q.item->>'release_id')::UUID release_id,
        (to_timestamp((r.state->>'created_at')::BIGINT / 1000.0) AT TIME ZONE 'UTC')::DATE AS day,
        date_trunc('week', to_timestamp((r.state->>'created_at')::BIGINT / 1000.0) AT TIME ZONE 'UTC')::DATE week_start,
        (r.state->>'created_at')::BIGINT created_ms
    FROM game_solo_runs r CROSS JOIN LATERAL jsonb_array_elements(r.state->'deck') WITH ORDINALITY q(item, position)
) allocations
ORDER BY account_id, week_start, question_id, created_ms, run_id, position
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION game_question_history_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE r game_solo_runs; expected_day DATE; q JSONB;
BEGIN
    SELECT * INTO STRICT r FROM game_solo_runs WHERE run_id = NEW.run_id;
    expected_day := (to_timestamp((r.state->>'created_at')::BIGINT / 1000.0) AT TIME ZONE 'UTC')::DATE;
    q := r.state->'deck'->(NEW.position - 1);
    IF NEW.account_id IS DISTINCT FROM r.account_id OR NEW.day IS DISTINCT FROM expected_day
       OR NEW.question_id IS DISTINCT FROM (q->>'question_id')::UUID
       OR NEW.release_id IS DISTINCT FROM (q->>'release_id')::UUID THEN
        RAISE EXCEPTION 'Question allocation must match the frozen quiz';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS game_question_history_validate ON game_question_history;
CREATE TRIGGER game_question_history_validate BEFORE INSERT ON game_question_history
FOR EACH ROW EXECUTE FUNCTION game_question_history_guard();
DROP TRIGGER IF EXISTS game_question_history_immutable ON game_question_history;
CREATE TRIGGER game_question_history_immutable BEFORE UPDATE OR DELETE ON game_question_history
FOR EACH ROW EXECUTE FUNCTION pvp_immutable();

CREATE OR REPLACE FUNCTION game_allocate_questions() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE allocated_day DATE;
BEGIN
    allocated_day := (to_timestamp((NEW.state->>'created_at')::BIGINT / 1000.0) AT TIME ZONE 'UTC')::DATE;
    INSERT INTO game_question_history(account_id, week_start, day, question_id, release_id, run_id, position)
    SELECT NEW.account_id, allocated_day - (EXTRACT(ISODOW FROM allocated_day)::INTEGER - 1),
        allocated_day, (q.item->>'question_id')::UUID, (q.item->>'release_id')::UUID,
        NEW.run_id, q.position::INTEGER
    FROM jsonb_array_elements(NEW.state->'deck') WITH ORDINALITY q(item, position);
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS game_allocate_questions ON game_solo_runs;
CREATE TRIGGER game_allocate_questions AFTER INSERT ON game_solo_runs
FOR EACH ROW EXECUTE FUNCTION game_allocate_questions();

COMMIT;
