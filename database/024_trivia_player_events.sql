BEGIN;

CREATE TABLE IF NOT EXISTS trivia_match_player_facts (
    dataset_id UUID NOT NULL,
    fixture_id BIGINT NOT NULL,
    team_id INTEGER NOT NULL,
    player_id BIGINT NOT NULL,
    player_name TEXT NOT NULL,
    aliases JSONB NOT NULL,
    appeared BOOLEAN NOT NULL,
    role TEXT CHECK (role IN ('starter', 'substitute')),
    statistics JSONB NOT NULL,
    PRIMARY KEY (dataset_id, fixture_id, team_id, player_id),
    FOREIGN KEY (dataset_id, fixture_id) REFERENCES trivia_match_data_quality(dataset_id, fixture_id)
);
CREATE INDEX IF NOT EXISTS trivia_player_scope ON trivia_match_player_facts(dataset_id, player_id, fixture_id);

CREATE TABLE IF NOT EXISTS trivia_event_facts (
    dataset_id UUID NOT NULL,
    fixture_id BIGINT NOT NULL,
    source_order INTEGER NOT NULL,
    team_id INTEGER,
    player_id BIGINT,
    assist_player_id BIGINT,
    player_name TEXT,
    aliases JSONB NOT NULL,
    clock_key INTEGER,
    event_type TEXT,
    event_detail TEXT,
    scorer_role TEXT CHECK (scorer_role IN ('starter', 'substitute')),
    PRIMARY KEY (dataset_id, fixture_id, source_order),
    FOREIGN KEY (dataset_id, fixture_id) REFERENCES trivia_match_data_quality(dataset_id, fixture_id)
);
CREATE INDEX IF NOT EXISTS trivia_goal_scope ON trivia_event_facts(dataset_id, fixture_id, team_id)
    WHERE event_type='Goal';

CREATE TABLE IF NOT EXISTS trivia_player_data_quality (
    dataset_id UUID NOT NULL,
    fixture_id BIGINT NOT NULL,
    scorers_valid BOOLEAN NOT NULL,
    substitutes_valid BOOLEAN NOT NULL,
    reasons JSONB NOT NULL,
    substitute_reasons JSONB NOT NULL,
    PRIMARY KEY (dataset_id, fixture_id),
    FOREIGN KEY (dataset_id, fixture_id) REFERENCES trivia_match_data_quality(dataset_id, fixture_id)
);

ALTER TABLE trivia_templates DROP CONSTRAINT IF EXISTS trivia_templates_answer_kind_check;
ALTER TABLE trivia_templates ADD CONSTRAINT trivia_templates_answer_kind_check
    CHECK (answer_kind IN ('percentage', 'integer', 'entity'));
INSERT INTO trivia_templates VALUES
    ('player_goals',1,'Player scoring total','timeline','integer'),
    ('top_scorer',1,'Leading scorer','timeline','entity'),
    ('comeback_wins',1,'Wins after falling behind','timeline','integer'),
    ('most_comeback_wins',1,'Most comeback wins','timeline','entity')
ON CONFLICT (template_key,version) DO UPDATE SET label=EXCLUDED.label;

COMMIT;
