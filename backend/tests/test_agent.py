"""Tests for quality.py, agent.py and the /agent/generate-quiz endpoint.

No real API calls: the Anthropic client is replaced by a FakeClient that returns
scripted responses, so these run without a key and cost nothing.
"""
from types import SimpleNamespace as NS

import pytest

import agent
import agent_routes
import database
import quality


# ------------------------------------------------------------------- helpers

def tool_block(name, input, id="tu_1"):
    return NS(type="tool_use", name=name, input=input, id=id)


def text_block(text):
    return NS(type="text", text=text)


class FakeClient:
    """Returns the scripted responses in order and records every request."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self.scripted:
            raise AssertionError("FakeClient ran out of scripted responses")
        return NS(content=self.scripted.pop(0), usage=NS(input_tokens=1, output_tokens=1))


class FakeLibrary:
    def __init__(self, notes):
        self.chunks = list(notes.values())
        self.sources = list(notes.keys())

    def is_empty(self):
        return not self.chunks

    def search(self, query, top_k=5):
        words = set(query.lower().split())
        hits = []
        for text, source in zip(self.chunks, self.sources):
            overlap = len(words & set(text.lower().split()))
            if overlap:
                hits.append({"text": text, "source": source, "score": float(overlap)})
        hits.sort(key=lambda h: -h["score"])
        return hits[:top_k]


def good_question(n=0):
    return {
        "question": f"Q{n}?",
        "options": ["a", "b", "c", "d"],
        "correct_index": 0,
        "explanation": "because",
    }


def verdict(index, ok, reason="fine"):
    return {
        "index": index,
        "answerable_from_notes": ok,
        "exactly_one_correct": True,
        "marked_answer_correct": True,
        "reason": reason,
    }


NOTES = {
    "Biology": "Mitochondria make ATP.",
    "History": "The Bastille fell in 1789.",
}


# ------------------------------------------------------------ validate_question

@pytest.mark.parametrize(
    "mutation",
    [
        lambda q: q.pop("explanation"),
        lambda q: q.update(options=["a", "b", "c"]),
        lambda q: q.update(options=["a", "a", "b", "c"]),
        lambda q: q.update(correct_index=4),
        lambda q: q.update(correct_index=True),
        lambda q: q.update(question="  "),
    ],
)
def test_validate_question_rejects_bad_shapes(mutation):
    q = good_question()
    mutation(q)
    assert quality.validate_question(q) is not None


def test_validate_question_accepts_good_question():
    assert quality.validate_question(good_question()) is None
    assert quality.validate_question("not a dict") is not None


# ------------------------------------------------------------ verify_and_repair

def test_verify_and_repair_rewrites_failed_question():
    client = FakeClient(
        [
            [tool_block("report_verdicts", {"verdicts": [verdict(0, True), verdict(1, False, "not in notes")]})],
            [tool_block("submit_questions", {"questions": [good_question(9)]})],
            [tool_block("report_verdicts", {"verdicts": [verdict(0, True), verdict(1, True)]})],
        ]
    )
    report = quality.verify_and_repair(client, "notes", [good_question(0), good_question(1)])

    assert [q["question"] for q in report["questions"]] == ["Q0?", "Q9?"]
    assert report["dropped"] == 0
    assert report["initial_passed"] == 1
    assert [r["passed"] for r in report["rounds"]] == [1, 2]
    # the repair request carried the reviewer's reason
    assert "not in notes" in client.requests[1]["messages"][0]["content"]


def test_verify_and_repair_drops_questions_that_never_pass():
    client = FakeClient(
        [
            [tool_block("report_verdicts", {"verdicts": [verdict(0, False)]})],
            [tool_block("submit_questions", {"questions": [good_question(1)]})],
            [tool_block("report_verdicts", {"verdicts": [verdict(0, False)]})],
            [tool_block("submit_questions", {"questions": [good_question(2)]})],
            [tool_block("report_verdicts", {"verdicts": [verdict(0, False)]})],
        ]
    )
    report = quality.verify_and_repair(client, "notes", [good_question(0)], max_rounds=2)

    assert report["questions"] == []
    assert report["dropped"] == 1
    assert len(report["rounds"]) == 3
    assert len(client.requests) == 5


def test_verify_skips_reviewer_for_structurally_broken_questions():
    broken = {"question": "no options"}
    client = FakeClient([[tool_block("report_verdicts", {"verdicts": [verdict(1, True)]})]])
    verdicts = quality.verify_questions(client, "notes", [broken, good_question()])

    assert verdicts[0]["passed"] is False and "Structurally invalid" in verdicts[0]["reason"]
    assert verdicts[1]["passed"] is True
    # only the well-formed question was sent to the reviewer
    assert '"no options"' not in client.requests[0]["messages"][0]["content"]


# ------------------------------------------------------------------ the agent

def test_agent_happy_path_uses_tools_then_submits():
    client = FakeClient(
        [
            [
                text_block("Let me look."),
                tool_block("list_notes", {}, "t1"),
                tool_block("search_notes", {"query": "mitochondria ATP"}, "t2"),
            ],
            [
                tool_block(
                    "submit_quiz",
                    {"questions": [good_question(0), good_question(1)], "sources_used": ["Biology"]},
                    "t3",
                )
            ],
        ]
    )
    result = agent.run_quiz_agent(
        client, FakeLibrary(NOTES), "quiz me on mitochondria", num_questions=2, verify=False
    )

    assert len(result["questions"]) == 2
    assert [t["tool"] for t in result["trace"]] == ["list_notes", "search_notes", "submit_quiz"]
    assert result["retrieved_sources"] == ["Biology"]
    assert result["primary_source"] == "Biology"
    assert result["quality"] is None


def test_agent_rejects_invalid_submission_and_lets_model_retry():
    bad = {"questions": [{**good_question(0), "options": ["a", "b", "c"]}], "sources_used": ["Biology"]}
    ok = {"questions": [good_question(0)], "sources_used": ["Biology"]}
    client = FakeClient(
        [
            [tool_block("search_notes", {"query": "mitochondria"}, "t1")],
            [tool_block("submit_quiz", bad, "t2")],
            [tool_block("submit_quiz", ok, "t3")],
        ]
    )
    result = agent.run_quiz_agent(client, FakeLibrary(NOTES), "mitochondria", num_questions=1, verify=False)

    assert len(result["questions"]) == 1
    last_result = client.requests[2]["messages"][-1]["content"][0]
    assert last_result["is_error"] is True
    assert "options" in last_result["content"]


def test_agent_cannot_submit_before_retrieving_anything():
    ok = {"questions": [good_question(0)], "sources_used": []}
    client = FakeClient(
        [
            [tool_block("submit_quiz", ok, "t1")],
            [tool_block("search_notes", {"query": "bastille"}, "t2")],
            [tool_block("submit_quiz", ok, "t3")],
        ]
    )
    result = agent.run_quiz_agent(client, FakeLibrary(NOTES), "bastille", num_questions=1, verify=False)

    assert "not retrieved any notes" in client.requests[1]["messages"][-1]["content"][0]["content"]
    assert result["primary_source"] == "History"  # fell back to what it retrieved


def test_agent_raises_when_model_gives_up_in_plain_text():
    client = FakeClient([[text_block("I found nothing relevant.")]])
    with pytest.raises(agent.NoQuizError, match="nothing relevant"):
        agent.run_quiz_agent(client, FakeLibrary(NOTES), "quantum gravity", num_questions=1)


def test_agent_stops_after_max_steps():
    client = FakeClient([[tool_block("list_notes", {})] for _ in range(3)])
    with pytest.raises(agent.AgentError):
        agent.run_quiz_agent(client, FakeLibrary(NOTES), "anything", num_questions=1, max_steps=3)


def test_agent_with_verify_returns_quality_report():
    client = FakeClient(
        [
            [tool_block("search_notes", {"query": "mitochondria"}, "t1")],
            [tool_block("submit_quiz", {"questions": [good_question(0)], "sources_used": ["Biology"]}, "t2")],
            [tool_block("report_verdicts", {"verdicts": [verdict(0, True)]})],
        ]
    )
    result = agent.run_quiz_agent(client, FakeLibrary(NOTES), "mitochondria", num_questions=1, verify=True)

    assert result["quality"]["initial_passed"] == 1
    assert result["quality"]["dropped"] == 0
    assert "Mitochondria make ATP." in client.requests[-1]["messages"][0]["content"]


def test_search_tool_clamps_top_k_and_hints_on_empty():
    lib = FakeLibrary(NOTES)
    assert agent.tool_search_notes(lib, "mitochondria", top_k=999)["count"] == 1
    empty = agent.tool_search_notes(lib, "zzz")
    assert empty["count"] == 0 and "hint" in empty


def test_get_note_matches_case_insensitively_and_lists_titles_on_miss():
    lib = FakeLibrary(NOTES)
    assert agent.tool_get_note(lib, "biology")["title"] == "Biology"
    miss = agent.tool_get_note(lib, "Chemistry")
    assert "error" in miss and miss["available_titles"] == ["Biology", "History"]


def test_source_stats_weakest_first_and_ignores_pasted_notes(client):
    q1 = database.insert_quiz_record("Biology", 4, "2026-01-01T10:00:00")
    database.update_quiz_score(q1, score=1, total=4)
    q2 = database.insert_quiz_record("History", 4, "2026-01-02T10:00:00")
    database.update_quiz_score(q2, score=3, total=4)
    q3 = database.insert_quiz_record("Pasted notes", 4, "2026-01-03T10:00:00")
    database.update_quiz_score(q3, score=0, total=4)

    stats = agent.tool_get_source_stats(FakeLibrary(NOTES))["sources"]
    assert [s["source"] for s in stats] == ["Biology", "History"]
    assert stats[0]["avg_accuracy"] == 0.25


# ----------------------------------------------------------------- the endpoint

def test_agent_endpoint_empty_library(client):
    response = client.post("/agent/generate-quiz", json={"goal": "quiz me"})
    assert response.status_code == 400


def test_agent_endpoint_missing_api_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client.post("/notes", json={"title": "Biology Chapter 1", "text": "Mitochondria make ATP."})
    response = client.post("/agent/generate-quiz", json={"goal": "mitochondria"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Server is missing an API key."


def test_agent_endpoint_validates_input(client):
    assert client.post("/agent/generate-quiz", json={"goal": ""}).status_code == 422
    assert client.post("/agent/generate-quiz", json={"goal": "x", "num_questions": 50}).status_code == 422


def test_agent_endpoint_saves_quiz_under_primary_source(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client.post("/notes", json={"title": "Biology Chapter 1", "text": "Mitochondria make ATP."})

    def fake_agent(*args, **kwargs):
        return {
            "questions": [good_question(0)],
            "trace": [{"step": 1, "tool": "search_notes", "input": {}, "result": "1 chunks"}],
            "retrieved_sources": ["Biology Chapter 1"],
            "primary_source": "Biology Chapter 1",
            "quality": {"initial_passed": 1, "dropped": 0, "requested": 1, "rounds": []},
        }

    monkeypatch.setattr(agent_routes, "run_quiz_agent", fake_agent)
    response = client.post("/agent/generate-quiz", json={"goal": "mitochondria", "num_questions": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "Biology Chapter 1"
    assert body["questions"][0]["correct_index"] == 0
    history = client.get("/quiz-history").json()["history"]
    assert history[0]["quiz_id"] == body["quiz_id"] and history[0]["source"] == "Biology Chapter 1"


@pytest.mark.parametrize(
    "error, status",
    [(agent.NoQuizError("nothing found"), 404), (agent.AgentError("gave up"), 502)],
)
def test_agent_endpoint_maps_agent_errors(client, monkeypatch, error, status):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client.post("/notes", json={"title": "Biology Chapter 1", "text": "Mitochondria make ATP."})

    def failing_agent(*args, **kwargs):
        raise error

    monkeypatch.setattr(agent_routes, "run_quiz_agent", failing_agent)
    response = client.post("/agent/generate-quiz", json={"goal": "mitochondria"})
    assert response.status_code == status
    assert response.json()["detail"] == str(error)
