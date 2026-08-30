"""Deterministic failure adapter for tests and demos."""

from pydantic import BaseModel, ConfigDict

from cloudtxn.adapters.base import Adapter, Config, Snapshot
from cloudtxn.errors import AdapterError


class FailConfig(BaseModel):
    """Intentional failure configuration."""

    model_config = ConfigDict(extra="forbid")
    message: str = "intentional failure"


class FailAdapter(Adapter):
    """Fail during apply without mutating state."""

    operation = "test.fail"

    def _parse(self, config: Config) -> FailConfig:
        return FailConfig.model_validate(config)

    def validate(self, config: Config) -> None:
        self._parse(config)

    def snapshot(self, config: Config) -> Snapshot:
        self._parse(config)
        return {}

    def apply(self, config: Config) -> None:
        self._parse(config)

    def verify(self, config: Config) -> None:
        parsed = self._parse(config)
        raise AdapterError(parsed.message)

    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        self._parse(config)

    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        self._parse(config)
