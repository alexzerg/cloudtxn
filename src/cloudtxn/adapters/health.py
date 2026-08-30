"""Non-mutating business health assertion with visible stabilization time."""

import os
import time

import httpx
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from cloudtxn.adapters.base import Adapter, Config, Snapshot
from cloudtxn.errors import AdapterError, ConfigurationError


class HealthAssertionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: AnyHttpUrl
    expected_status: int = Field(default=200, ge=100, le=599)
    stabilization_seconds: int = Field(default=10, ge=0, le=30)


class HealthAssertionAdapter(Adapter):
    operation = "http.assert_payment_health"

    def _parse(self, config: Config) -> HealthAssertionConfig:
        return HealthAssertionConfig.model_validate(config)

    def validate(self, config: Config) -> None:
        parsed = self._parse(config)
        allowed = os.environ.get("CLOUDTXN_PAYMENT_HEALTH_URL", "").rstrip("/")
        if not allowed or str(parsed.url).rstrip("/") != allowed:
            raise ConfigurationError("payment health URL is outside the sandbox allowlist")

    def snapshot(self, config: Config) -> Snapshot:
        self._parse(config)
        return {}

    def apply(self, config: Config) -> None:
        parsed = self._parse(config)
        deadline = time.monotonic() + parsed.stabilization_seconds
        last_status = 0
        while True:
            response = httpx.get(str(parsed.url), timeout=10)
            last_status = response.status_code
            if last_status == parsed.expected_status:
                return
            if time.monotonic() >= deadline:
                break
            time.sleep(0.25)
        raise AdapterError(
            f"payment health expected HTTP {parsed.expected_status}, "
            f"received HTTP {last_status}"
        )

    def verify(self, config: Config) -> None:
        self._parse(config)

    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        self._parse(config)

    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        self._parse(config)
