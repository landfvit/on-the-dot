BEGIN;
ALTER TABLE game_accounts ADD COLUMN email TEXT;
ALTER TABLE game_accounts ADD COLUMN is_guest BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE game_accounts ADD CONSTRAINT game_email_canonical CHECK(email IS NULL OR (email=lower(email) AND length(email)<=254 AND position('@' in email)>1));
CREATE UNIQUE INDEX game_account_email ON game_accounts(email) WHERE email IS NOT NULL;
CREATE FUNCTION game_account_identity_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='INSERT' AND NOT NEW.is_guest AND NEW.email IS NULL THEN
        RAISE EXCEPTION 'New player accounts require an email';
    END IF;
    IF TG_OP='UPDATE' AND (NEW.is_guest<>OLD.is_guest OR (OLD.email IS NOT NULL AND NEW.email IS NULL)) THEN
        RAISE EXCEPTION 'Account identity cannot be downgraded';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_account_identity BEFORE INSERT OR UPDATE ON game_accounts FOR EACH ROW EXECUTE FUNCTION game_account_identity_guard();
ALTER TABLE game_solo_runs ADD COLUMN is_trial BOOLEAN NOT NULL DEFAULT FALSE;
CREATE UNIQUE INDEX game_one_trial ON game_solo_runs(account_id) WHERE is_trial;
CREATE FUNCTION game_trial_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.is_trial IS DISTINCT FROM (SELECT is_guest FROM game_accounts WHERE account_id=NEW.account_id)
       OR (TG_OP='UPDATE' AND NEW.is_trial<>OLD.is_trial) THEN
        RAISE EXCEPTION 'Trial identity must match the quiz owner';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_trial_valid BEFORE INSERT OR UPDATE ON game_solo_runs FOR EACH ROW EXECUTE FUNCTION game_trial_guard();
ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_ledger_amount_check;
ALTER TABLE game_xp_ledger DROP CONSTRAINT game_xp_ledger_check;
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_amount CHECK(amount IN (10,20,30,100,200,600));
ALTER TABLE game_xp_ledger ADD CONSTRAINT game_xp_slot_amount CHECK(
    (slot=0 AND reason='perfect_bonus' AND amount IN (100,200,600)) OR
    (slot>0 AND reason='correct_answer' AND amount IN (10,20,30)));
CREATE OR REPLACE FUNCTION game_reward_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE s JSONB; trial BOOLEAN; per_answer INTEGER; multiplier INTEGER;
BEGIN
    SELECT state,is_trial INTO s,trial FROM game_solo_runs WHERE run_id=NEW.run_id;
    IF trial THEN RAISE EXCEPTION 'Trials cannot earn saved XP or streak credit'; END IF;
    per_answer:=(s->'rules'->>'xp_per_correct')::integer;
    multiplier:=(s->'rules'->'perfect_multipliers'->>(s->>'difficulty'))::integer;
    IF TG_TABLE_NAME='game_daily_activity' THEN
        IF s->>'phase'<>'FINISHED' OR jsonb_array_length(s->'history')<>10
           OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'option_id' IS NULL)
           OR NEW.day<>(to_timestamp((s->>'finished_at')::bigint/1000.0) AT TIME ZONE 'UTC')::date THEN
            RAISE EXCEPTION 'Daily activity requires ten submitted answers';
        END IF;
    ELSIF NEW.slot>0 THEN
        IF NEW.amount IS DISTINCT FROM per_answer OR NOT EXISTS(
            SELECT 1 FROM game_solo_answers WHERE run_id=NEW.run_id AND position=NEW.slot AND correct) THEN
            RAISE EXCEPTION 'Answer XP must match the correct answer and frozen rules';
        END IF;
    ELSE
        IF s->>'phase'<>'FINISHED' OR jsonb_array_length(s->'history')<>10
           OR EXISTS(SELECT 1 FROM jsonb_array_elements(s->'history') a WHERE a->>'correct'<>'true')
           OR NEW.amount IS DISTINCT FROM (10*per_answer*(multiplier-1)) THEN
            RAISE EXCEPTION 'Perfect bonus does not match the completed quiz';
        END IF;
    END IF;
    RETURN NEW;
END $$;
COMMIT;
