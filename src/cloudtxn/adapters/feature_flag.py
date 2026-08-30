"""Reversible payment feature-flag operation."""

import httpx
from pydantic import AnyHttpUrl, BaseModel, ConfigDict

from cloudtxn.adapters.base import Adapter, Config, Snapshot
from cloudtxn.errors import AdapterError, ConfigurationError


class FeatureFlagConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: AnyHttpUrl
    enabled: bool


class FeatureFlagAdapter(Adapter):
    operation = "feature_flag.set"

    def _parse(self, config: Config) -> FeatureFlagConfig:
        return FeatureFlagConfig.model_validate(config)

    def _allowed_url(self) -> str:
        import os

        value = os.environ.get("CLOUDTXN_FEATURE_FLAG_URL")
        if not value:
            raise ConfigurationError("CLOUDTXN_FEATURE_FLAG_URL is required")
        return value.rstrip("/")

    def validate(self, config: Config) -> None:
        parsed = self._parse(config)
        if str(parsed.url).rstrip("/") != self._allowed_url():
            raise ConfigurationError("feature flag URL is outside the sandbox allowlist")

    def snapshot(self, config: Config) -> Snapshot:
        parsed = self._parse(config)
        response = httpx.get(str(parsed.url), timeout=10)
        response.raise_for_status()
        return {"enabled": bool(response.json()["enabled"])}

    def _set(self, parsed: FeatureFlagConfig, enabled: bool) -> None:
        response = httpx.put(str(parsed.url), json={"enabled": enabled}, timeout=10)
        response.raise_for_status()

    def apply(self, config: Config) -> None:
        parsed = self._parse(config)
        self._set(parsed, parsed.enabled)

    def verify(self, config: Config) -> None:
        parsed = self._parse(config)
        state = self.snapshot(config)
        if state["enabled"] is not parsed.enabled:
            raise AdapterError("feature flag did not reach the requested state")

    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        self._set(self._parse(config), bool(snapshot["enabled"]))

    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        state = self.snapshot(config)
        if state["enabled"] is not bool(snapshot["enabled"]):
            raise AdapterError("feature flag compensation was not verified")
