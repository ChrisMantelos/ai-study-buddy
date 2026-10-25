"""Put demo notes and quiz scores into the local notes.db, to try the weak-spot
screens without an API key.

    python seed_demo_data.py            add three demo notes with scores
    python seed_demo_data.py --remove   remove exactly those demo rows again

Run it from the backend folder, with the server stopped, then start the server
again: it reads the notes from the database when it starts. Demo titles start
with "[demo] ", so --remove never touches your real notes.
"""
import os
import sqlite3
import sys

import database
from rag import chunk_text

PREFIX = "[demo] "

DEMO = [
    # (title, note text, score, total)
    (
        "Biology: Mitochondria",
        "Mitochondria produce most of the cell's ATP through oxidative "
        "phosphorylation. Their inner membrane is folded into cristae.",
        1,
        4,
    ),
    (
        "Networking: TCP vs UDP",
        "TCP is connection-oriented and reliable. UDP is connectionless and has "
        "low overhead, which suits live video and DNS lookups.",
        2,
        4,
    ),
    (
        "History: Cold War",
        "The Cold War was a rivalry between the United States and the Soviet "
        "Union after 1945, fought through an arms race and proxy wars.",
        3,
        4,
    ),
]


def remove() -> None:
    conn = sqlite3.connect(database.DB_PATH)
    notes = conn.execute("DELETE FROM notes WHERE source LIKE ?", (PREFIX + "%",)).rowcount
    quizzes = conn.execute("DELETE FROM quiz_history WHERE source LIKE ?", (PREFIX + "%",)).rowcount
    conn.commit()
    conn.close()
    print(f"Removed {notes} demo note chunks and {quizzes} demo quizzes.")


def seed() -> None:
    existing = {source for source, _ in database.fetch_all_chunks()}
    if any(source.startswith(PREFIX) for source in existing):
        raise SystemExit("Demo data is already there. Run with --remove first to start over.")

    for number, (title, text, score, total) in enumerate(DEMO, start=1):
        source = PREFIX + title
        database.insert_chunks(source, chunk_text(text))
        quiz_id = database.insert_quiz_record(source, total, f"2026-01-0{number}T10:00:00")
        database.update_quiz_score(quiz_id, score, total)
    print(f"Added {len(DEMO)} demo notes with scores. Start the server (again) to see them.")


if __name__ == "__main__":
    database.init_db()
    print(f"Using database: {os.path.abspath(database.DB_PATH)}")
    remove() if "--remove" in sys.argv else seed()
