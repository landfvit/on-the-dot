BEGIN;


-- API-Football can occasionally return unusual event time values,
-- including negative elapsed minutes.
--
-- We preserve provider data exactly as received and use source_order
-- as the authoritative ordering of fixture events.

ALTER TABLE fixture_events
DROP CONSTRAINT IF EXISTS fixture_events_elapsed_minute_check;


ALTER TABLE fixture_events
DROP CONSTRAINT IF EXISTS fixture_events_extra_minute_check;


COMMIT;