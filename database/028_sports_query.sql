BEGIN;

CREATE TABLE trivia_team_aliases (
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    alias TEXT NOT NULL CHECK (length(alias) BETWEEN 1 AND 100),
    PRIMARY KEY (alias, team_id)
);
INSERT INTO trivia_team_aliases(team_id,alias)
SELECT t.team_id, a.alias FROM (VALUES
    (33,'man united'),(33,'man utd'),(33,'mufc'),(33,'united'),
    (34,'newcastle united'),(34,'united'),(48,'west ham'),(48,'united'),
    (62,'sheffield united'),(62,'united'),(63,'leeds'),(63,'united'),
    (47,'spurs'),(47,'tottenham hotspur'),(50,'man city'),(50,'mcfc')
) a(team_id,alias) JOIN teams t USING(team_id);

CREATE TABLE trivia_opponent_groups (
    group_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    label TEXT NOT NULL,
    league_id INTEGER NOT NULL,
    team_ids INTEGER[] NOT NULL CHECK (cardinality(team_ids) BETWEEN 2 AND 100),
    PRIMARY KEY (group_key, version)
);
INSERT INTO trivia_opponent_groups VALUES ('big_6',1,'Big 6',39,ARRAY[33,40,42,47,49,50]);
CREATE FUNCTION trivia_query_definition_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Query group definitions are immutable; insert a new version';
END $$;
CREATE TRIGGER trivia_query_group_immutable BEFORE UPDATE OR DELETE ON trivia_opponent_groups
    FOR EACH ROW EXECUTE FUNCTION trivia_query_definition_guard();

CREATE TABLE trivia_unrecognized_queries (
    query_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dataset_id UUID NOT NULL REFERENCES trivia_datasets(dataset_id),
    parser_version TEXT NOT NULL,
    query_text TEXT NOT NULL CHECK (length(query_text) BETWEEN 1 AND 1000),
    recognized JSONB NOT NULL,
    issues JSONB NOT NULL
);
CREATE INDEX trivia_unrecognized_created ON trivia_unrecognized_queries(created_at);

ALTER TABLE trivia_templates DROP CONSTRAINT trivia_templates_answer_kind_check;
ALTER TABLE trivia_templates ADD CONSTRAINT trivia_templates_answer_kind_check
    CHECK (answer_kind IN ('percentage','integer','entity','decimal'));
INSERT INTO trivia_templates VALUES
    ('loss_rate',1,'Loss rate','result','percentage'),
    ('draw_rate',1,'Draw rate','result','percentage'),
    ('goals_per_game',1,'Goals per game','result','decimal'),
    ('points_per_game',1,'Points per game','result','decimal'),
    ('goals_conceded',1,'Goals conceded','result','integer'),
    ('clean_sheets',1,'Clean sheets','result','integer');

COMMIT;
