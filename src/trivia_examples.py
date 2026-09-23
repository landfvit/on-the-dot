"""Preview or explicitly publish a small, reproducible review pack from verified facts."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg.types.json import Jsonb

from api import trivia, trivia_quizzes
from api.database import get_connection
from api.sports_query import ParseRequest, SportsQuery, parse_query
from api.sports_query_routes import catalogue
from api.trivia_models import EvaluationRequest, SaveQuestion, TriviaSpec


EXAMPLES = [
    'Manchester United wins 2017/18',
    'Manchester City goals scored 2017/18',
    'Chelsea clean sheets 2016/17',
    'Arsenal points per game away 2024/25',
    'Liverpool goals per game 2023/24',
    'Manchester United loss rate 2017/18',
    'Manchester United win rate against Big 6 last 10 seasons',
]


def create_pack(publish=False):
    with get_connection() as conn:
        # One transaction and lock make a rerun safe, including partial failures.
        conn.execute('SELECT pg_advisory_xact_lock(84424324)')
        context = catalogue(conn, 39)
        specs = [TriviaSpec(template='top_scorer', league_id=39, team_id=33,
                            period={'mode': 'seasons', 'seasons': [2017]}, name_policy='unique-surname-v1')]
        for text in EXAMPLES:
            parsed = parse_query(ParseRequest(text=text, competition_id=39), context)
            if not parsed['ok']:
                raise RuntimeError(f"Cannot parse example: {parsed['issues']}")
            specs.append(SportsQuery(**parsed['query']).specification())

        @contextmanager
        def shared():
            yield conn

        versions = []
        with patch('api.trivia.get_connection', shared), patch('api.trivia_quizzes.get_connection', shared):
            for spec in specs:
                result = trivia.evaluate(conn, EvaluationRequest(specification=spec, dataset_id=context['dataset_id']))
                answer = result['answer']
                print(f"{result['question_text']}\n  {answer.get('label', '')} {answer['value']} {answer['unit']} | "
                      f"eligible {result['coverage']['eligible_matches']}/{result['coverage']['requested_matches']} | "
                      f"publishable={result['coverage']['publishable']}", flush=True)
                if not result['coverage']['publishable']:
                    raise RuntimeError('Example failed quality checks; nothing was published')
                if not publish:
                    continue
                existing = conn.execute('''SELECT version_id,question_id,specification,answer FROM trivia_question_versions
                    WHERE dataset_id=%s AND specification-'name_policy'=%s::jsonb-'name_policy'
                        AND state='published' AND verified_at IS NOT NULL
                    ORDER BY revision DESC,created_at LIMIT 1''', (context['dataset_id'], Jsonb(result['specification']))).fetchone()
                if existing and existing['answer'] == result['answer'] and existing['specification'].get('name_policy', 'exact-v1') == spec.name_policy:
                    versions.append(existing['version_id'])
                    continue
                saved = trivia.save(SaveQuestion(specification=spec, dataset_id=context['dataset_id'],
                    question_id=existing['question_id'] if existing else None))
                trivia.publish(saved['version_id'])
                versions.append(saved['version_id'])
            if publish:
                existing = conn.execute('''SELECT v.version_id FROM trivia_quiz_versions v
                    JOIN trivia_quiz_questions x ON x.quiz_version_id=v.version_id
                    WHERE v.title='Premier League | Review pack' AND v.state='published'
                    GROUP BY v.version_id HAVING ARRAY_AGG(x.question_version_id ORDER BY x.position)=%s''', (versions,)).fetchone()
                if existing:
                    print(f"Existing quiz: {existing['version_id']}")
                else:
                    previous = conn.execute("SELECT quiz_id FROM trivia_quiz_versions WHERE title='Premier League | Review pack' ORDER BY created_at DESC,revision DESC LIMIT 1").fetchone()
                    quiz = trivia_quizzes.save_quiz(trivia_quizzes.QuizDefinition(title='Premier League | Review pack',
                        description='8 questions: scorers, wins, goals, clean sheets, averages and Big 6.', question_versions=versions,
                        quiz_id=previous['quiz_id'] if previous else None))
                    trivia_quizzes.publish_quiz(quiz['version_id'])
                    print(f"Published quiz: {quiz['version_id']}")
        return versions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Publish verified questions and a playable quiz; default is preview only')
    create_pack(parser.parse_args().publish)
