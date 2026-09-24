BEGIN;

-- Canonical pairs make simultaneous/reversed requests a single relationship.
CREATE TABLE game_friendships (
    account_a uuid NOT NULL REFERENCES game_accounts(account_id),
    account_b uuid NOT NULL REFERENCES game_accounts(account_id),
    requested_by uuid NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    accepted_at timestamptz,
    invite_run uuid REFERENCES game_mode_runs(run_id),
    invited_by uuid,
    PRIMARY KEY (account_a,account_b),
    CHECK (account_a < account_b),
    CHECK (requested_by IN (account_a,account_b)),
    CHECK (invited_by IS NULL OR invited_by IN (account_a,account_b)),
    CHECK ((status='accepted') = (accepted_at IS NOT NULL))
);
CREATE INDEX game_friendships_recipient ON game_friendships(account_b);

-- Only the authenticated result-publishing endpoint writes this allowlisted
-- snapshot. A random token is independent of the private run/account IDs.
CREATE TABLE game_result_shares (
    token text PRIMARY KEY,
    mode text NOT NULL CHECK (mode IN ('solo','daily','friend')),
    run_id uuid NOT NULL,
    owner_id uuid NOT NULL REFERENCES game_accounts(account_id),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot)='object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (mode,run_id,owner_id)
);
CREATE FUNCTION game_result_share_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Published result snapshots cannot be edited';
END $$;
CREATE TRIGGER game_result_share_immutable BEFORE UPDATE ON game_result_shares
    FOR EACH ROW EXECUTE FUNCTION game_result_share_immutable();

COMMIT;
