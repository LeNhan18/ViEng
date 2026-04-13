import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "ViEng"
    assert "version" in data


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_test_when_llm_fails(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("Simulated LLM failure (e.g. missing API key)")

    import app.services.llm_service as llm_mod

    monkeypatch.setattr(llm_mod.llm_service, "generate_questions", boom)

    response = client.post(
        "/api/v1/test/generate",
        json={
            "exam_type": "toeic",
            "skill": "reading",
            "level": "intermediate",
            "num_questions": 3,
        },
    )
    assert response.status_code == 500
    assert "thử lại" in response.json().get("detail", "")


def test_generate_test_mocked_llm(client, monkeypatch):
    payload = [
        {
            "id": 1,
            "content": "Test question?",
            "options": ["A. one", "B. two", "C. three", "D. four"],
            "correct_answer": "A",
        }
    ]

    async def fake_generate(*args, **kwargs):
        return json.dumps(payload)

    import app.services.llm_service as llm_mod

    monkeypatch.setattr(llm_mod.llm_service, "generate_questions", fake_generate)

    response = client.post(
        "/api/v1/test/generate",
        json={
            "exam_type": "toeic",
            "skill": "reading",
            "level": "intermediate",
            "num_questions": 1,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data.get("questions", [])) == 1
    assert data["questions"][0]["correct_answer"] == "A"


def test_rag_search_empty(client):
    response = client.post("/api/v1/rag/search?query=grammar+tenses")
    data = response.json()
    assert "results" in data or "message" in data


def test_db_status_when_disabled(client):
    """USE_DATABASE defaults false — expect 503 from dependency."""
    response = client.get("/api/v1/db/status")
    assert response.status_code == 503
