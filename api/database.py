import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


load_dotenv()
_pool = None


def connection_settings():
    url = os.getenv('DATABASE_URL', '').strip()
    if url:
        return url, {'row_factory': dict_row}
    return '', dict(host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'),
                    dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'),
                    password=os.getenv('DB_PASSWORD'), row_factory=dict_row)


def start_pool():
    """Only web workers pool connections; CLI migrations keep direct sessions."""
    global _pool
    if _pool is not None:
        raise RuntimeError('Database pool is already running')
    minimum = int(os.getenv('DB_POOL_MIN', '2'))
    maximum = int(os.getenv('DB_POOL_MAX', '10'))
    if not 0 <= minimum <= maximum <= 30 or maximum == 0:
        raise ValueError('DB_POOL_MIN/MAX must satisfy 0 <= min <= max <= 30 and max > 0')
    url, kwargs = connection_settings()
    _pool = ConnectionPool(url, kwargs={**kwargs, 'connect_timeout': 5, 'prepare_threshold': None},
                          min_size=minimum, max_size=maximum, timeout=5, max_waiting=100,
                          check=ConnectionPool.check_connection, open=False,
                          name='game-web', max_idle=60)
    _pool.open()


def close_pool():
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        pool.close()


def get_connection():
    if _pool is not None:
        return _pool.connection()
    # Hosting providers supply one connection URL. Do not mix it with local
    # DB_* values, which could otherwise override the URL's credentials/host.
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return psycopg.connect(database_url, row_factory=dict_row)
    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row
    )


def fetch_all(query, params=None):
    if params is None:
        params = ()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query,
                params
            )

            return cursor.fetchall()


def fetch_one(query, params=None):
    if params is None:
        params = ()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                query,
                params
            )

            return cursor.fetchone()
