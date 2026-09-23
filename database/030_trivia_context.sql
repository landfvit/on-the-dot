BEGIN;
CREATE TABLE trivia_context_snapshots (
    context_id UUID PRIMARY KEY,
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_hash TEXT NOT NULL,
    method TEXT NOT NULL,
    summary JSONB NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE(dataset_id,source_hash)
);
CREATE INDEX trivia_context_dataset ON trivia_context_snapshots(dataset_id,created_at DESC);
CREATE TRIGGER trivia_context_immutable BEFORE UPDATE OR DELETE ON trivia_context_snapshots
    FOR EACH ROW EXECUTE FUNCTION trivia_query_definition_guard();
INSERT INTO trivia_templates VALUES ('kit_colour',1,'Kit shirt colour','result','entity') ON CONFLICT DO NOTHING;
ALTER TABLE trivia_query_annotations DROP CONSTRAINT trivia_query_annotations_label_check;
ALTER TABLE trivia_query_annotations ADD CONSTRAINT trivia_query_annotations_label_check CHECK
    (label IN ('win_rate','loss_rate','draw_rate','total_wins','total_goals','goals_conceded',
    'goals_per_game','points_per_game','clean_sheets','unsupported','ambiguous','kit_colour','historical_weather'));
COMMIT;
