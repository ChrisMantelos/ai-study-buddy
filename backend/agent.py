"""Tool-using quiz agent for the AI Study Buddy.

Instead of the fixed pipeline (BM25 -> chunks -> one Claude call), the model gets
tools and decides what to look up, how often, and when it has enough material:

    list_notes        what is in the library
    search_notes      BM25 keyword search (the model rewrites the query if it misses)
    get_note          read a whole note
    get_source_stats  quiz accuracy per note, from the SQL window-function query
    submit_quiz       final answer, validated before it is accepted

The loop is plain Anthropic tool use. `client` and `library` are passed in, so the
agent can be tested with fakes and never touches global state.
"""
import json
from collections import Counter

import database
import quality

MAX_NOTE_CHARS = 12_000       # one get_note result
MAX_MATERIAL_CHARS = 40_000   # everything handed to the verifier

TOOLS = [
    {
        "name": "list_notes",
        "description": (
            "List the titles of all notes in the library with their chunk counts. "
            "Call this first when you do not know what notes exist."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_notes",
        "description": (
            "Keyword (BM25) search over all note chunks. Returns up to top_k chunks with "
            "their source title and a score. Matching is on exact words only, so if the "
            "results are empty or off-topic, search again with synonyms or related terms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to search for."},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_note",
        "description": "Return the full text of one note, by its exact title (see list_notes).",
        "input_schema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "get_source_stats",
        "description": (
            "Return the user's quiz accuracy per note title (average accuracy and number of "
            "scored quizzes), weakest first. Use it when the user wants to review weak spots."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_quiz",
        "description": (
            "Submit the final quiz. Call it exactly once, after you have retrieved the notes "
            "the questions are based on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "questions": {"type": "array", "items": quality.QUESTION_SCHEMA},
                "sources_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Titles of the notes the questions are based on, main one first.",
                },
            },
            "required": ["questions", "sources_used"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are the quiz-building agent inside a study app. The user's notes live in a library "
    "that you can only reach through tools.\n\n"
    "How to work:\n"
    "1. If you do not know what notes exist, call list_notes.\n"
    "2. Find the relevant material with search_notes, or read a whole note with get_note. "
    "Search is keyword based: when a search comes back empty or off-topic, retry with "
    "synonyms or related terms (a few attempts at most).\n"
    "3. If the user asks to review weak spots or what they struggle with, call "
    "get_source_stats and build the quiz from the weakest note(s).\n"
    "4. When you have enough material, call submit_quiz once.\n\n"
    "Rules:\n"
    "- Base every question ONLY on text returned by the tools. Never use outside knowledge.\n"
    "- Each question has exactly 4 options, exactly one of them correct according to the "
    "notes, and a short explanation. Wrong options must be plausible but clearly wrong.\n"
    "- If after several tries you find nothing relevant, do NOT invent questions: reply "
    "with a short plain-text message saying what you could not find."
)


class AgentError(Exception):
    """The agent could not produce a usable quiz (maps to HTTP 502)."""


class NoQuizError(Exception):
    """The agent found nothing to build a quiz from (maps to HTTP 404)."""


# ------------------------------------------------------------------ the tools

def tool_list_notes(library) -> dict:
    counts = Counter(library.sources)
    return {"notes": [{"title": t, "chunks": c} for t, c in sorted(counts.items())]}


def tool_search_notes(library, query: str, top_k: int = 5) -> dict:
    top_k = max(1, min(int(top_k), 10))
    results = library.search(query, top_k=top_k)
    payload = {"count": len(results), "results": results}
    if not results:
        payload["hint"] = "No matches. Try different wording, synonyms, or list_notes."
    return payload


def tool_get_note(library, title: str) -> dict:
    titles = sorted(set(library.sources))
    match = title if title in titles else next((t for t in titles if t.lower() == title.lower()), None)
    if match is None:
        return {"error": f"No note titled '{title}'.", "available_titles": titles}
    text = "\n\n".join(c for c, s in zip(library.chunks, library.sources) if s == match)
    truncated = len(text) > MAX_NOTE_CHARS
    return {"title": match, "text": text[:MAX_NOTE_CHARS], "truncated": truncated}


def tool_get_source_stats(library) -> dict:
    """Latest running average per note title, weakest first.

    Only titles that exist in the library are returned ('Pasted notes' quizzes cannot be
    regenerated from the library, so they are left out).
    """
    titles = set(library.sources)
    latest: dict[str, float] = {}
    counts: Counter = Counter()
    # Rows are ordered by (source, created_at), so the last row per source holds the
    # running average over all of that source's scored quizzes.
    for row in database.fetch_accuracy_trend_by_source():
        if row["source"] in titles:
            latest[row["source"]] = row["running_avg_accuracy"]
            counts[row["source"]] += 1
    stats = [
        {"source": s, "avg_accuracy": acc, "scored_quizzes": counts[s]} for s, acc in latest.items()
    ]
    stats.sort(key=lambda item: item["avg_accuracy"])
    payload = {"sources": stats}
    if not stats:
        payload["hint"] = "No scored quizzes yet, so there is no weak-spot data."
    return payload


# ------------------------------------------------------------------ the loop

def _first_message(goal: str, num_questions: int, difficulty: str) -> str:
    return (
        f"Request: {goal}\n"
        f"Number of questions: exactly {num_questions}\n"
        f"Difficulty: {difficulty}"
    )


def _validate_submission(args: dict, num_questions: int, has_material: bool) -> str | None:
    if not has_material:
        return (
            "You have not retrieved any notes yet. Call search_notes or get_note first and "
            "base the quiz on what they return."
        )
    questions = args.get("questions")
    if not isinstance(questions, list):
        return "'questions' must be a list."
    if len(questions) != num_questions:
        return f"Expected exactly {num_questions} questions, got {len(questions)}."
    for i, q in enumerate(questions):
        error = quality.validate_question(q)
        if error:
            return f"Question {i}: {error}."
    return None


def _brief(name: str, payload: dict, is_error: bool) -> str:
    if is_error:
        return f"error: {payload.get('error', 'rejected')}"
    if name == "search_notes":
        sources = sorted({r["source"] for r in payload["results"]})
        return f"{payload['count']} chunks from {sources}"
    if name == "list_notes":
        return f"{len(payload['notes'])} notes"
    if name == "get_note":
        return f"{len(payload['text'])} chars from '{payload['title']}'"
    if name == "get_source_stats":
        return f"{len(payload['sources'])} sources with scores"
    return "accepted"


def _pick_primary_source(sources_used: list, retrieved_sources: list, library) -> str:
    titles = set(library.sources)
    for source in list(sources_used) + list(retrieved_sources):
        if source in titles:
            return source
    return "Agent quiz"


def run_quiz_agent(
    client,
    library,
    goal: str,
    num_questions: int = 5,
    difficulty: str = "medium",
    *,
    verify: bool = True,
    model: str | None = None,
    max_steps: int = 8,
) -> dict:
    """Run the agent. Returns questions, a trace of the tool calls and the sources used."""
    model = model or quality.MODEL
    messages = [{"role": "user", "content": _first_message(goal, num_questions, difficulty)}]
    trace: list[dict] = []
    material: dict[str, str] = {}      # text the agent actually saw -> where it came from
    retrieved_sources: list[str] = []  # in order of first appearance
    submitted: list | None = None
    sources_used: list = []

    def remember(source: str) -> None:
        if source not in retrieved_sources:
            retrieved_sources.append(source)

    for step in range(1, max_steps + 1):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = " ".join(b.text for b in response.content if b.type == "text").strip()
            raise NoQuizError(text or "The agent could not find notes to build a quiz from.")

        messages.append({"role": "assistant", "content": response.content})
        results = []

        for block in tool_uses:
            args = block.input if isinstance(block.input, dict) else {}
            is_error = False

            if block.name == "list_notes":
                payload = tool_list_notes(library)
            elif block.name == "search_notes":
                query = str(args.get("query", "")).strip()
                if not query:
                    payload, is_error = {"error": "'query' must not be empty."}, True
                else:
                    payload = tool_search_notes(library, query, args.get("top_k", 5))
                    for hit in payload["results"]:
                        material[hit["text"]] = hit["source"]
                        remember(hit["source"])
            elif block.name == "get_note":
                payload = tool_get_note(library, str(args.get("title", "")))
                if "error" in payload:
                    is_error = True
                else:
                    material[payload["text"]] = payload["title"]
                    remember(payload["title"])
            elif block.name == "get_source_stats":
                payload = tool_get_source_stats(library)
            elif block.name == "submit_quiz":
                if submitted is not None:
                    payload, is_error = {"error": "A quiz was already submitted."}, True
                else:
                    problem = _validate_submission(args, num_questions, bool(material))
                    if problem:
                        payload, is_error = {"error": problem}, True
                    else:
                        submitted = [
                            {key: q[key] for key in quality.QUESTION_KEYS} for q in args["questions"]
                        ]
                        sources_used = args.get("sources_used") or []
                        payload = {"status": "accepted"}
            else:
                payload, is_error = {"error": f"Unknown tool '{block.name}'."}, True

            trace.append(
                {
                    "step": step,
                    "tool": block.name,
                    "input": args,
                    "result": _brief(block.name, payload, is_error),
                }
            )
            result = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(payload, ensure_ascii=False),
            }
            if is_error:
                result["is_error"] = True
            results.append(result)

        messages.append({"role": "user", "content": results})
        if submitted is not None:
            break

    if submitted is None:
        raise AgentError(f"The agent did not submit a quiz within {max_steps} steps.")

    quality_report = None
    questions = submitted
    if verify:
        notes_text = "\n\n".join(material)[:MAX_MATERIAL_CHARS]
        report = quality.verify_and_repair(client, notes_text, submitted, difficulty, model=model)
        questions = report.pop("questions")
        quality_report = report
        if not questions:
            raise AgentError("No generated question passed the quality check.")

    return {
        "questions": questions,
        "trace": trace,
        "retrieved_sources": retrieved_sources,
        "primary_source": _pick_primary_source(sources_used, retrieved_sources, library),
        "quality": quality_report,
    }
