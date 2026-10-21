"""Tests for the weak-spot review flow, from saving a note to ranking it.

The quiz generator is replaced by a stub, so no API key is needed.
"""
import database

QUESTION = {
    "question": "Q?",
    "options": ["a", "b", "c", "d"],
    "correct_index": 0,
    "explanation": "because",
}


def stub_quiz_generator(monkeypatch):
    import main

    monkeypatch.setattr(main, "call_claude_for_quiz", lambda notes, n, difficulty="medium": [QUESTION])


def take_quiz(client, title, notes, score, total=4):
    """Generate a quiz recorded under `title` and submit a score for it."""
    body = {"notes": notes, "num_questions": 1}
    if title is not None:
        body["source"] = title
    quiz_id = client.post("/generate-quiz", json=body).json()["quiz_id"]
    client.post(f"/quiz-history/{quiz_id}/score", json={"score": score, "total": total})
    return quiz_id


def test_generate_quiz_records_the_given_source(client, monkeypatch):
    stub_quiz_generator(monkeypatch)
    take_quiz(client, "Biology: Mitochondria", "Mitochondria make ATP.", score=1)
    history = client.get("/quiz-history").json()["history"]
    assert history[0]["source"] == "Biology: Mitochondria"


def test_generate_quiz_without_source_stays_pasted_notes(client, monkeypatch):
    stub_quiz_generator(monkeypatch)
    take_quiz(client, None, "Some notes.", score=1)
    take_quiz(client, "   ", "Some notes.", score=1)
    sources = [h["source"] for h in client.get("/quiz-history").json()["history"]]
    assert sources == ["Pasted notes", "Pasted notes"]


def test_generate_quiz_rejects_overlong_source(client, monkeypatch):
    stub_quiz_generator(monkeypatch)
    response = client.post("/generate-quiz", json={"notes": "x", "source": "t" * 201})
    assert response.status_code == 422


def test_weak_spots_empty_when_nothing_is_scored(client):
    body = client.get("/weak-spots").json()
    assert body["sources"] == []
    assert "hint" in body


def test_weak_spots_rank_saved_notes_weakest_first(client, monkeypatch):
    stub_quiz_generator(monkeypatch)
    client.post("/notes", json={"title": "Biology: Mitochondria", "text": "Mitochondria make ATP."})
    client.post("/notes", json={"title": "History: Cold War", "text": "The Cold War began in 1947."})
    take_quiz(client, "History: Cold War", "The Cold War began in 1947.", score=3)
    take_quiz(client, "Biology: Mitochondria", "Mitochondria make ATP.", score=1)

    sources = client.get("/weak-spots").json()["sources"]
    assert [s["source"] for s in sources] == ["Biology: Mitochondria", "History: Cold War"]
    assert sources[0]["avg_accuracy"] == 0.25
    assert sources[0]["scored_quizzes"] == 1


def test_weak_spots_ignore_pasted_notes_and_unsaved_titles(client, monkeypatch):
    stub_quiz_generator(monkeypatch)
    client.post("/notes", json={"title": "Biology: Mitochondria", "text": "Mitochondria make ATP."})
    take_quiz(client, None, "Pasted text.", score=0)                      # not in the library
    take_quiz(client, "Never saved", "Some text.", score=0)                # title not in the library
    take_quiz(client, "Biology: Mitochondria", "Mitochondria make ATP.", score=2)

    sources = client.get("/weak-spots").json()["sources"]
    assert [s["source"] for s in sources] == ["Biology: Mitochondria"]
