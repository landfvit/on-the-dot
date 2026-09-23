"""Apply trivia-only migrations; never import or modify provider football records."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.database import get_connection


def migrate():
    with get_connection() as conn:
        conn.autocommit = True
        conn.execute('SELECT pg_advisory_lock(84424323)')
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS trivia_schema_migrations(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
            for name in ['022_trivia', '024_trivia_player_events', '025_trivia_integrity', '026_trivia_quizzes', '027_trivia_lifecycle_guards', '028_sports_query', '029_query_training', '030_trivia_context', '031_penalty_games', '032_penalty_guards', '033_trivia_bank', '034_trivia_bank_guards', '035_trivia_bank_completeness', '036_penalty_bank', '037_player_progress', '038_solo_answer_guards', '039_email_trials_xp', '040_weekly_question_history', '041_recognition_choices', '042_solo_answer_duration', '043_solo_shootout', '044_solo_community']:
                if conn.execute('SELECT 1 FROM trivia_schema_migrations WHERE name=%s', (name,)).fetchone():
                    continue
                conn.execute((ROOT / 'database' / f'{name}.sql').read_text())
                conn.execute('INSERT INTO trivia_schema_migrations(name) VALUES (%s) ON CONFLICT DO NOTHING', (name,))
                print(f'Applied {name}', flush=True)
        finally:
            conn.execute('SELECT pg_advisory_unlock(84424323)')


if __name__ == '__main__':
    migrate()
