"""Tests for mcp_server.py.

Most of them start the real server as a subprocess and talk to it over stdio with the
official MCP client, the same way Claude Desktop would. No API key is needed.

They are skipped when the MCP SDK (version 2) is not installed:
    pip install -r requirements-mcp.txt
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.mcpserver", reason="needs mcp 2.x: pip install -r requirements-mcp.txt")

from mcp import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

import database  # noqa: E402
import mcp_server  # noqa: E402
from rag import chunk_text  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
TIMEOUT = 60


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """An empty, isolated database that both this process and the server subprocess use."""
    path = str(tmp_path / "mcp_test.db")
    monkeypatch.setattr(database, "DB_PATH", path)
    database.init_db()
    return path


def add_note(title, text, score=None, total=4):
    database.insert_chunks(title, chunk_text(text))
    if score is not None:
        quiz_id = database.insert_quiz_record(title, total, "2026-01-01T10:00:00")
        database.update_quiz_score(quiz_id, score, total)


def seed():
    add_note("Biology: Mitochondria", "Mitochondria make ATP.\n\nTheir inner membrane has cristae.", score=1)
    add_note("History: Cold War", "The Cold War began after 1945.", score=3)


def run_against_server(db_path, scenario):
    """Start the server on `db_path`, run `await scenario(client)`, return its result."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(BACKEND / "mcp_server.py")],
        env={**os.environ, "STUDY_BUDDY_DB": db_path},
        cwd=str(BACKEND),
    )

    async def main():
        async with Client(params) as client:
            return await scenario(client)

    return asyncio.run(asyncio.wait_for(main(), timeout=TIMEOUT))


def payload(result):
    """The JSON a tool returned (as a text block)."""
    return json.loads(result.content[0].text)


# ------------------------------------------------------ over stdio, real server

def test_server_exposes_tools_resources_and_prompts(db_path):
    async def scenario(client):
        return (
            {t.name for t in (await client.list_tools()).tools},
            {str(r.uri) for r in (await client.list_resources()).resources},
            {str(t.uri_template) for t in (await client.list_resource_templates()).resource_templates},
            {p.name for p in (await client.list_prompts()).prompts},
        )

    tools, resources, templates, prompts = run_against_server(db_path, scenario)
    assert tools == {"list_notes", "search_notes", "get_note", "get_source_stats", "record_quiz_score"}
    assert resources == {"study-buddy://notes"}
    assert templates == {"study-buddy://notes/{title}"}
    assert prompts == {"quiz_me", "review_weak_spots"}


def test_tools_read_the_library_and_stats(db_path):
    seed()

    async def scenario(client):
        notes = payload(await client.call_tool("list_notes", {}))
        found = payload(await client.call_tool("search_notes", {"query": "mitochondria", "top_k": 3}))
        note = payload(await client.call_tool("get_note", {"title": "History: Cold War"}))
        missing = payload(await client.call_tool("get_note", {"title": "Nope"}))
        stats = payload(await client.call_tool("get_source_stats", {}))
        return notes, found, note, missing, stats

    notes, found, note, missing, stats = run_against_server(db_path, scenario)
    assert [n["title"] for n in notes["notes"]] == ["Biology: Mitochondria", "History: Cold War"]
    assert found["count"] >= 1 and found["results"][0]["source"] == "Biology: Mitochondria"
    assert "began after 1945" in note["text"]
    assert "error" in missing and "Biology: Mitochondria" in missing["available_titles"]
    assert [s["source"] for s in stats["sources"]] == ["Biology: Mitochondria", "History: Cold War"]
    assert stats["sources"][0]["avg_accuracy"] == 0.25


def test_recorded_score_changes_the_weak_spot_ranking(db_path):
    seed()  # Biology 25%, Cold War 75%

    async def scenario(client):
        saved = payload(
            await client.call_tool("record_quiz_score", {"note_title": "History: Cold War", "score": 0, "total": 4})
        )
        stats = payload(await client.call_tool("get_source_stats", {}))
        return saved, stats

    saved, stats = run_against_server(db_path, scenario)
    assert saved["status"] == "saved"
    # Cold War is now (75% + 0%) / 2 = 37.5%, still above Biology at 25%, with two scored quizzes
    cold_war = next(s for s in stats["sources"] if s["source"] == "History: Cold War")
    assert cold_war["scored_quizzes"] == 2 and cold_war["avg_accuracy"] == 0.38


def test_resources_over_stdio(db_path):
    seed()

    async def scenario(client):
        index = (await client.read_resource("study-buddy://notes")).contents[0].text
        text = (await client.read_resource("study-buddy://notes/Biology%3A%20Mitochondria")).contents[0].text
        try:
            await client.read_resource("study-buddy://notes/Nope")
            error = None
        except Exception as exc:  # the SDK raises an MCPError carrying the message
            error = str(exc)
        return index, text, error

    index, text, error = run_against_server(db_path, scenario)
    assert "Biology: Mitochondria (2 chunks)" in index
    assert "cristae" in text
    assert error is not None and "No note titled 'Nope'" in error


def test_prompts_over_stdio(db_path):
    async def scenario(client):
        quiz = await client.get_prompt("quiz_me", {"topic": "mitochondria", "num_questions": "3"})
        weak = await client.get_prompt("review_weak_spots", {})
        return quiz.messages[0].content.text, weak.messages[0].content.text

    quiz, weak = run_against_server(db_path, scenario)
    assert '"mitochondria"' in quiz and "3 multiple-choice" in quiz and "record_quiz_score" in quiz
    assert "get_source_stats" in weak and "5 multiple-choice" in weak


# --------------------------------------------------- direct calls, no subprocess

def test_record_quiz_score_rejects_unknown_note_and_bad_scores(db_path):
    add_note("Biology: Mitochondria", "Mitochondria make ATP.")
    unknown = mcp_server.record_quiz_score("Nope", 1, 4)
    assert "error" in unknown and unknown["available_titles"] == ["Biology: Mitochondria"]
    for score, total in [(5, 4), (-1, 4), (0, 0)]:
        assert "error" in mcp_server.record_quiz_score("Biology: Mitochondria", score, total)
    assert database.fetch_accuracy_trend_by_source() == []  # nothing was written


def test_server_sees_notes_added_while_it_is_running(db_path):
    assert mcp_server.list_notes() == {"notes": []}
    add_note("Biology: Mitochondria", "Mitochondria make ATP.")  # e.g. added through the API
    assert [n["title"] for n in mcp_server.list_notes()["notes"]] == ["Biology: Mitochondria"]


def test_configure_database_uses_the_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", database.DB_PATH)  # restored after the test
    target = str(tmp_path / "elsewhere.db")
    monkeypatch.setenv("STUDY_BUDDY_DB", target)
    assert mcp_server.configure_database() == target
    assert database.DB_PATH == target and Path(target).exists()
