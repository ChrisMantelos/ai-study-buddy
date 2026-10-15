"""Quiz quality checks: review questions against the notes and repair the bad ones.

Two building blocks:

- verify_questions: a reviewer call that judges every question against a piece of text.
- verify_and_repair: verify, rewrite the failing questions, verify again (bounded
  number of rounds) and return only the questions that pass.

Both use forced tool calls, so the model answers in a fixed schema instead of
free text that has to be parsed.
"""
import json
import os

MODEL = os.getenv("STUDY_BUDDY_MODEL", "claude-sonnet-4-6")
# Used by evaluate.py. Set STUDY_BUDDY_JUDGE_MODEL to a different model than the one
# that writes the quiz, otherwise the model is grading its own homework.
JUDGE_MODEL = os.getenv("STUDY_BUDDY_JUDGE_MODEL", MODEL)

QUESTION_KEYS = ("question", "options", "correct_index", "explanation")

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 4,
            "maxItems": 4,
        },
        "correct_index": {"type": "integer", "minimum": 0, "maximum": 3},
        "explanation": {"type": "string"},
    },
    "required": list(QUESTION_KEYS),
}


def validate_question(q) -> str | None:
    """Return a description of what is wrong with a question, or None if it is well formed."""
    if not isinstance(q, dict):
        return "a question must be an object"
    for key in QUESTION_KEYS:
        if key not in q:
            return f"missing field '{key}'"
    if not isinstance(q["question"], str) or not q["question"].strip():
        return "'question' must be a non-empty string"
    options = q["options"]
    if (
        not isinstance(options, list)
        or len(options) != 4
        or not all(isinstance(o, str) and o.strip() for o in options)
    ):
        return "'options' must be a list of exactly 4 non-empty strings"
    index = q["correct_index"]
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 3:
        return "'correct_index' must be an integer from 0 to 3"
    if len({o.strip().lower() for o in options}) != 4:
        return "the 4 options must be different from each other"
    if not isinstance(q["explanation"], str) or not q["explanation"].strip():
        return "'explanation' must be a non-empty string"
    return None


def forced_tool_call(client, *, model, system, user, tool, max_tokens=4096) -> dict:
    """Call the model and force it to answer through `tool`. Returns the tool input."""
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input
    raise ValueError(f"The model did not return the expected '{tool['name']}' tool call.")


# ---------------------------------------------------------------- verification

VERDICT_TOOL = {
    "name": "report_verdicts",
    "description": "Report exactly one verdict per quiz question, using the question's index.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "answerable_from_notes": {"type": "boolean"},
                        "exactly_one_correct": {"type": "boolean"},
                        "marked_answer_correct": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "index",
                        "answerable_from_notes",
                        "exactly_one_correct",
                        "marked_answer_correct",
                        "reason",
                    ],
                },
            }
        },
        "required": ["verdicts"],
    },
}

VERIFY_SYSTEM = (
    "You are a strict reviewer of multiple-choice study questions. You receive study "
    "notes and a list of questions. The notes are the only source of truth: ignore "
    "anything you know from outside them. For every question decide:\n"
    "- answerable_from_notes: the notes contain what is needed to determine the right answer.\n"
    "- exactly_one_correct: exactly one of the four options is correct according to the "
    "notes. Fail this if two options are defensible, or if none is.\n"
    "- marked_answer_correct: the option at correct_index is the correct one according "
    "to the notes.\n"
    "Give a one-sentence reason that is specific enough for someone to fix the question. "
    "Return one verdict per question, using the question's index."
)


def verify_questions(client, notes_text: str, questions: list, model: str | None = None) -> list[dict]:
    """Judge every question against `notes_text`.

    Returns one verdict per question, in order: {"index", "passed", "reason", ...}.
    A question passes only if all three criteria hold. Structurally broken questions
    fail without being sent to the reviewer.
    """
    verdicts: dict[int, dict] = {}
    payload = []
    for i, q in enumerate(questions):
        error = validate_question(q)
        if error:
            verdicts[i] = {"index": i, "passed": False, "reason": f"Structurally invalid: {error}."}
        else:
            payload.append({**q, "index": i})

    if payload:
        user = (
            f"Study notes:\n{notes_text}\n\n"
            f"Quiz questions (JSON):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "Review every question using only the notes."
        )
        result = forced_tool_call(
            client, model=model or MODEL, system=VERIFY_SYSTEM, user=user, tool=VERDICT_TOOL
        )
        by_index = {v.get("index"): v for v in result.get("verdicts", []) if isinstance(v, dict)}
        for item in payload:
            i = item["index"]
            verdict = by_index.get(i)
            if verdict is None:
                verdicts[i] = {
                    "index": i,
                    "passed": False,
                    "reason": "The reviewer returned no verdict for this question.",
                }
                continue
            passed = all(
                bool(verdict.get(key))
                for key in ("answerable_from_notes", "exactly_one_correct", "marked_answer_correct")
            )
            verdicts[i] = {**verdict, "index": i, "passed": passed}

    return [verdicts[i] for i in range(len(questions))]


# ---------------------------------------------------------------------- repair

REPAIR_TOOL = {
    "name": "submit_questions",
    "description": "Submit the rewritten questions, in the same order as the flawed ones were given.",
    "input_schema": {
        "type": "object",
        "properties": {"questions": {"type": "array", "items": QUESTION_SCHEMA}},
        "required": ["questions"],
    },
}

REPAIR_SYSTEM = (
    "You fix flawed multiple-choice study questions. Use ONLY the notes provided. For each "
    "flawed question, rewrite it so that it is answerable from the notes, has exactly one "
    "correct option out of 4, and correct_index points at that option. Keep the same topic "
    "where possible, keep the requested difficulty, and make the wrong options plausible but "
    "clearly wrong according to the notes. Return exactly one rewritten question per flawed "
    "question, in the same order."
)


def repair_questions(
    client, notes_text: str, flawed: list[tuple], difficulty: str = "medium", model: str | None = None
) -> list:
    """Rewrite flawed questions. `flawed` is a list of (question, reason) pairs."""
    listing = [{"question": q, "problem": reason} for q, reason in flawed]
    user = (
        f"Study notes:\n{notes_text}\n\n"
        f"Difficulty: {difficulty}\n\n"
        f"Flawed questions and what is wrong with each (JSON):\n"
        f"{json.dumps(listing, ensure_ascii=False)}\n\n"
        f"Rewrite all {len(flawed)} of them."
    )
    result = forced_tool_call(
        client, model=model or MODEL, system=REPAIR_SYSTEM, user=user, tool=REPAIR_TOOL
    )
    return result.get("questions", [])


# ------------------------------------------------------------ verify + repair

def verify_and_repair(
    client,
    notes_text: str,
    questions: list,
    difficulty: str = "medium",
    max_rounds: int = 2,
    model: str | None = None,
) -> dict:
    """Verify, rewrite what fails, verify again. At most `max_rounds` rewrites.

    Returns only questions that passed the last verification. Questions that still
    fail are dropped, so the result can be shorter than the input.
    """
    current = list(questions)
    rounds = []
    verdicts: list[dict] = []

    for round_no in range(max_rounds + 1):
        verdicts = verify_questions(client, notes_text, current, model=model)
        failures = [v for v in verdicts if not v["passed"]]
        rounds.append(
            {
                "round": round_no,
                "checked": len(current),
                "passed": len(current) - len(failures),
                "failures": [{"index": v["index"], "reason": v.get("reason", "")} for v in failures],
            }
        )
        if not failures or round_no == max_rounds:
            break

        replacements = repair_questions(
            client,
            notes_text,
            [(current[v["index"]], v.get("reason", "")) for v in failures],
            difficulty,
            model=model,
        )
        if len(replacements) != len(failures):
            break
        for verdict, new_question in zip(failures, replacements):
            if validate_question(new_question) is None:
                current[verdict["index"]] = new_question

    kept = [q for q, v in zip(current, verdicts) if v["passed"]]
    return {
        "questions": kept,
        "requested": len(questions),
        "dropped": len(current) - len(kept),
        "initial_passed": rounds[0]["passed"],
        "rounds": rounds,
    }
