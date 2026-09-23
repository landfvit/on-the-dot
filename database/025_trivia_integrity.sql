BEGIN;

CREATE TABLE IF NOT EXISTS trivia_schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS trivia_competition_rules (
    league_id INTEGER NOT NULL,
    first_season INTEGER NOT NULL,
    last_season INTEGER NOT NULL CHECK (last_season >= first_season),
    team_count INTEGER NOT NULL CHECK (team_count > 1),
    meetings_per_pair INTEGER NOT NULL CHECK (meetings_per_pair = 2),
    description TEXT NOT NULL,
    PRIMARY KEY (league_id, first_season)
);
INSERT INTO trivia_competition_rules VALUES
    (39, 1995, 2026, 20, 2, 'Premier League: 20 clubs, home and away; extend only after checking competition format')
ON CONFLICT DO NOTHING;

ALTER TABLE trivia_question_versions ADD COLUMN IF NOT EXISTS analysis JSONB NOT NULL DEFAULT '{}';
ALTER TABLE trivia_question_versions ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE trivia_question_versions ADD COLUMN IF NOT EXISTS verified_by TEXT;
ALTER TABLE trivia_question_versions ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE trivia_datasets ADD COLUMN IF NOT EXISTS sealed_at TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION trivia_frozen_fact_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Trivia snapshot facts are immutable; build another dataset';
    END IF;
    PERFORM 1 FROM trivia_datasets WHERE dataset_id=NEW.dataset_id AND sealed_at IS NULL FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cannot append facts to a sealed or missing trivia dataset';
    END IF;
    RETURN NEW;
END $$;

DO $$ DECLARE table_name TEXT; BEGIN
    FOREACH table_name IN ARRAY ARRAY['trivia_match_data_quality','trivia_match_team_facts',
        'trivia_match_state_intervals','trivia_match_player_facts','trivia_event_facts','trivia_player_data_quality'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trivia_frozen_fact ON %I', table_name);
        EXECUTE format('CREATE TRIGGER trivia_frozen_fact BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION trivia_frozen_fact_guard()', table_name);
    END LOOP;
END $$;

UPDATE trivia_datasets SET sealed_at=NOW() WHERE sealed_at IS NULL;
CREATE OR REPLACE FUNCTION trivia_dataset_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' OR OLD.sealed_at IS NOT NULL OR
       (to_jsonb(NEW)-'sealed_at') IS DISTINCT FROM (to_jsonb(OLD)-'sealed_at') THEN
        RAISE EXCEPTION 'Trivia datasets are immutable; only an initial seal is allowed';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trivia_dataset_frozen ON trivia_datasets;
CREATE TRIGGER trivia_dataset_frozen BEFORE UPDATE OR DELETE ON trivia_datasets
    FOR EACH ROW EXECUTE FUNCTION trivia_dataset_guard();

CREATE OR REPLACE FUNCTION trivia_version_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'Question revisions cannot be deleted';
    END IF;
    IF (to_jsonb(NEW)-ARRAY['state','published_at','verified_at','verified_by']) IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['state','published_at','verified_at','verified_by']) THEN
        RAISE EXCEPTION 'Question content is immutable; create a new revision';
    END IF;
    IF (OLD.state='retired' AND NEW.state<>'retired') OR (OLD.state='published' AND NEW.state='draft') THEN
        RAISE EXCEPTION 'Invalid question state transition';
    END IF;
    IF NEW.state='published' AND (NEW.verified_at IS NULL OR NEW.verified_by IS NULL OR
        NEW.coverage->>'publishable' IS DISTINCT FROM 'true' OR NEW.analysis->>'policy_version' IS NULL) THEN
        RAISE EXCEPTION 'Publication requires an audited question revision';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trivia_version_frozen ON trivia_question_versions;
CREATE TRIGGER trivia_version_frozen BEFORE UPDATE OR DELETE ON trivia_question_versions
    FOR EACH ROW EXECUTE FUNCTION trivia_version_guard();

CREATE OR REPLACE FUNCTION trivia_evidence_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Question evidence is immutable';
    END IF;
    PERFORM 1 FROM trivia_question_versions WHERE version_id=NEW.version_id AND state='draft' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Evidence can only be added to a draft'; END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trivia_evidence_frozen ON trivia_evidence;
CREATE TRIGGER trivia_evidence_frozen BEFORE INSERT OR UPDATE OR DELETE ON trivia_evidence
    FOR EACH ROW EXECUTE FUNCTION trivia_evidence_guard();

CREATE INDEX IF NOT EXISTS trivia_facts_season_audit ON trivia_match_team_facts(dataset_id,league_id,season);
INSERT INTO trivia_schema_migrations(name) VALUES ('025_trivia_integrity') ON CONFLICT DO NOTHING;
COMMIT;
