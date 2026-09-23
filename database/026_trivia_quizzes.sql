BEGIN;
CREATE TABLE IF NOT EXISTS trivia_quizzes (
    quiz_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS trivia_quiz_versions (
    version_id UUID PRIMARY KEY,
    quiz_id UUID NOT NULL REFERENCES trivia_quizzes,
    revision INTEGER NOT NULL CHECK (revision > 0),
    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 160),
    description TEXT NOT NULL DEFAULT '' CHECK (length(description) <= 1000),
    state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','published','retired')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    UNIQUE (quiz_id, revision)
);
CREATE TABLE IF NOT EXISTS trivia_quiz_questions (
    quiz_version_id UUID NOT NULL REFERENCES trivia_quiz_versions(version_id),
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 50),
    question_version_id UUID NOT NULL REFERENCES trivia_question_versions(version_id),
    PRIMARY KEY (quiz_version_id, position),
    UNIQUE (quiz_version_id, question_version_id),
    UNIQUE (quiz_version_id, position, question_version_id)
);
CREATE TABLE IF NOT EXISTS trivia_quiz_attempts (
    attempt_id UUID PRIMARY KEY,
    quiz_version_id UUID NOT NULL REFERENCES trivia_quiz_versions(version_id),
    token_hash TEXT NOT NULL CHECK (length(token_hash)=64),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '14 days',
    finished_at TIMESTAMPTZ,
    UNIQUE (attempt_id, quiz_version_id)
);
CREATE TABLE IF NOT EXISTS trivia_attempt_answers (
    attempt_id UUID NOT NULL,
    quiz_version_id UUID NOT NULL,
    position INTEGER NOT NULL,
    question_version_id UUID NOT NULL,
    response JSONB NOT NULL,
    correct BOOLEAN NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (attempt_id, position),
    FOREIGN KEY (attempt_id, quiz_version_id) REFERENCES trivia_quiz_attempts(attempt_id, quiz_version_id),
    FOREIGN KEY (quiz_version_id, position, question_version_id)
        REFERENCES trivia_quiz_questions(quiz_version_id, position, question_version_id)
);
CREATE INDEX IF NOT EXISTS trivia_attempts_quiz ON trivia_quiz_attempts(quiz_version_id,started_at);

CREATE OR REPLACE FUNCTION trivia_quiz_version_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Quiz revisions cannot be deleted'; END IF;
    IF (to_jsonb(NEW)-ARRAY['state','published_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['state','published_at'])
       OR (OLD.state='retired' AND NEW.state<>'retired') OR (OLD.state='published' AND NEW.state='draft') THEN
        RAISE EXCEPTION 'Quiz revisions are immutable';
    END IF;
    IF NEW.state='published' AND (NOT EXISTS(SELECT 1 FROM trivia_quiz_questions WHERE quiz_version_id=NEW.version_id)
        OR EXISTS(SELECT 1 FROM trivia_quiz_questions x JOIN trivia_question_versions q ON q.version_id=x.question_version_id
            WHERE x.quiz_version_id=NEW.version_id AND (q.state<>'published' OR q.verified_at IS NULL))) THEN
        RAISE EXCEPTION 'A quiz requires verified, published questions';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trivia_quiz_version_frozen ON trivia_quiz_versions;
CREATE TRIGGER trivia_quiz_version_frozen BEFORE UPDATE OR DELETE ON trivia_quiz_versions
    FOR EACH ROW EXECUTE FUNCTION trivia_quiz_version_guard();

CREATE OR REPLACE FUNCTION trivia_quiz_item_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Quiz question order is immutable'; END IF;
    PERFORM 1 FROM trivia_quiz_versions WHERE version_id=NEW.quiz_version_id AND state='draft' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Only draft quizzes accept questions'; END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trivia_quiz_item_frozen ON trivia_quiz_questions;
CREATE TRIGGER trivia_quiz_item_frozen BEFORE INSERT OR UPDATE OR DELETE ON trivia_quiz_questions
    FOR EACH ROW EXECUTE FUNCTION trivia_quiz_item_guard();

CREATE OR REPLACE FUNCTION trivia_attempt_answer_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Submitted answers are immutable'; END IF;
    PERFORM 1 FROM trivia_quiz_attempts WHERE attempt_id=NEW.attempt_id AND finished_at IS NULL
        AND expires_at>NOW() FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Attempt is closed or expired'; END IF;
    IF NEW.position <> (SELECT COUNT(*)+1 FROM trivia_attempt_answers WHERE attempt_id=NEW.attempt_id) THEN
        RAISE EXCEPTION 'Answers must be submitted in order';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trivia_attempt_answer_frozen ON trivia_attempt_answers;
CREATE TRIGGER trivia_attempt_answer_frozen BEFORE INSERT OR UPDATE OR DELETE ON trivia_attempt_answers
    FOR EACH ROW EXECUTE FUNCTION trivia_attempt_answer_guard();
INSERT INTO trivia_schema_migrations(name) VALUES ('026_trivia_quizzes') ON CONFLICT DO NOTHING;
COMMIT;
