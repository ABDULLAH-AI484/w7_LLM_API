import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_stub_returns_schema(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    response = client.post("/triage", json={"text": "hello"})
    assert response.status_code == 200
    assert set(response.json()) == {"category", "urgency", "confidence", "reason"}


def test_invalid_input_names_field(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    response = client.post("/triage", json={"text": ""})
    assert response.status_code == 422
    assert any("text" in str(item["loc"]) for item in response.json()["detail"])


def test_extra_field_rejected(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    response = client.post("/triage", json={"text": "hello", "secret": "no"})
    assert response.status_code == 422


def test_disabled_returns_deterministic_fallback(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    response = client.post("/triage", json={"text": "I need a refund"})
    assert response.status_code == 200
    assert response.json()["category"] == "billing"
    monkeypatch.delenv("LLM_ENABLED", raising=False)


def test_json_extraction():
    from app.main import _validate
    result = _validate('Here is the answer:\n```json\n{"category":"bug","urgency":"high","confidence":0.9,"reason":"It is broken."}\n```')
    assert result.category.value == "bug"
