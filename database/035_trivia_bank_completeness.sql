BEGIN;
ALTER TABLE trivia_bank_questions ADD CONSTRAINT bank_required_content CHECK (
    jsonb_typeof(content)='object' AND content ?& ARRAY['id','question','answer','topic','section','sources','check']
);

CREATE FUNCTION trivia_bank_complete_audit() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE histogram JSONB; n INTEGER;
BEGIN
    SELECT count(*) INTO n FROM trivia_bank_checks WHERE run_id=NEW.run_id;
    IF n<>(SELECT question_count FROM trivia_bank_batches WHERE batch_id=NEW.batch_id) THEN
        RAISE EXCEPTION 'Audit must contain one check for every imported question';
    END IF;
    SELECT jsonb_object_agg(status,total) INTO histogram FROM (
        SELECT status,count(*) AS total FROM trivia_bank_checks WHERE run_id=NEW.run_id GROUP BY status
    ) counts;
    IF NEW.summary IS DISTINCT FROM histogram THEN
        RAISE EXCEPTION 'Audit summary does not match its question checks';
    END IF;
    RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER bank_complete_audit AFTER INSERT ON trivia_bank_validation_runs
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION trivia_bank_complete_audit();

CREATE FUNCTION trivia_bank_batch_frozen() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM trivia_bank_batches WHERE batch_id=NEW.batch_id FOR UPDATE;
    IF EXISTS(SELECT 1 FROM trivia_bank_validation_runs WHERE batch_id=NEW.batch_id) THEN
        RAISE EXCEPTION 'Cannot append questions to an audited batch';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER bank_batch_frozen BEFORE INSERT ON trivia_bank_questions
    FOR EACH ROW EXECUTE FUNCTION trivia_bank_batch_frozen();
COMMIT;
