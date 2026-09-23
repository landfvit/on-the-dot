BEGIN;
CREATE TABLE trivia_query_families (
    family_key TEXT PRIMARY KEY CHECK (length(family_key) BETWEEN 1 AND 80),
    split TEXT NOT NULL CHECK (split IN ('train','validation','test'))
);
CREATE TRIGGER trivia_query_family_immutable BEFORE UPDATE OR DELETE ON trivia_query_families
    FOR EACH ROW EXECUTE FUNCTION trivia_query_definition_guard();

CREATE TABLE trivia_query_examples (
    example_id UUID PRIMARY KEY,
    query_text TEXT NOT NULL CHECK (length(query_text) BETWEEN 1 AND 1000),
    normalized_text TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE trivia_query_annotations (
    annotation_id UUID PRIMARY KEY,
    example_id UUID NOT NULL REFERENCES trivia_query_examples(example_id),
    revision INTEGER NOT NULL CHECK (revision>0),
    family_key TEXT NOT NULL REFERENCES trivia_query_families(family_key),
    phrase TEXT NOT NULL CHECK (length(phrase) BETWEEN 1 AND 300),
    label TEXT NOT NULL CHECK (label IN ('win_rate','loss_rate','draw_rate','total_wins','total_goals',
        'goals_conceded','goals_per_game','points_per_game','clean_sheets','unsupported','ambiguous')),
    note TEXT NOT NULL CHECK (length(note)<=2000),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    UNIQUE(example_id,revision),
    CHECK ((reviewed_by IS NULL)=(reviewed_at IS NULL))
);
CREATE FUNCTION trivia_annotation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.reviewed_at IS NOT NULL THEN RAISE EXCEPTION 'Annotations must start unreviewed'; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP='DELETE' OR OLD.reviewed_at IS NOT NULL OR
       (to_jsonb(NEW)-'reviewed_by'-'reviewed_at') IS DISTINCT FROM (to_jsonb(OLD)-'reviewed_by'-'reviewed_at')
       OR NEW.reviewed_at IS NULL THEN
        RAISE EXCEPTION 'Append a new annotation revision';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trivia_annotation_immutable BEFORE INSERT OR UPDATE OR DELETE ON trivia_query_annotations
    FOR EACH ROW EXECUTE FUNCTION trivia_annotation_guard();
CREATE TRIGGER trivia_query_example_immutable BEFORE UPDATE OR DELETE ON trivia_query_examples
    FOR EACH ROW EXECUTE FUNCTION trivia_query_definition_guard();

CREATE TABLE trivia_query_model_runs (
    model_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dataset_hash TEXT NOT NULL,
    corpus JSONB NOT NULL,
    manifest JSONB NOT NULL,
    report JSONB NOT NULL,
    artifact JSONB NOT NULL
);
CREATE TRIGGER trivia_query_model_immutable BEFORE UPDATE OR DELETE ON trivia_query_model_runs
    FOR EACH ROW EXECUTE FUNCTION trivia_query_definition_guard();
COMMIT;
