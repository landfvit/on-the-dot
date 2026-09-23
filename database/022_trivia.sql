BEGIN;

CREATE TABLE IF NOT EXISTS trivia_datasets (
    dataset_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    engine_version TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    summary JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS trivia_match_data_quality (
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    fixture_id BIGINT NOT NULL,
    result_valid BOOLEAN NOT NULL,
    timeline_valid BOOLEAN NOT NULL,
    reasons JSONB NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY (dataset_id, fixture_id)
);

CREATE TABLE IF NOT EXISTS trivia_match_team_facts (
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    fixture_id BIGINT NOT NULL,
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    match_date TIMESTAMPTZ NOT NULL,
    team_id INTEGER NOT NULL,
    team_name TEXT NOT NULL,
    opponent_id INTEGER NOT NULL,
    opponent_name TEXT NOT NULL,
    is_home BOOLEAN NOT NULL,
    goals_for INTEGER,
    goals_against INTEGER,
    result CHAR(1) CHECK (result IN ('W','D','L')),
    status TEXT NOT NULL,
    PRIMARY KEY (dataset_id, fixture_id, team_id),
    FOREIGN KEY (dataset_id, fixture_id) REFERENCES trivia_match_data_quality(dataset_id, fixture_id)
);
CREATE INDEX IF NOT EXISTS trivia_facts_scope ON trivia_match_team_facts(dataset_id, league_id, team_id, season, match_date);

CREATE TABLE IF NOT EXISTS trivia_match_state_intervals (
    dataset_id UUID NOT NULL,
    fixture_id BIGINT NOT NULL,
    start_key INTEGER NOT NULL,
    end_key INTEGER NOT NULL CHECK (end_key > start_key),
    home_goals INTEGER NOT NULL CHECK (home_goals >= 0),
    away_goals INTEGER NOT NULL CHECK (away_goals >= 0),
    PRIMARY KEY (dataset_id, fixture_id, start_key),
    FOREIGN KEY (dataset_id, fixture_id) REFERENCES trivia_match_data_quality(dataset_id, fixture_id)
);

CREATE TABLE IF NOT EXISTS trivia_templates (
    template_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    label TEXT NOT NULL,
    required_quality TEXT NOT NULL CHECK (required_quality IN ('result', 'timeline')),
    answer_kind TEXT NOT NULL CHECK (answer_kind IN ('percentage', 'integer')),
    PRIMARY KEY (template_key, version)
);
INSERT INTO trivia_templates VALUES
    ('conditional_win_rate',1,'Win rate at a score checkpoint','timeline','percentage'),
    ('win_rate',1,'Win rate','result','percentage'),
    ('total_wins',1,'Number of wins','result','integer'),
    ('total_goals',1,'Goals scored','result','integer')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS trivia_questions (
    question_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS trivia_question_versions (
    version_id UUID PRIMARY KEY,
    question_id UUID NOT NULL REFERENCES trivia_questions(question_id),
    revision INTEGER NOT NULL,
    template_key TEXT NOT NULL,
    template_version INTEGER NOT NULL DEFAULT 1,
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    specification JSONB NOT NULL,
    question_text TEXT NOT NULL,
    answer JSONB NOT NULL,
    coverage JSONB NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','published','retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    UNIQUE (question_id, revision),
    FOREIGN KEY (template_key, template_version) REFERENCES trivia_templates(template_key, version)
);
CREATE TABLE IF NOT EXISTS trivia_evidence (
    version_id UUID NOT NULL REFERENCES trivia_question_versions(version_id),
    fixture_id BIGINT NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('matched','not_matched','excluded')),
    evidence JSONB NOT NULL,
    PRIMARY KEY (version_id, fixture_id)
);

COMMIT;
