BEGIN;
SET LOCAL lock_timeout='5s';
CREATE TABLE game_question_submissions (
 submission_id UUID PRIMARY KEY,
 owner_id UUID NOT NULL REFERENCES game_accounts,
 request_id UUID NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 content JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 submitted_at TIMESTAMPTZ,
 reviewed_at TIMESTAMPTZ,
 review_note TEXT NOT NULL DEFAULT '',
 reviewed_by TEXT,
 release_id UUID,
 question_id UUID,
 UNIQUE(owner_id,request_id),
 FOREIGN KEY(release_id,question_id) REFERENCES penalty_bank_questions,
 CHECK((status='approved')=(release_id IS NOT NULL AND question_id IS NOT NULL)),
 CHECK(status NOT IN ('approved','rejected') OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL))
);
CREATE INDEX game_submissions_owner ON game_question_submissions(owner_id,created_at DESC);
CREATE INDEX game_submissions_queue ON game_question_submissions(status,submitted_at);
CREATE TABLE game_question_reviews (
 review_id UUID PRIMARY KEY,
 submission_id UUID NOT NULL REFERENCES game_question_submissions,
 revision INTEGER NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('approved','rejected')),
 content JSONB NOT NULL,
 note TEXT NOT NULL,
 actor TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(submission_id,revision)
);
CREATE TRIGGER game_question_review_frozen BEFORE UPDATE OR DELETE ON game_question_reviews
 FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
CREATE FUNCTION game_submission_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status='approved' OR NEW.owner_id<>OLD.owner_id OR NEW.request_id<>OLD.request_id
    OR NEW.submission_id<>OLD.submission_id OR NEW.created_at<>OLD.created_at
    OR (NEW.content<>OLD.content AND (NEW.revision<>OLD.revision+1 OR NEW.status<>'draft')) THEN
   RAISE EXCEPTION 'Published content and submission identity cannot be changed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER game_submission_valid BEFORE UPDATE ON game_question_submissions
 FOR EACH ROW EXECUTE FUNCTION game_submission_guard();
COMMIT;
