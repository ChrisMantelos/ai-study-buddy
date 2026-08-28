import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from anthropic import Anthropic, APIError, APIConnectionError
from rag import NoteLibrary

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


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class QuizResponse(BaseModel):
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


def get_client() -> Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="Server is missing an API key.")
    return Anthropic(api_key=key)


def build_prompt(notes: str, num_questions: int) -> str:
    return (
        f"Create exactly {num_questions} multiple-choice quiz questions "
        f"based on these study notes. Each question needs 4 options with "
        f"exactly one correct answer, and a short explanation of why that "
        f"answer is correct.\n\n"
        f"Notes:\n{notes}\n\n"
        f"Respond with ONLY valid JSON, no other text, in this exact shape:\n"
        f'{{"questions": [{{"question": "...", "options": ["...", "...", '
        f'"...", "..."], "correct_index": 0, "explanation": "..."}}]}}'
    )


@app.post("/generate-quiz", response_model=QuizResponse)
def generate_quiz(request: QuizRequest) -> QuizResponse:
    client = get_client()
    prompt = build_prompt(request.notes, request.num_questions)

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
        return QuizResponse(**parsed)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="AI response was not valid quiz data.")


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

    client = get_client()
    prompt = build_prompt(combined_notes, request.num_questions)

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
        return QuizResponse(**parsed)
    except (json.JSONDecodeError, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="AI response was not valid quiz data.")
