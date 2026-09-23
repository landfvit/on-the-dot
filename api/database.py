import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv()


def get_connection():
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
