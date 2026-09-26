BEGIN;
SET LOCAL lock_timeout='5s';

ALTER TABLE game_admin_audit DROP CONSTRAINT game_admin_audit_action_check;
ALTER TABLE game_admin_audit ADD CONSTRAINT game_admin_audit_action_check
    CHECK(action IN ('block','unblock','revoke_sessions','delete'));
-- Keep the confirmed name on new actions, including after anonymization.
ALTER TABLE game_admin_audit ADD COLUMN target_username TEXT;

-- Active emails have one owner. Blocked claims survive account deletion;
-- only a digest, not another copy of the email address, is retained.
CREATE TABLE game_email_claims (
    email_hash TEXT PRIMARY KEY CHECK(length(email_hash)=64),
    account_id UUID NOT NULL REFERENCES game_accounts,
    blocked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX game_email_claims_account ON game_email_claims(account_id);
INSERT INTO game_email_claims(email_hash,account_id,blocked)
    SELECT encode(sha256(convert_to(lower(email),'UTF8')),'hex'),account_id,blocked_at IS NOT NULL
    FROM game_accounts WHERE email IS NOT NULL AND deleted_at IS NULL;

CREATE FUNCTION game_claim_email() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE claimed UUID;
BEGIN
    IF TG_OP='UPDATE' AND OLD.blocked_at IS NOT NULL AND NEW.deleted_at IS NULL
       AND NEW.email IS DISTINCT FROM OLD.email THEN
        RAISE EXCEPTION 'Blocked account email cannot be changed' USING ERRCODE='23514';
    END IF;
    IF NEW.email IS NOT NULL THEN
        -- ON CONFLICT waits for concurrent block/delete/registration commits.
        -- A prior SELECT alone would allow a race when the old account is deleted.
        INSERT INTO game_email_claims(email_hash,account_id,blocked)
            VALUES(encode(sha256(convert_to(lower(NEW.email),'UTF8')),'hex'),
                   NEW.account_id,NEW.blocked_at IS NOT NULL)
            ON CONFLICT(email_hash) DO UPDATE SET blocked=EXCLUDED.blocked
                WHERE game_email_claims.account_id=EXCLUDED.account_id
            RETURNING account_id INTO claimed;
        IF claimed IS NULL THEN
            RAISE EXCEPTION 'This email is unavailable' USING ERRCODE='23505';
        END IF;
    END IF;
    IF TG_OP='UPDATE' AND OLD.email IS DISTINCT FROM NEW.email THEN
        DELETE FROM game_email_claims WHERE account_id=NEW.account_id AND NOT blocked
            AND email_hash=encode(sha256(convert_to(lower(OLD.email),'UTF8')),'hex');
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER game_email_claim AFTER INSERT OR UPDATE OF email,blocked_at,deleted_at
    ON game_accounts FOR EACH ROW EXECUTE FUNCTION game_claim_email();

-- A revoked token can explain a block, but never authenticates a request.
-- Notices expire with the original session, and contain no raw credentials.
CREATE TABLE game_session_notices (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64),
    account_id UUID NOT NULL REFERENCES game_accounts,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX game_session_notices_expiry ON game_session_notices(expires_at);
COMMIT;
