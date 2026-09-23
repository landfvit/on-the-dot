BEGIN;
DO $$ DECLARE constraint_name TEXT;
BEGIN
    FOR constraint_name IN SELECT conname FROM pg_constraint
        WHERE conrelid='penalty_bank_questions'::regclass AND contype='c'
        AND pg_get_constraintdef(oid) LIKE '%jsonb_array_length%'
    LOOP
        EXECUTE format('ALTER TABLE penalty_bank_questions DROP CONSTRAINT %I',constraint_name);
    END LOOP;
END $$;
ALTER TABLE penalty_bank_questions ADD CONSTRAINT penalty_choice_count
    CHECK(jsonb_array_length(question->'options') BETWEEN 2 AND 4);
CREATE OR REPLACE FUNCTION penalty_bank_question_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE item JSONB; audit JSONB; correct_text TEXT; choice_count INTEGER;
BEGIN
    SELECT q.content,c.result INTO item,audit FROM trivia_bank_questions q
        JOIN trivia_bank_checks c USING(question_id)
        JOIN penalty_bank_releases r ON r.validation_run_id=c.run_id
        WHERE r.release_id=NEW.release_id AND q.question_id=NEW.question_id;
    IF item IS NULL OR audit ? 'publication_exclusion' OR audit->>'status'='conflict' OR (audit->>'status'='ambiguous'
        AND audit->>'reason' NOT LIKE 'Database player found, but reference name%') THEN
        RAISE EXCEPTION 'Question is not eligible in this audited release';
    END IF;
    choice_count=jsonb_array_length(NEW.question->'options');
    SELECT choice->>'text' INTO correct_text FROM jsonb_array_elements(NEW.question->'options') choice
        WHERE choice->>'id'=NEW.question->>'correct';
    IF correct_text IS DISTINCT FROM item->>'answer' OR NEW.question->>'text' IS DISTINCT FROM item->>'question'
        OR NEW.section_name IS DISTINCT FROM item->>'section'
        OR NEW.section_code IS DISTINCT FROM substring(item->>'id' FROM '([A-Z]{3})-[0-9]{3}$')
        OR NEW.question->>'validation_status' IS DISTINCT FROM audit->>'status'
        OR NEW.question->>'authority' IS DISTINCT FROM (CASE WHEN audit->>'status'='matched' THEN 'database_matched' ELSE 'user_attested' END)
        OR (SELECT count(DISTINCT choice->>'id') FROM jsonb_array_elements(NEW.question->'options') choice)<>choice_count
        OR (SELECT count(DISTINCT lower(choice->>'text')) FROM jsonb_array_elements(NEW.question->'options') choice)<>choice_count
        OR EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.question->'options') choice
            WHERE choice->>'id' IS NULL OR choice->>'text' IS NULL OR btrim(choice->>'text')=''
            OR choice->>'id' NOT IN (SELECT i::text FROM generate_series(0,choice_count-1) i)) THEN
        RAISE EXCEPTION 'Penalty choices must retain exactly one canonical reference answer and audit status';
    END IF;
    PERFORM 1 FROM penalty_bank_releases WHERE release_id=NEW.release_id FOR UPDATE;
    IF (SELECT count(*) FROM penalty_bank_questions WHERE release_id=NEW.release_id)>=
       (SELECT question_count FROM penalty_bank_releases WHERE release_id=NEW.release_id) THEN
        RAISE EXCEPTION 'Penalty release is already complete';
    END IF;
    RETURN NEW;
END $$;
COMMIT;
