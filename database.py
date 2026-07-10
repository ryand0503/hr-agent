import sqlite3
import os
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,
            email       TEXT,
            subject     TEXT,
            received_at TEXT,
            file_name   TEXT,
            file_path   TEXT,
            cv_text     TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rankings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            jd_snippet   TEXT,
            candidate_id INTEGER,
            rank         INTEGER,
            score        INTEGER,
            summary      TEXT,
            strengths    TEXT,
            gaps         TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (candidate_id) REFERENCES candidates(id)
        );
    """)
    conn.commit()
    conn.close()


def candidate_exists(email, file_name):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM candidates WHERE email=? AND file_name=?",
        (email, file_name)
    ).fetchone()
    conn.close()
    return row is not None


def insert_candidate(name, email, subject, received_at, file_name, file_path, cv_text):
    conn = get_conn()
    conn.execute(
        """INSERT INTO candidates (name, email, subject, received_at, file_name, file_path, cv_text)
           VALUES (?,?,?,?,?,?,?)""",
        (name, email, subject, received_at, file_name, file_path, cv_text)
    )
    conn.commit()
    conn.close()


def get_all_candidates():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, email, subject, received_at, file_name FROM candidates ORDER BY received_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_candidates_for_ranking():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, email, cv_text FROM candidates WHERE cv_text IS NOT NULL AND cv_text != ''"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_rankings(jd_snippet, results):
    conn = get_conn()
    for r in results:
        conn.execute(
            """INSERT INTO rankings (jd_snippet, candidate_id, rank, score, summary, strengths, gaps)
               VALUES (?,?,?,?,?,?,?)""",
            (jd_snippet, r["id"], r["rank"], r["score"], r["summary"], r["strengths"], r["gaps"])
        )
    conn.commit()
    conn.close()


def get_candidate_count():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    conn.close()
    return count
