import sqlite3

DB_PATH = "notes.db"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            chunk TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            num_questions INTEGER NOT NULL,
            score INTEGER,
            total INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def insert_chunks(source: str, chunks: list[str]) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        "INSERT INTO notes (source, chunk) VALUES (?, ?)",
        [(source, chunk) for chunk in chunks],
    )
    conn.commit()
    conn.close()


def fetch_all_chunks() -> list[tuple[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT source, chunk FROM notes").fetchall()
    conn.close()
    return rows


def clear_all() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM notes")
    conn.commit()
    conn.close()


def insert_quiz_record(source: str, num_questions: int, created_at: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "INSERT INTO quiz_history (source, num_questions, created_at) VALUES (?, ?, ?)",
        (source, num_questions, created_at),
    )
    conn.commit()
    quiz_id = cursor.lastrowid
    conn.close()
    return quiz_id


def update_quiz_score(quiz_id: int, score: int, total: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "UPDATE quiz_history SET score = ?, total = ? WHERE id = ?",
        (score, total, quiz_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


def fetch_quiz_history_with_notes() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            quiz_history.id AS quiz_id,
            quiz_history.source AS source,
            quiz_history.num_questions AS num_questions,
            quiz_history.score AS score,
            quiz_history.total AS total,
            quiz_history.created_at AS created_at,
            notes.chunk AS sample_note
        FROM quiz_history
        LEFT JOIN notes ON quiz_history.source = notes.source
        GROUP BY quiz_history.id
        ORDER BY quiz_history.id DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_accuracy_trend_by_source() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            source,
            created_at,
            score,
            total,
            ROUND(
                AVG(CAST(score AS FLOAT) / total) OVER (
                    PARTITION BY source
                    ORDER BY created_at
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ),
                2
            ) AS running_avg_accuracy
        FROM quiz_history
        WHERE score IS NOT NULL AND total IS NOT NULL AND total > 0
        ORDER BY source, created_at
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]
