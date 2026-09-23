BEGIN;
ALTER TABLE trivia_bank_questions ADD CONSTRAINT bank_question_content CHECK (
    content->>'id'=external_id AND jsonb_typeof(content->'answer')='string'
    AND length(content->>'answer')>0 AND jsonb_typeof(content->'question')='string'
    AND length(content->>'question')>0
);
ALTER TABLE trivia_bank_checks ADD CONSTRAINT bank_check_status_matches CHECK (
    result ? 'status' AND result->>'status'=status
);
CREATE FUNCTION trivia_bank_insert_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE r trivia_bank_validation_runs; n INTEGER;
BEGIN
    IF TG_TABLE_NAME='trivia_bank_validation_runs' THEN
        IF NOT EXISTS(SELECT 1 FROM trivia_datasets WHERE dataset_id=NEW.dataset_id AND sealed_at IS NOT NULL) THEN
            RAISE EXCEPTION 'Bank validation requires a sealed dataset';
        END IF;
        SELECT count(*) INTO n FROM trivia_bank_questions WHERE batch_id=NEW.batch_id;
        IF n<>(SELECT question_count FROM trivia_bank_batches WHERE batch_id=NEW.batch_id) THEN
            RAISE EXCEPTION 'Incomplete imported question batch';
        END IF;
    ELSIF TG_TABLE_NAME='trivia_bank_checks' THEN
        SELECT * INTO r FROM trivia_bank_validation_runs WHERE run_id=NEW.run_id;
        IF NOT EXISTS(SELECT 1 FROM trivia_bank_questions WHERE question_id=NEW.question_id AND batch_id=r.batch_id) THEN
            RAISE EXCEPTION 'Question belongs to a different bank batch';
        END IF;
    ELSIF TG_TABLE_NAME='trivia_bank_models' THEN
        SELECT * INTO r FROM trivia_bank_validation_runs WHERE run_id=NEW.validation_run_id;
        IF r.batch_id IS DISTINCT FROM NEW.batch_id THEN RAISE EXCEPTION 'Model and audit batch differ'; END IF;
        SELECT count(*) INTO n FROM trivia_bank_checks WHERE run_id=r.run_id;
        IF n<>(SELECT question_count FROM trivia_bank_batches WHERE batch_id=NEW.batch_id) THEN
            RAISE EXCEPTION 'Model requires a completed bank audit';
        END IF;
    ELSIF TG_TABLE_NAME='trivia_bank_authored_drafts' THEN
        IF NEW.calculation->>'status' IS DISTINCT FROM 'calculated' OR NEW.calculation->>'answer' IS NULL THEN
            RAISE EXCEPTION 'Authored draft requires a calculated answer';
        END IF;
        IF NOT EXISTS(SELECT 1 FROM trivia_datasets WHERE dataset_id=NEW.dataset_id AND sealed_at IS NOT NULL) THEN
            RAISE EXCEPTION 'Authored draft requires a sealed dataset';
        END IF;
    END IF;
    RETURN NEW;
END $$;
DO $$ DECLARE t TEXT; BEGIN
    FOREACH t IN ARRAY ARRAY['trivia_bank_validation_runs','trivia_bank_checks','trivia_bank_models','trivia_bank_authored_drafts'] LOOP
        EXECUTE format('CREATE TRIGGER bank_insert_guard BEFORE INSERT ON %I FOR EACH ROW EXECUTE FUNCTION trivia_bank_insert_guard()',t);
    END LOOP;
END $$;
COMMIT;
