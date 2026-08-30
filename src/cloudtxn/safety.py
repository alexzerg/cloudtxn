"""Hard demo-mode isolation boundaries."""

import ipaddress
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from cloudtxn.errors import ConfigurationError


def _sandbox_root() -> Path:
    value = os.environ.get("CLOUDTXN_SANDBOX_ROOT")
    if not value:
        raise ConfigurationError("CLOUDTXN_SANDBOX_ROOT is required in demo mode")
    return Path(value).expanduser().resolve()


def _require_path_in_sandbox(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise ConfigurationError(f"{variable} is required in demo mode")
    root = _sandbox_root()
    path = Path(value).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ConfigurationError(f"{variable} must be inside {root}")
    return path


def demo_mode_enabled() -> bool:
    """Return whether hard sandbox restrictions are enabled."""

    return os.environ.get("CLOUDTXN_DEMO_MODE") == "1"


def require_sandbox_kubernetes(context: Optional[str]) -> None:
    """Reject any Kubernetes target outside the isolated demo context."""

    if not demo_mode_enabled():
        return
    _require_path_in_sandbox("KUBECONFIG")
    allowed = os.environ.get("CLOUDTXN_ALLOWED_KUBE_CONTEXT")
    if not allowed:
        raise ConfigurationError("CLOUDTXN_ALLOWED_KUBE_CONTEXT is required in demo mode")
    if context != allowed:
        raise ConfigurationError(
            f"demo mode allows only Kubernetes context {allowed!r}, got {context!r}"
        )


def require_sandbox_aws(endpoint_url: Optional[str]) -> None:
    """Reject AWS configuration or endpoints outside the isolated demo sandbox."""

    if not demo_mode_enabled():
        return
    _require_path_in_sandbox("AWS_CONFIG_FILE")
    _require_path_in_sandbox("AWS_SHARED_CREDENTIALS_FILE")
    allowed = os.environ.get("CLOUDTXN_ALLOWED_SSM_ENDPOINT")
    if not allowed:
        raise ConfigurationError("CLOUDTXN_ALLOWED_SSM_ENDPOINT is required in demo mode")
    normalized = endpoint_url.rstrip("/") if endpoint_url else None
    if normalized != allowed.rstrip("/"):
        raise ConfigurationError(
            f"demo mode allows only SSM endpoint {allowed!r}, got {endpoint_url!r}"
        )
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ConfigurationError("demo SSM endpoint must be an HTTP loopback URL")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        internal_hosts = {
            host.strip()
            for host in os.environ.get("CLOUDTXN_ALLOWED_SERVICE_HOSTS", "").split(",")
            if host.strip()
        }
        if parsed.hostname != "localhost" and parsed.hostname not in internal_hosts:
            raise ConfigurationError(
                "demo SSM endpoint must use loopback or an explicitly allowed sandbox service"
            ) from None
    else:
        if not address.is_loopback:
            raise ConfigurationError("demo SSM endpoint must use a loopback address")
