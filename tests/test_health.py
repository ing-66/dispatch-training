import os

os.environ.setdefault("TRAINING_APP_ENV", "test")

from fastapi.testclient import TestClient

from backend.main import app


def test_health_declares_only_training_database_dependency():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["runtime_dependencies"] == ["training_database"]
