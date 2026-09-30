BEGIN;
SET LOCAL lock_timeout='5s';

-- Keep recovery requests in the existing immutable admin audit. Existing
-- accounts, credentials, sessions and reset tokens are left untouched.
ALTER TABLE game_admin_audit DROP CONSTRAINT game_admin_audit_action_check;
ALTER TABLE game_admin_audit ADD CONSTRAINT game_admin_audit_action_check
    CHECK(action IN ('block','unblock','revoke_sessions','delete','password_reset_requested'));

COMMIT;
