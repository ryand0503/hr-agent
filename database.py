import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id          SERIAL PRIMARY KEY,
            name        TEXT,
            email       TEXT,
            subject     TEXT,
            received_at TEXT,
            file_name   TEXT,
            file_path   TEXT,
            cv_text     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rankings (
            id           SERIAL PRIMARY KEY,
            jd_snippet   TEXT,
            candidate_id INTEGER REFERENCES candidates(id),
            rank         INTEGER,
            score        INTEGER,
            summary      TEXT,
            strengths    TEXT,
            gaps         TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def candidate_exists(email, file_name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM candidates WHERE email=%s AND file_name=%s",
        (email, file_name)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row is not None


def insert_candidate(name, email, subject, received_at, file_name, file_path, cv_text):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO candidates (name, email, subject, received_at, file_name, file_path, cv_text)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (name, email, subject, received_at, file_name, file_path, cv_text)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_all_candidates():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, email, subject, received_at, file_name FROM candidates ORDER BY received_at DESC"
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def get_candidates_for_ranking():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, email, cv_text FROM candidates WHERE cv_text IS NOT NULL AND cv_text != ''"
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def save_rankings(jd_snippet, results):
    conn = get_conn()
    cur = conn.cursor()
    for r in results:
        cur.execute(
            """INSERT INTO rankings (jd_snippet, candidate_id, rank, score, summary, strengths, gaps)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (jd_snippet, r["id"], r["rank"], r["score"], r["summary"], r["strengths"], r["gaps"])
        )
    conn.commit()
    cur.close()
    conn.close()


def get_candidate_count():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS count FROM candidates")
    count = cur.fetchone()["count"]
    cur.close()
    conn.close()
    return count
