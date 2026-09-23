"""Temporary browser QA server. Its entire database transaction is rolled back on exit."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from api import trivia, trivia_quizzes
from api.database import get_connection
from api.trivia_models import SaveQuestion
from api.trivia_quizzes import QuizDefinition
from trivia_app.main import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8003)
    args = parser.parse_args()
    conn = get_connection()
    @contextmanager
    def shared():
        yield conn
    try:
        with patch('api.trivia.get_connection', shared), patch('api.trivia_quizzes.get_connection', shared):
            spec = {'template': 'top_scorer', 'league_id': 39, 'team_id': 33,
                    'period': {'mode': 'seasons', 'seasons': [2017]}, 'minimum_sample': 1}
            ids = []
            for template in ['top_scorer', 'total_wins']:
                saved = trivia.save(SaveQuestion(specification={**spec, 'template': template}))
                trivia.publish(saved['version_id']); ids.append(saved['version_id'])
            quiz = trivia_quizzes.save_quiz(QuizDefinition(title='Manchester United 2017/18',
                description='Premier League', question_versions=ids))
            trivia_quizzes.publish_quiz(quiz['version_id'])
            print('ROLLBACK-ONLY BROWSER PREVIEW', flush=True)
            uvicorn.run(app, host='127.0.0.1', port=args.port)
    finally:
        conn.rollback(); conn.close()
        print('Preview transaction rolled back.', flush=True)


if __name__ == '__main__':
    main()
