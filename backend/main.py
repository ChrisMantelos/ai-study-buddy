import os
import json
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from anthropic import Anthropic, APIError, APIConnectionError
from rag import NoteLibrary
import database

app = FastAPI(title="AI Study Buddy API")
library = NoteLibrary()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuizRequest(BaseModel):
    notes: str = Field(min_length=1, max_length=8000)
    num_questions: int = Field(default=5, ge=1, le=10)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class QuizResponse(BaseModel):
    quiz_id: int
    questions: list[QuizQuestion]


class AddNoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=50000)


class AddNoteResponse(BaseModel):
    title: str
    chunks_added: int
    total_chunks_in_library: int


class TopicQuizRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    num_questions: int = Field(default=5, ge=1, le=10)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")


class SubmitScoreRequest(BaseModel):
    score: int = Field(ge=0)
    total: int = Field(ge=1)


def get_client() -> Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="Server is missing an API key.")
    return Anthropic(api_key=key)


DIFFICULTY_INSTRUCTIONS = {
    "easy": "Keep questions straightforward, testing basic recall of facts stated directly in the notes.",
    "medium": "Questions should require understanding the material, not just spotting a matching phrase.",
    "hard": "Questions should require connecting multiple ideas from the notes or applying them to a new situation, not just recalling a single fact.",
}


def build_prompt(notes: str, num_questions: int, difficulty: str = "medium") -> str:
    difficulty_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS["medium"])
    return (
        f"Create exactly {num_questions} multiple-choice quiz questions "
        f"based on these study notes. Each question needs 4 options with "
        f"exactly one correct answer, and a short explanation of why that "
        f"answer is correct. {difficulty_instruction}\n\n"
        f"Notes:\n{notes}\n\n"
        f"Respond with ONLY valid JSON, no other text, in this exact shape:\n"
        f'{{"questions": [{{"question": "...", "options": ["...", "...", '
        f'"...", "..."], "correct_index": 0, "explanation": "..."}}]}}'
    )


def call_claude_for_quiz(notes: str, num_questions: int, difficulty: str = "medium") -> list[dict]:
    client = get_client()
    prompt = build_prompt(notes, num_questions, difficulty)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
    except APIConnectionError:
        raise HTTPException(status_code=502, detail="Could not reach the AI service.")
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")

    raw_text = response.content[0].text.strip()

    try:
        parsed = json.loads(raw_text)
        return parsed["questions"]
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        raise HTTPException(status_code=502, detail="AI response was not valid quiz data.")


@app.post("/generate-quiz", response_model=QuizResponse)
def generate_quiz(request: QuizRequest) -> QuizResponse:
    questions = call_claude_for_quiz(request.notes, request.num_questions, request.difficulty)
    quiz_id = database.insert_quiz_record(
        source="Pasted notes",
        num_questions=len(questions),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return QuizResponse(quiz_id=quiz_id, questions=questions)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/notes", response_model=AddNoteResponse)
def add_note(request: AddNoteRequest) -> AddNoteResponse:
    chunks_added = library.add_document(request.title, request.text)
    return AddNoteResponse(
        title=request.title,
        chunks_added=chunks_added,
        total_chunks_in_library=len(library.chunks),
    )


@app.get("/notes")
def list_notes() -> dict:
    titles = sorted(set(library.sources))
    return {"documents": titles, "total_chunks": len(library.chunks)}


@app.post("/generate-quiz-from-topic", response_model=QuizResponse)
def generate_quiz_from_topic(request: TopicQuizRequest) -> QuizResponse:
    if library.is_empty():
        raise HTTPException(status_code=400, detail="No notes in the library yet. Add some with POST /notes first.")

    relevant_chunks = library.search(request.topic, top_k=6)

    if not relevant_chunks:
        raise HTTPException(status_code=404, detail=f"No notes found matching '{request.topic}'.")

    combined_notes = "\n\n".join(chunk["text"] for chunk in relevant_chunks)
    questions = call_claude_for_quiz(combined_notes, request.num_questions, request.difficulty)

    matched_source = relevant_chunks[0]["source"]
    quiz_id = database.insert_quiz_record(
        source=matched_source,
        num_questions=len(questions),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return QuizResponse(quiz_id=quiz_id, questions=questions)


@app.post("/quiz-history/{quiz_id}/score")
def submit_score(quiz_id: int, request: SubmitScoreRequest) -> dict:
    updated = database.update_quiz_score(quiz_id, request.score, request.total)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No quiz found with id {quiz_id}.")
    return {"quiz_id": quiz_id, "score": request.score, "total": request.total}


@app.get("/quiz-history")
def get_quiz_history() -> dict:
    history = database.fetch_quiz_history_with_notes()
    return {"history": history}
