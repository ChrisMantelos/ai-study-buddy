"""HTTP endpoint for the quiz agent.

Kept out of main.py so the existing endpoints stay untouched (they are the baseline
that evaluate.py compares against). main.py only needs:

    from agent_routes import register_agent_routes
    register_agent_routes(app, lambda: library, get_client)
"""
from datetime import datetime, timezone

from anthropic import APIConnectionError, APIError
from fastapi import HTTPException
from pydantic import BaseModel, Field

import database
from agent import AgentError, NoQuizError, run_quiz_agent, tool_get_source_stats


class AgentQuizRequest(BaseModel):
    goal: str = Field(
        min_length=1,
        max_length=500,
        description="What to study, e.g. 'quiz me on mitochondria' or 'review my weak spots'.",
    )
    num_questions: int = Field(default=5, ge=1, le=10)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    verify: bool = Field(default=True, description="Check every question against the notes and rewrite bad ones.")


class AgentQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class AgentQuizResponse(BaseModel):
    quiz_id: int
    questions: list[AgentQuestion]
    source: str
    trace: list[dict]
    quality: dict | None = None


def register_agent_routes(app, get_library, get_client) -> None:
    """`get_library` is a callable so the route always sees the current library object."""

    @app.get("/weak-spots")
    def weak_spots() -> dict:
        """Saved notes ranked by the user's quiz accuracy, weakest first (no AI call)."""
        return tool_get_source_stats(get_library())

    @app.post("/agent/generate-quiz", response_model=AgentQuizResponse)
    def agent_generate_quiz(request: AgentQuizRequest) -> AgentQuizResponse:
        library = get_library()
        if library.is_empty():
            raise HTTPException(
                status_code=400,
                detail="No notes in the library yet. Add some with POST /notes first.",
            )
        client = get_client()

        try:
            result = run_quiz_agent(
                client,
                library,
                request.goal,
                request.num_questions,
                request.difficulty,
                verify=request.verify,
            )
        except NoQuizError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except APIConnectionError:
            raise HTTPException(status_code=502, detail="Could not reach the AI service.")
        except APIError as exc:
            raise HTTPException(status_code=502, detail=f"AI service error: {exc}")

        quiz_id = database.insert_quiz_record(
            source=result["primary_source"],
            num_questions=len(result["questions"]),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return AgentQuizResponse(
            quiz_id=quiz_id,
            questions=result["questions"],
            source=result["primary_source"],
            trace=result["trace"],
            quality=result["quality"],
        )
