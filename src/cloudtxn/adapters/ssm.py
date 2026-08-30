"""Reversible AWS SSM String parameter updates."""

import json
from typing import Optional

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from cloudtxn.adapters.base import Adapter, Config, Snapshot
from cloudtxn.command import run_command
from cloudtxn.errors import AdapterError, ConfigurationError
from cloudtxn.safety import require_sandbox_aws


class SsmPutConfig(BaseModel):
    """Typed SSM parameter operation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: str
    region: str = "us-east-1"
    endpoint_url: Optional[AnyHttpUrl] = None
    parameter_type: str = Field(default="String", pattern=r"^String$")


class SsmPutParameterAdapter(Adapter):
    """Update and restore an existing non-secret SSM String parameter."""

    operation = "aws.ssm_put_parameter"

    def _parse(self, config: Config) -> SsmPutConfig:
        return SsmPutConfig.model_validate(config)

    def _base(self, parsed: SsmPutConfig) -> list[str]:
        args = ["aws"]
        if parsed.endpoint_url:
            args.extend(["--endpoint-url", str(parsed.endpoint_url)])
        args.extend(["--region", parsed.region, "ssm"])
        return args

    def _state(self, parsed: SsmPutConfig) -> Snapshot:
        result = run_command(
            self._base(parsed)
            + ["get-parameter", "--name", parsed.name, "--output", "json"]
        )
        document = json.loads(result.stdout)
        parameter = document["Parameter"]
        parameter_type = str(parameter["Type"])
        if parameter_type != "String":
            raise ConfigurationError("bootstrap adapter refuses SecureString and StringList")
        return {"value": str(parameter["Value"]), "type": parameter_type}

    def _put(self, parsed: SsmPutConfig, value: str) -> None:
        run_command(
            self._base(parsed)
            + [
                "put-parameter",
                "--name",
                parsed.name,
                "--type",
                "String",
                "--value",
                value,
                "--overwrite",
            ]
        )

    def _verify_value(self, parsed: SsmPutConfig, expected: str) -> None:
        state = self._state(parsed)
        if state["value"] != expected:
            raise AdapterError(f"parameter {parsed.name} did not reach the expected value")

    def validate(self, config: Config) -> None:
        parsed = self._parse(config)
        if parsed.parameter_type != "String":
            raise ConfigurationError("bootstrap adapter supports only non-secret String parameters")
        require_sandbox_aws(str(parsed.endpoint_url) if parsed.endpoint_url else None)
        run_command(["aws", "--version"])

    def snapshot(self, config: Config) -> Snapshot:
        return self._state(self._parse(config))

    def apply(self, config: Config) -> None:
        parsed = self._parse(config)
        self._put(parsed, parsed.value)

    def verify(self, config: Config) -> None:
        parsed = self._parse(config)
        self._verify_value(parsed, parsed.value)

    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        parsed = self._parse(config)
        self._put(parsed, str(snapshot["value"]))

    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        self._verify_value(self._parse(config), str(snapshot["value"]))
