BEGIN;
SET LOCAL lock_timeout='5s';

-- Existing memberships can change once immediately; subsequent changes wait 72h.
ALTER TABLE game_accounts ADD COLUMN club_changed_at TIMESTAMPTZ;

CREATE FUNCTION game_club_change_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE changed_at TIMESTAMPTZ := clock_timestamp();
BEGIN
    -- Account erasure must remain possible even during a membership cooldown.
    IF NEW.deleted_at IS NOT NULL THEN RETURN NEW; END IF;
    IF NEW.club_id IS DISTINCT FROM OLD.club_id THEN
        IF OLD.club_changed_at IS NOT NULL AND changed_at < OLD.club_changed_at + INTERVAL '72 hours' THEN
            RAISE EXCEPTION 'Team membership can change only once every 72 hours'
                USING ERRCODE='23514', CONSTRAINT='game_club_change_cooldown';
        END IF;
        NEW.club_changed_at := changed_at;
    ELSIF NEW.club_changed_at IS DISTINCT FROM OLD.club_changed_at THEN
        RAISE EXCEPTION 'Membership cooldown cannot be rewritten'
            USING ERRCODE='23514', CONSTRAINT='game_club_change_timestamp';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_club_change_guard BEFORE UPDATE OF club_id, club_changed_at
    ON game_accounts FOR EACH ROW EXECUTE FUNCTION game_club_change_guard();
COMMIT;
