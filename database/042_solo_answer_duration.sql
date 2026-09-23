BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE game_solo_answers DROP CONSTRAINT game_solo_answers_elapsed_ms_check;
ALTER TABLE game_solo_answers ADD CONSTRAINT game_solo_answers_elapsed_ms_check
    CHECK (elapsed_ms BETWEEN 0 AND 15000);
COMMIT;
