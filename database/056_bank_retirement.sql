BEGIN;
SET LOCAL lock_timeout='5s';

-- Retire a whole source batch so publishing another release cannot revive it.
-- Immutable question snapshots remain available to historical game records.
CREATE TABLE game_retired_bank_batches (
 batch_id UUID PRIMARY KEY REFERENCES trivia_bank_batches,
 retired_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 actor TEXT NOT NULL,
 reason TEXT NOT NULL
);
CREATE TRIGGER game_bank_retirement_frozen BEFORE UPDATE OR DELETE ON game_retired_bank_batches
 FOR EACH ROW EXECUTE FUNCTION pvp_immutable();

-- A bank replacement must not rewrite the original daily pool or started runs.
CREATE TABLE game_daily_bank_pools (
 day DATE NOT NULL REFERENCES game_daily_pools,
 bank_key TEXT NOT NULL,
 deck JSONB NOT NULL CHECK(jsonb_typeof(deck)='array' AND jsonb_array_length(deck)>0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(day,bank_key)
);
CREATE TRIGGER game_daily_bank_pool_frozen BEFORE UPDATE OR DELETE ON game_daily_bank_pools
 FOR EACH ROW EXECUTE FUNCTION pvp_immutable();
COMMIT;
