BEGIN;
CREATE OR REPLACE FUNCTION trivia_initial_draft_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.state<>'draft' OR NEW.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'Content must be inserted as a draft and verified before publication';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trivia_question_initial_draft BEFORE INSERT ON trivia_question_versions
    FOR EACH ROW EXECUTE FUNCTION trivia_initial_draft_guard();
CREATE TRIGGER trivia_quiz_initial_draft BEFORE INSERT ON trivia_quiz_versions
    FOR EACH ROW EXECUTE FUNCTION trivia_initial_draft_guard();

CREATE OR REPLACE FUNCTION trivia_attempt_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Attempts cannot be deleted by normal operations'; END IF;
    IF (to_jsonb(NEW)-'finished_at') IS DISTINCT FROM (to_jsonb(OLD)-'finished_at') OR OLD.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'Attempt identity and completion are immutable';
    END IF;
    IF NEW.finished_at IS NULL OR NEW.finished_at<NEW.started_at OR
        (SELECT COUNT(*) FROM trivia_attempt_answers WHERE attempt_id=NEW.attempt_id) <>
        (SELECT COUNT(*) FROM trivia_quiz_questions WHERE quiz_version_id=NEW.quiz_version_id) THEN
        RAISE EXCEPTION 'An attempt can only finish after every answer';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trivia_attempt_lifecycle BEFORE UPDATE OR DELETE ON trivia_quiz_attempts
    FOR EACH ROW EXECUTE FUNCTION trivia_attempt_guard();
INSERT INTO trivia_schema_migrations(name) VALUES ('027_trivia_lifecycle_guards') ON CONFLICT DO NOTHING;
COMMIT;
