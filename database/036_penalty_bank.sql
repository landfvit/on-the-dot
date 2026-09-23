BEGIN;
CREATE TABLE penalty_bank_releases (
    release_id UUID PRIMARY KEY,
    validation_run_id UUID NOT NULL REFERENCES trivia_bank_validation_runs(run_id),
    choice_version TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    reference_answers_approved BOOLEAN NOT NULL CHECK(reference_answers_approved),
    question_count INTEGER NOT NULL CHECK(question_count>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(validation_run_id,choice_version)
);
CREATE TABLE penalty_bank_questions (
    release_id UUID NOT NULL REFERENCES penalty_bank_releases(release_id),
    question_id UUID NOT NULL REFERENCES trivia_bank_questions(question_id),
    section_code TEXT NOT NULL CHECK(section_code ~ '^[A-Z]{3}$' AND section_code<>'ALL'),
    section_name TEXT NOT NULL,
    question JSONB NOT NULL CHECK(question ?& ARRAY['text','options','correct','explanation','authority','validation_status','source','key']),
    PRIMARY KEY(release_id,question_id),
    CHECK(jsonb_array_length(question->'options')=4),
    CHECK(question->>'correct' IN ('0','1','2','3')),
    CHECK(question->>'validation_status'<>'conflict')
);
CREATE INDEX penalty_bank_sections ON penalty_bank_questions(release_id,section_code);
CREATE TRIGGER penalty_release_frozen BEFORE UPDATE OR DELETE ON penalty_bank_releases
    FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
CREATE TRIGGER penalty_bank_question_frozen BEFORE UPDATE OR DELETE ON penalty_bank_questions
    FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
CREATE FUNCTION penalty_bank_release_complete() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT count(*) FROM penalty_bank_questions WHERE release_id=NEW.release_id)<>NEW.question_count THEN
        RAISE EXCEPTION 'Penalty release must contain its entire question set';
    END IF;
    RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER penalty_bank_complete AFTER INSERT ON penalty_bank_releases
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION penalty_bank_release_complete();
CREATE FUNCTION penalty_bank_question_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE item JSONB; audit JSONB; correct_text TEXT;
BEGIN
    SELECT q.content,c.result INTO item,audit FROM trivia_bank_questions q
        JOIN trivia_bank_checks c USING(question_id)
        JOIN penalty_bank_releases r ON r.validation_run_id=c.run_id
        WHERE r.release_id=NEW.release_id AND q.question_id=NEW.question_id;
    IF item IS NULL OR audit->>'status'='conflict' OR (audit->>'status'='ambiguous'
        AND audit->>'reason' NOT LIKE 'Database player found, but reference name%') THEN
        RAISE EXCEPTION 'Question is not eligible in this audited release';
    END IF;
    SELECT choice->>'text' INTO correct_text FROM jsonb_array_elements(NEW.question->'options') choice
        WHERE choice->>'id'=NEW.question->>'correct';
    IF correct_text IS DISTINCT FROM item->>'answer' OR NEW.question->>'text' IS DISTINCT FROM item->>'question'
        OR NEW.section_name IS DISTINCT FROM item->>'section'
        OR NEW.section_code IS DISTINCT FROM split_part(item->>'id','-',1)
        OR NEW.question->>'validation_status' IS DISTINCT FROM audit->>'status'
        OR NEW.question->>'authority' IS DISTINCT FROM (CASE WHEN audit->>'status'='matched' THEN 'database_matched' ELSE 'user_attested' END)
        OR (SELECT count(DISTINCT choice->>'id') FROM jsonb_array_elements(NEW.question->'options') choice)<>4
        OR (SELECT count(DISTINCT lower(choice->>'text')) FROM jsonb_array_elements(NEW.question->'options') choice)<>4
        OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.question->'options') choice WHERE choice->>'id' NOT IN ('0','1','2','3')) THEN
        RAISE EXCEPTION 'Penalty choices must retain exactly one canonical reference answer and audit status';
    END IF;
    PERFORM 1 FROM penalty_bank_releases WHERE release_id=NEW.release_id FOR UPDATE;
    IF (SELECT count(*) FROM penalty_bank_questions WHERE release_id=NEW.release_id)>=
       (SELECT question_count FROM penalty_bank_releases WHERE release_id=NEW.release_id) THEN
        RAISE EXCEPTION 'Penalty release is already complete';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER penalty_bank_question_valid BEFORE INSERT ON penalty_bank_questions
    FOR EACH ROW EXECUTE FUNCTION penalty_bank_question_guard();
COMMIT;
