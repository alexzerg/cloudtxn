"""Reversible Kubernetes Deployment scaling."""

import json
import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from cloudtxn.adapters.base import Adapter, Config, Snapshot
from cloudtxn.command import run_command
from cloudtxn.errors import AdapterError
from cloudtxn.safety import require_sandbox_kubernetes


class KubernetesScaleConfig(BaseModel):
    """Typed Kubernetes scale operation."""

    model_config = ConfigDict(extra="forbid")

    context: Optional[str] = None
    namespace: str = "default"
    deployment: str = Field(min_length=1)
    replicas: int = Field(ge=0, le=1000)
    timeout_seconds: int = Field(default=90, ge=1, le=600)
    wait_for_ready: bool = True
    observation_seconds: int = Field(default=0, ge=0, le=30)


class KubernetesScaleAdapter(Adapter):
    """Scale a Deployment and restore its prior replica count."""

    operation = "kubernetes.scale_deployment"

    def _parse(self, config: Config) -> KubernetesScaleConfig:
        return KubernetesScaleConfig.model_validate(config)

    def _base(self, parsed: KubernetesScaleConfig) -> list[str]:
        args = ["kubectl"]
        if parsed.context:
            args.extend(["--context", parsed.context])
        args.extend(["--namespace", parsed.namespace])
        return args

    def _state(self, parsed: KubernetesScaleConfig) -> Snapshot:
        result = run_command(
            self._base(parsed)
            + ["get", "deployment", parsed.deployment, "--output", "json"]
        )
        document = json.loads(result.stdout)
        replicas = int(document.get("spec", {}).get("replicas", 1))
        ready = int(document.get("status", {}).get("readyReplicas", 0))
        return {"replicas": replicas, "ready_replicas": ready}

    def _set_replicas(
        self,
        parsed: KubernetesScaleConfig,
        replicas: int,
        *,
        wait_for_ready: Optional[bool] = None,
    ) -> None:
        run_command(
            self._base(parsed)
            + ["scale", "deployment", parsed.deployment, f"--replicas={replicas}"]
        )
        should_wait = parsed.wait_for_ready if wait_for_ready is None else wait_for_ready
        if should_wait:
            run_command(
                self._base(parsed)
                + [
                    "rollout",
                    "status",
                    f"deployment/{parsed.deployment}",
                    f"--timeout={parsed.timeout_seconds}s",
                ]
            )
        elif parsed.observation_seconds:
            time.sleep(parsed.observation_seconds)

    def _verify_replicas(
        self,
        parsed: KubernetesScaleConfig,
        expected: int,
        *,
        require_ready: Optional[bool] = None,
    ) -> None:
        state = self._state(parsed)
        should_require_ready = (
            parsed.wait_for_ready if require_ready is None else require_ready
        )
        desired_matches = state["replicas"] == expected
        ready_matches = state["ready_replicas"] == expected
        if not desired_matches or (should_require_ready and not ready_matches):
            raise AdapterError(
                f"deployment {parsed.deployment} expected {expected} replicas, got {state}"
            )

    def validate(self, config: Config) -> None:
        parsed = self._parse(config)
        require_sandbox_kubernetes(parsed.context)
        run_command(["kubectl", "version", "--client"])

    def snapshot(self, config: Config) -> Snapshot:
        return self._state(self._parse(config))

    def apply(self, config: Config) -> None:
        parsed = self._parse(config)
        self._set_replicas(parsed, parsed.replicas)

    def verify(self, config: Config) -> None:
        parsed = self._parse(config)
        self._verify_replicas(parsed, parsed.replicas)

    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        parsed = self._parse(config)
        self._set_replicas(
            parsed,
            int(snapshot["replicas"]),
            wait_for_ready=True,
        )

    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        self._verify_replicas(
            self._parse(config),
            int(snapshot["replicas"]),
            require_ready=True,
        )
