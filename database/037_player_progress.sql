BEGIN;
CREATE TABLE game_accounts (
    account_id UUID PRIMARY KEY,
    username TEXT UNIQUE NOT NULL CHECK(username ~ '^[a-z0-9_]{3,24}$'),
    password_hash TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT '' CHECK(length(bio)<=160),
    accent TEXT NOT NULL DEFAULT 'green' CHECK(accent IN ('green','pink','blue','gold')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE game_sessions (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
    account_id UUID NOT NULL REFERENCES game_accounts,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '30 days'
);
CREATE INDEX game_session_account ON game_sessions(account_id);
CREATE TABLE game_levels (
    level INTEGER PRIMARY KEY CHECK(level>=1),
    minimum_xp BIGINT UNIQUE NOT NULL CHECK(minimum_xp>=0)
);
INSERT INTO game_levels SELECT n,100::bigint*n*(n-1) FROM generate_series(1,100) n;
CREATE TABLE game_question_difficulty (
    revision_id BIGSERIAL PRIMARY KEY,
    release_id UUID NOT NULL,
    question_id UUID NOT NULL,
    difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),
    reviewed_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY(release_id,question_id) REFERENCES penalty_bank_questions
);
CREATE INDEX game_difficulty_latest ON game_question_difficulty(release_id,question_id,revision_id DESC);
CREATE VIEW game_current_difficulty AS
    SELECT DISTINCT ON(release_id,question_id) * FROM game_question_difficulty
    ORDER BY release_id,question_id,revision_id DESC;
CREATE TABLE game_solo_runs (
    run_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES game_accounts,
    start_request_id UUID NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id,start_request_id),
    UNIQUE(run_id,account_id),
    CHECK(jsonb_array_length(state->'deck')=10),
    CHECK(state->>'phase' IN ('READY','ANSWERING','REVIEW','FINISHED','ABANDONED'))
);
CREATE UNIQUE INDEX game_one_active_run ON game_solo_runs(account_id)
    WHERE state->>'phase' NOT IN ('FINISHED','ABANDONED');
CREATE TABLE game_solo_answers (
    run_id UUID NOT NULL REFERENCES game_solo_runs,
    position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 10),
    request_id UUID,
    release_id UUID NOT NULL,
    question_id UUID NOT NULL,
    difficulty_revision BIGINT NOT NULL REFERENCES game_question_difficulty,
    option_id TEXT CHECK(option_id IN ('0','1','2','3')),
    correct BOOLEAN NOT NULL,
    elapsed_ms INTEGER NOT NULL CHECK(elapsed_ms BETWEEN 0 AND 10000),
    answered_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(run_id,position),
    UNIQUE(run_id,request_id),
    CHECK(option_id IS NOT NULL OR NOT correct),
    FOREIGN KEY(release_id,question_id) REFERENCES penalty_bank_questions
);
CREATE INDEX game_answer_calibration ON game_solo_answers(release_id,question_id,answered_at);
CREATE TABLE game_xp_ledger (
    account_id UUID NOT NULL,
    run_id UUID NOT NULL,
    slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 10),
    amount INTEGER NOT NULL CHECK(amount IN (10,100,200)),
    reason TEXT NOT NULL CHECK(reason IN ('correct_answer','perfect_bonus')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(run_id,slot),
    FOREIGN KEY(run_id,account_id) REFERENCES game_solo_runs(run_id,account_id),
    CHECK((slot=0 AND reason='perfect_bonus' AND amount IN (100,200)) OR
          (slot>0 AND reason='correct_answer' AND amount=10))
);
CREATE INDEX game_xp_account ON game_xp_ledger(account_id);
CREATE TABLE game_daily_activity (
    account_id UUID NOT NULL,
    day DATE NOT NULL,
    run_id UUID NOT NULL,
    PRIMARY KEY(account_id,day),
    FOREIGN KEY(run_id,account_id) REFERENCES game_solo_runs(run_id,account_id)
);
CREATE FUNCTION game_run_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.account_id<>OLD.account_id OR NEW.start_request_id<>OLD.start_request_id
       OR NEW.state->'deck' IS DISTINCT FROM OLD.state->'deck'
       OR NEW.state->'rules' IS DISTINCT FROM OLD.state->'rules'
       OR NEW.state->'difficulty' IS DISTINCT FROM OLD.state->'difficulty'
       OR NEW.state->'category' IS DISTINCT FROM OLD.state->'category'
       OR NEW.state->'created_at' IS DISTINCT FROM OLD.state->'created_at'
       OR (OLD.state->>'phase' IN ('FINISHED','ABANDONED') AND NEW.state<>OLD.state) THEN
        RAISE EXCEPTION 'Solo identity, content, rules and completed results are frozen';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_run_frozen BEFORE UPDATE ON game_solo_runs FOR EACH ROW EXECUTE FUNCTION game_run_guard();
CREATE FUNCTION game_reward_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE s JSONB;
BEGIN
    SELECT state INTO s FROM game_solo_runs WHERE run_id=NEW.run_id;
    IF TG_TABLE_NAME='game_daily_activity' THEN
        IF s->>'phase'<>'FINISHED' OR jsonb_array_length(s->'history')<>10
           OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'option_id' IS NULL)
           OR NEW.day<>(to_timestamp((s->>'finished_at')::bigint/1000.0) AT TIME ZONE 'UTC')::date THEN
            RAISE EXCEPTION 'Daily activity requires ten submitted answers';
        END IF;
    ELSIF NEW.slot>0 THEN
        IF NOT EXISTS(SELECT 1 FROM game_solo_answers WHERE run_id=NEW.run_id AND position=NEW.slot AND correct) THEN
            RAISE EXCEPTION 'Answer XP requires a correct persisted answer';
        END IF;
    ELSE
        IF s->>'phase'<>'FINISHED' OR jsonb_array_length(s->'history')<>10
           OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'correct'<>'true')
           OR NEW.amount<>(CASE s->>'difficulty' WHEN 'medium' THEN 100 WHEN 'hard' THEN 200 ELSE 0 END) THEN
            RAISE EXCEPTION 'Perfect bonus does not match the completed quiz';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_xp_valid BEFORE INSERT ON game_xp_ledger FOR EACH ROW EXECUTE FUNCTION game_reward_guard();
CREATE TRIGGER game_daily_valid BEFORE INSERT ON game_daily_activity FOR EACH ROW EXECUTE FUNCTION game_reward_guard();
DO $$ DECLARE t TEXT; BEGIN
    FOREACH t IN ARRAY ARRAY['game_question_difficulty','game_solo_answers','game_xp_ledger','game_daily_activity'] LOOP
        EXECUTE format('CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION pvp_immutable()',t);
    END LOOP;
END $$;
COMMIT;
