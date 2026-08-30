"""Business Web App boundary tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from cloudtxn.web import app


def test_health_reports_local_ai_and_no_production_access(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / ".sandbox"
    root.mkdir()
    monkeypatch.setenv("CLOUDTXN_DEMO_MODE", "1")
    monkeypatch.setenv("CLOUDTXN_SANDBOX_ROOT", str(root))
    monkeypatch.setenv("CLOUDTXN_OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("CLOUDTXN_OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("CLOUDTXN_ALLOWED_KUBE_CONTEXT", "k3d-cloudtxn-sandbox-demo")
    monkeypatch.setenv("CLOUDTXN_ALLOWED_SSM_ENDPOINT", "http://127.0.0.1:14566")

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["production_access"] is False
    assert response.json()["ai"] == {"provider": "local-ollama", "model": "test-model"}
