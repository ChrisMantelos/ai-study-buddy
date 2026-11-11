"""Study Buddy as a local MCP server.

It exposes the notes library and the quiz history to any MCP client (Claude Desktop,
Claude Code, ...) over stdio, so the client's own model can build and run quizzes
from your notes. The tools reuse the functions of the agent in agent.py.

    Tools      list_notes, search_notes, get_note, get_source_stats, record_quiz_score
    Resources  study-buddy://notes  and  study-buddy://notes/{title}
    Prompts    quiz_me, review_weak_spots

Run it directly (the client normally starts it for you):

    python mcp_server.py

It reads the same notes.db as the FastAPI server (the one in this folder), unless
the STUDY_BUDDY_DB environment variable points somewhere else. Needs
`pip install -r requirements-mcp.txt`.

Nothing is printed to stdout, because stdout carries the protocol itself.
"""
import os
import sys
from datetime import datetime, timezone
from urllib.parse import unquote

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError

import agent
import database
from rag import NoteLibrary

HERE = os.path.dirname(os.path.abspath(__file__))

mcp = MCPServer(
    "study-buddy",
    instructions=(
        "Tools for the user's saved study notes. Use list_notes to see what exists, "
        "search_notes (keyword search: retry with synonyms if nothing is found) or "
        "get_note to read material, and get_source_stats for the accuracy per note. "
        "Build quiz questions only from text these tools return. After a quiz, save "
        "the result with record_quiz_score."
    ),
)


def _library() -> NoteLibrary:
    """A fresh view of the library on every call, so notes added through the API
    while this server is running are visible."""
    return NoteLibrary()


# ----------------------------------------------------------------------- tools

@mcp.tool()
def list_notes() -> dict:
    """List the titles of all saved notes, with their chunk counts."""
    return agent.tool_list_notes(_library())


@mcp.tool()
def search_notes(query: str, top_k: int = 5) -> dict:
    """Keyword (BM25) search over all saved notes.

    Returns up to top_k chunks (1 to 10) with their note title and a score. Matching
    is on exact words only, so if the results are empty or off-topic, search again
    with synonyms or related terms.
    """
    return agent.tool_search_notes(_library(), query, top_k)


@mcp.tool()
def get_note(title: str) -> dict:
    """Return the full text of one saved note, by its exact title (see list_notes)."""
    return agent.tool_get_note(_library(), title)


@mcp.tool()
def get_source_stats() -> dict:
    """The user's average quiz accuracy per saved note, weakest first.

    Use it to find the notes the user needs to review most.
    """
    return agent.tool_get_source_stats(_library())


@mcp.tool()
def record_quiz_score(note_title: str, score: int, total: int) -> dict:
    """Save the result of a quiz the user just took, under the note it was based on.

    note_title must be the exact title of a saved note. The score then counts towards
    that note's statistics, which get_source_stats and the weak-spot review use.
    """
    titles = sorted(set(_library().sources))
    if note_title not in titles:
        return {"error": f"No note titled '{note_title}'.", "available_titles": titles}
    if total < 1 or score < 0 or score > total:
        return {"error": "score must be between 0 and total, and total must be at least 1."}

    quiz_id = database.insert_quiz_record(
        source=note_title,
        num_questions=total,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    database.update_quiz_score(quiz_id, score, total)
    return {"status": "saved", "quiz_id": quiz_id, "note_title": note_title, "score": score, "total": total}


# ------------------------------------------------------------------- resources

@mcp.resource("study-buddy://notes", mime_type="text/plain")
def notes_index() -> str:
    """The titles of all saved notes, one per line."""
    notes = agent.tool_list_notes(_library())["notes"]
    return "\n".join(f"{n['title']} ({n['chunks']} chunks)" for n in notes) or "No notes saved yet."


@mcp.resource("study-buddy://notes/{title}", mime_type="text/plain")
def note_text(title: str) -> str:
    """The full text of one saved note. Percent-encode the title in the URI."""
    note = agent.tool_get_note(_library(), unquote(title))
    if "error" in note:
        raise ResourceNotFoundError(note["error"])
    return note["text"]


# --------------------------------------------------------------------- prompts

@mcp.prompt()
def quiz_me(topic: str, num_questions: int = 5) -> str:
    """Quiz me on a topic, using only my saved notes."""
    return (
        f'Quiz me on "{topic}" with {num_questions} multiple-choice questions, using only my '
        "saved notes.\n\n"
        "1. Find the material with search_notes (retry with different words if it finds "
        "nothing) or get_note.\n"
        "2. Write the questions from that text only: 4 options each, exactly one correct.\n"
        "3. Ask one question at a time, wait for my answer, and tell me if it was right.\n"
        "4. At the end, tell me my score and save it with record_quiz_score, using the exact "
        "title of the note the questions came from."
    )


@mcp.prompt()
def review_weak_spots(num_questions: int = 5) -> str:
    """Quiz me on the saved notes where my scores are lowest."""
    return (
        f"Quiz me with {num_questions} multiple-choice questions on my weakest saved note.\n\n"
        "1. Call get_source_stats to find the note with the lowest accuracy. If there are no "
        "scores yet, say so and offer to quiz me on any note instead.\n"
        "2. Read that note with get_note and write the questions from its text only: 4 options "
        "each, exactly one correct.\n"
        "3. Ask one question at a time, wait for my answer, and tell me if it was right.\n"
        "4. At the end, tell me my score and save it with record_quiz_score."
    )


# ------------------------------------------------------------------------ main

def configure_database() -> str:
    """Point the database module at the shared notes.db (not at the current folder)."""
    path = os.environ.get("STUDY_BUDDY_DB") or os.path.join(HERE, "notes.db")
    database.DB_PATH = path
    database.init_db()
    return path


if __name__ == "__main__":
    print(f"study-buddy MCP server, database: {configure_database()}", file=sys.stderr)
    mcp.run()
