BEGIN;
SET LOCAL lock_timeout='5s';
ALTER TABLE game_accounts ADD COLUMN blocked_at TIMESTAMPTZ;
CREATE TABLE game_admin_audit (
    request_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES game_accounts,
    action TEXT NOT NULL CHECK(action IN ('block','unblock','revoke_sessions')),
    reason TEXT NOT NULL CHECK(length(reason) BETWEEN 3 AND 500),
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX game_admin_audit_account ON game_admin_audit(account_id,created_at DESC);
CREATE TRIGGER frozen BEFORE UPDATE OR DELETE ON game_admin_audit
    FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
CREATE INDEX game_solo_created ON game_solo_runs(created_at DESC);
CREATE INDEX game_mode_created ON game_mode_runs(created_at DESC);
COMMIT;
