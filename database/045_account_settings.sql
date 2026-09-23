BEGIN;
SET LOCAL lock_timeout='5s';

ALTER TABLE game_accounts ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE game_accounts ADD COLUMN animations BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE game_accounts ADD COLUMN reduced_motion BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE game_password_resets (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
    account_id UUID NOT NULL REFERENCES game_accounts,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()+INTERVAL '30 minutes'
);
CREATE INDEX game_reset_account ON game_password_resets(account_id);

-- Deletion removes login/profile data while keeping anonymous sporting records.
-- No completed answer, XP entry or frozen game is rewritten or deleted.
CREATE OR REPLACE FUNCTION game_account_identity_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='INSERT' AND NOT NEW.is_guest AND NEW.email IS NULL THEN
        RAISE EXCEPTION 'New player accounts require an email';
    END IF;
    IF TG_OP='UPDATE' THEN
        IF OLD.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'Deleted accounts cannot be restored'; END IF;
        IF NEW.is_guest<>OLD.is_guest THEN RAISE EXCEPTION 'Account identity cannot be downgraded'; END IF;
        IF NEW.deleted_at IS NOT NULL THEN
            IF NEW.email IS NOT NULL OR NEW.password_hash<>'!' OR NEW.bio<>'' OR NEW.club_id IS NOT NULL
               OR NEW.username NOT LIKE 'deleted_%' THEN RAISE EXCEPTION 'Deletion must remove personal account fields'; END IF;
        ELSIF OLD.email IS NOT NULL AND NEW.email IS NULL THEN RAISE EXCEPTION 'Account email cannot be removed';
        END IF;
    END IF;
    RETURN NEW;
END $$;

DROP INDEX game_one_trial;
-- Guest games have no weekly allowance. Registered players keep their existing
-- no-repeat history; every individual guest shootout still has a unique deck.
CREATE OR REPLACE FUNCTION game_allocate_questions() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE allocated_day DATE; q RECORD; previous_count INTEGER:=0;
BEGIN
  IF NEW.is_trial THEN RETURN NEW; END IF;
  IF TG_OP='UPDATE' THEN previous_count:=jsonb_array_length(OLD.state->'deck'); END IF;
  FOR q IN SELECT item,position::integer FROM jsonb_array_elements(NEW.state->'deck') WITH ORDINALITY q(item,position)
           WHERE position>previous_count LOOP
    allocated_day:=(to_timestamp(COALESCE(q.item->>'allocated_at',NEW.state->>'created_at')::bigint/1000.0) AT TIME ZONE 'UTC')::date;
    INSERT INTO game_question_history VALUES(NEW.account_id,
      allocated_day-(EXTRACT(ISODOW FROM allocated_day)::integer-1),allocated_day,
      (q.item->>'question_id')::uuid,(q.item->>'release_id')::uuid,NEW.run_id,q.position);
  END LOOP;
  RETURN NEW;
END $$;
COMMIT;
