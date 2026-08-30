"""Adapter contract and registry."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from cloudtxn.errors import ConfigurationError

Snapshot = dict[str, Any]
Config = dict[str, Any]


class Adapter(ABC):
    """A curated reversible cloud operation."""

    operation: str

    @abstractmethod
    def validate(self, config: Config) -> None:
        """Reject unsafe or malformed configuration before any mutation."""

    @abstractmethod
    def snapshot(self, config: Config) -> Snapshot:
        """Capture the exact state required for compensation."""

    @abstractmethod
    def apply(self, config: Config) -> None:
        """Apply the requested mutation."""

    @abstractmethod
    def verify(self, config: Config) -> None:
        """Verify the requested postcondition."""

    @abstractmethod
    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        """Restore the captured pre-state."""

    @abstractmethod
    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        """Verify restoration of the captured pre-state."""


class AdapterRegistry:
    """Resolve only explicitly registered operation types."""

    def __init__(self, adapters: Iterable[Adapter] = ()) -> None:
        self._adapters = {adapter.operation: adapter for adapter in adapters}

    def register(self, adapter: Adapter) -> None:
        """Register or replace one adapter."""

        self._adapters[adapter.operation] = adapter

    def get(self, operation: str) -> Adapter:
        """Return an adapter or reject the plan before mutation."""

        try:
            return self._adapters[operation]
        except KeyError as error:
            raise ConfigurationError(f"unsupported operation: {operation}") from error
