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
