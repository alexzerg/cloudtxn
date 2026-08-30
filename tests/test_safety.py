"""Hard sandbox-boundary tests."""

from pathlib import Path

import pytest

from cloudtxn.errors import ConfigurationError
from cloudtxn.safety import require_sandbox_aws, require_sandbox_kubernetes


def sandbox_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / ".sandbox"
    root.mkdir()
    monkeypatch.setenv("CLOUDTXN_DEMO_MODE", "1")
    monkeypatch.setenv("CLOUDTXN_SANDBOX_ROOT", str(root))
    monkeypatch.setenv("KUBECONFIG", str(root / "kubeconfig"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(root / "aws" / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(root / "aws" / "credentials"))
    monkeypatch.setenv("CLOUDTXN_ALLOWED_KUBE_CONTEXT", "k3d-cloudtxn-sandbox-demo")
    monkeypatch.setenv("CLOUDTXN_ALLOWED_SSM_ENDPOINT", "http://127.0.0.1:14566")
    return root


def test_rejects_non_sandbox_kubernetes_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox_environment(monkeypatch, tmp_path)

    with pytest.raises(ConfigurationError, match="allows only Kubernetes context"):
        require_sandbox_kubernetes("production")


def test_rejects_default_kubeconfig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sandbox_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("KUBECONFIG", str(Path.home() / ".kube" / "config"))

    with pytest.raises(ConfigurationError, match="must be inside"):
        require_sandbox_kubernetes("k3d-cloudtxn-sandbox-demo")


def test_rejects_real_aws_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sandbox_environment(monkeypatch, tmp_path)

    with pytest.raises(ConfigurationError, match="allows only SSM endpoint"):
        require_sandbox_aws("https://ssm.us-east-1.amazonaws.com")


def test_accepts_exact_sandbox_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sandbox_environment(monkeypatch, tmp_path)

    require_sandbox_kubernetes("k3d-cloudtxn-sandbox-demo")
    require_sandbox_aws("http://127.0.0.1:14566")


def test_accepts_explicit_internal_sandbox_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("CLOUDTXN_ALLOWED_SSM_ENDPOINT", "http://localstack:4566")
    monkeypatch.setenv("CLOUDTXN_ALLOWED_SERVICE_HOSTS", "localstack")

    require_sandbox_aws("http://localstack:4566")
