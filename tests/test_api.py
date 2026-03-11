import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "ViEng"
    assert "version" in data


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_test_no_api_key():
    response = client.post("/api/v1/test/generate", json={
        "exam_type": "toeic",
        "skill": "reading",
        "level": "intermediate",
        "num_questions": 3,
    })
    assert response.status_code == 500


def test_rag_search_empty():
    response = client.post("/api/v1/rag/search?query=grammar tenses")
    data = response.json()
    assert "results" in data or "message" in data
