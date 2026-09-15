def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_quiz_rejects_empty_notes(client):
    response = client.post("/generate-quiz", json={"notes": "", "num_questions": 3})
    assert response.status_code == 422


def test_generate_quiz_rejects_too_many_questions(client):
    response = client.post("/generate-quiz", json={"notes": "some notes", "num_questions": 50})
    assert response.status_code == 422


def test_generate_quiz_rejects_invalid_difficulty(client):
    response = client.post(
        "/generate-quiz",
        json={"notes": "some notes", "num_questions": 3, "difficulty": "impossible"},
    )
    assert response.status_code == 422


def test_generate_quiz_missing_api_key(client):
    response = client.post("/generate-quiz", json={"notes": "The heart pumps blood.", "num_questions": 3})
    assert response.status_code == 500
    assert response.json()["detail"] == "Server is missing an API key."


def test_add_note_and_list(client):
    add_response = client.post(
        "/notes",
        json={"title": "Biology Chapter 1", "text": "Mitochondria are the powerhouse of the cell."},
    )
    assert add_response.status_code == 200
    body = add_response.json()
    assert body["title"] == "Biology Chapter 1"
    assert body["chunks_added"] == 1

    list_response = client.get("/notes")
    assert list_response.status_code == 200
    assert list_response.json() == {"documents": ["Biology Chapter 1"], "total_chunks": 1}


def test_generate_quiz_from_topic_empty_library(client):
    response = client.post(
        "/generate-quiz-from-topic",
        json={"topic": "mitochondria", "num_questions": 3},
    )
    assert response.status_code == 400


def test_generate_quiz_from_topic_no_match(client):
    client.post(
        "/notes",
        json={"title": "Biology Chapter 1", "text": "Mitochondria are the powerhouse of the cell."},
    )
    response = client.post(
        "/generate-quiz-from-topic",
        json={"topic": "quantum physics black holes xyz123", "num_questions": 3},
    )
    assert response.status_code == 404


def test_generate_quiz_from_topic_match_reaches_ai_call(client):
    client.post(
        "/notes",
        json={"title": "Biology Chapter 1", "text": "Mitochondria are the powerhouse of the cell."},
    )
    response = client.post(
        "/generate-quiz-from-topic",
        json={"topic": "mitochondria", "num_questions": 3},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Server is missing an API key."


def test_submit_score_nonexistent_quiz(client):
    response = client.post("/quiz-history/999/score", json={"score": 2, "total": 3})
    assert response.status_code == 404


def test_quiz_history_starts_empty(client):
    response = client.get("/quiz-history")
    assert response.status_code == 200
    assert response.json() == {"history": []}


def test_accuracy_trend_starts_empty(client):
    response = client.get("/quiz-history/stats")
    assert response.status_code == 200
    assert response.json() == {"trend": []}


def test_accuracy_trend_computes_running_average(client):
    import database

    q1 = database.insert_quiz_record("Biology", 3, "2026-01-01T10:00:00")
    database.update_quiz_score(q1, score=1, total=3)

    q2 = database.insert_quiz_record("Biology", 3, "2026-01-02T10:00:00")
    database.update_quiz_score(q2, score=2, total=3)

    response = client.get("/quiz-history/stats")
    assert response.status_code == 200
    trend = response.json()["trend"]

    assert len(trend) == 2
    assert trend[0]["running_avg_accuracy"] == 0.33
    assert trend[1]["running_avg_accuracy"] == 0.5
