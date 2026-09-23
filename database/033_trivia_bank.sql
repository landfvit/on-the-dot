BEGIN;
CREATE TABLE trivia_bank_batches (
    batch_id UUID PRIMARY KEY,
    source_sha256 TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    source_text TEXT NOT NULL,
    answer_authority TEXT NOT NULL CHECK(answer_authority='user_attested'),
    question_count INTEGER NOT NULL CHECK(question_count>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE trivia_bank_questions (
    question_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES trivia_bank_batches(batch_id),
    external_id TEXT NOT NULL,
    content JSONB NOT NULL,
    UNIQUE(batch_id,external_id)
);
CREATE TABLE trivia_bank_validation_runs (
    run_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES trivia_bank_batches(batch_id),
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    validator_version TEXT NOT NULL,
    inputs JSONB NOT NULL,
    summary JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE trivia_bank_checks (
    run_id UUID NOT NULL REFERENCES trivia_bank_validation_runs(run_id),
    question_id UUID NOT NULL REFERENCES trivia_bank_questions(question_id),
    status TEXT NOT NULL CHECK(status IN ('matched','conflict','incomplete','unsupported','ambiguous')),
    result JSONB NOT NULL,
    PRIMARY KEY(run_id,question_id)
);
CREATE INDEX trivia_bank_check_status ON trivia_bank_checks(run_id,status);
CREATE TABLE trivia_bank_models (
    model_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES trivia_bank_batches(batch_id),
    validation_run_id UUID NOT NULL REFERENCES trivia_bank_validation_runs(run_id),
    corpus JSONB NOT NULL,
    report JSONB NOT NULL,
    artifact JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE trivia_bank_authored_drafts (
    draft_id UUID PRIMARY KEY,
    model_id UUID NOT NULL REFERENCES trivia_bank_models(model_id),
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    question_text TEXT NOT NULL CHECK(length(question_text) BETWEEN 10 AND 1000),
    topic_suggestion TEXT,
    calculation JSONB NOT NULL,
    inputs JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE FUNCTION trivia_bank_immutable() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Bank records are immutable; import or validate a new revision'; END $$;
DO $$ DECLARE t TEXT; BEGIN
    FOREACH t IN ARRAY ARRAY['trivia_bank_batches','trivia_bank_questions','trivia_bank_validation_runs',
        'trivia_bank_checks','trivia_bank_models','trivia_bank_authored_drafts'] LOOP
        EXECUTE format('CREATE TRIGGER bank_immutable BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trivia_bank_immutable()',t);
    END LOOP;
END $$;
COMMIT;
