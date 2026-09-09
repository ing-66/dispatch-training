"""Smoke test that intentionally knows only the training API and its database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.main import app

with TestClient(app) as client:
    response = client.get("/api/health")
    response.raise_for_status()
    body = response.json()
    assert body["runtime_dependencies"] == ["training_database"]
    print("Detachment A passed: training API has no hotline/Qdrant/LLM runtime dependency.")
