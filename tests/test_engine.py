"""Behavioral tests for the transaction state machine."""

import json
import stat
from pathlib import Path

import pytest

from cloudtxn.adapters.base import Adapter, AdapterRegistry, Config, Snapshot
from cloudtxn.engine import TransactionEngine
from cloudtxn.errors import AdapterError, ConfigurationError
from cloudtxn.models import Step, Transaction, TransactionStatus


class MemoryAdapter(Adapter):
    operation = "memory.set"

    def __init__(self, state: dict[str, str], events: list[str], fail_rollback: bool = False):
        self.state = state
        self.events = events
        self.fail_rollback = fail_rollback

    def validate(self, config: Config) -> None:
        if "key" not in config or "value" not in config:
            raise ConfigurationError("key and value are required")

    def snapshot(self, config: Config) -> Snapshot:
        return {"value": self.state[str(config["key"])]}

    def apply(self, config: Config) -> None:
        key = str(config["key"])
        self.state[key] = str(config["value"])
        self.events.append(f"apply:{key}")

    def verify(self, config: Config) -> None:
        assert self.state[str(config["key"])] == str(config["value"])

    def compensate(self, config: Config, snapshot: Snapshot) -> None:
        key = str(config["key"])
        self.events.append(f"rollback:{key}")
        if self.fail_rollback:
            raise AdapterError("rollback failed")
        self.state[key] = str(snapshot["value"])

    def verify_compensation(self, config: Config, snapshot: Snapshot) -> None:
        assert self.state[str(config["key"])] == str(snapshot["value"])


class FailingMemoryAdapter(MemoryAdapter):
    operation = "memory.fail"

    def apply(self, config: Config) -> None:
        raise AdapterError("planned failure")


class MutatingFailureAdapter(MemoryAdapter):
    operation = "memory.mutate_then_fail"

    def verify(self, config: Config) -> None:
        raise AdapterError("verification failed")


class MutatingApplyFailureAdapter(MemoryAdapter):
    operation = "memory.apply_then_fail"

    def apply(self, config: Config) -> None:
        super().apply(config)
        raise AdapterError("apply failed after mutation")


def transaction(*steps: Step) -> Transaction:
    return Transaction(apiVersion="cloudtxn.io/v1", id="test-run", steps=list(steps))


def step(identifier: str, operation: str, key: str, value: str) -> Step:
    return Step(id=identifier, operation=operation, config={"key": key, "value": value})


def test_commits_when_all_steps_verify(tmp_path: Path) -> None:
    state = {"a": "old"}
    events: list[str] = []
    engine = TransactionEngine(
        AdapterRegistry([MemoryAdapter(state, events)]), tmp_path / "journals"
    )

    result = engine.run(transaction(step("change-a", "memory.set", "a", "new")))

    assert result.status == TransactionStatus.COMMITTED
    assert state == {"a": "new"}
    assert events == ["apply:a"]


def test_rolls_back_completed_steps_in_reverse_order(tmp_path: Path) -> None:
    state = {"a": "old-a", "b": "old-b", "c": "old-c"}
    events: list[str] = []
    engine = TransactionEngine(
        AdapterRegistry([MemoryAdapter(state, events), FailingMemoryAdapter(state, events)]),
        tmp_path / "journals",
    )

    result = engine.run(
        transaction(
            step("change-a", "memory.set", "a", "new-a"),
            step("change-b", "memory.set", "b", "new-b"),
            step("fail", "memory.fail", "c", "new-c"),
        )
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert state == {"a": "old-a", "b": "old-b", "c": "old-c"}
    assert events == ["apply:a", "apply:b", "rollback:c", "rollback:b", "rollback:a"]


def test_compensates_when_apply_mutates_then_raises(tmp_path: Path) -> None:
    state = {"a": "old"}
    events: list[str] = []
    engine = TransactionEngine(
        AdapterRegistry([MutatingApplyFailureAdapter(state, events)]), tmp_path / "journals"
    )

    result = engine.run(
        transaction(step("change-a", "memory.apply_then_fail", "a", "new"))
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert state == {"a": "old"}
    assert events == ["apply:a", "rollback:a"]


def test_includes_current_step_when_postcondition_fails(tmp_path: Path) -> None:
    state = {"a": "old"}
    events: list[str] = []
    engine = TransactionEngine(
        AdapterRegistry([MutatingFailureAdapter(state, events)]), tmp_path / "journals"
    )

    result = engine.run(
        transaction(step("change-a", "memory.mutate_then_fail", "a", "new"))
    )

    assert result.status == TransactionStatus.ROLLED_BACK
    assert state == {"a": "old"}
    assert events == ["apply:a", "rollback:a"]


def test_reports_rollback_failure_and_continues_other_compensations(tmp_path: Path) -> None:
    state = {"a": "old-a", "b": "old-b", "c": "old-c"}
    events: list[str] = []
    good = MemoryAdapter(state, events)
    bad = MemoryAdapter(state, events, fail_rollback=True)
    bad.operation = "memory.bad_rollback"
    engine = TransactionEngine(
        AdapterRegistry([good, bad, FailingMemoryAdapter(state, events)]),
        tmp_path / "journals",
    )

    result = engine.run(
        transaction(
            step("change-a", "memory.set", "a", "new-a"),
            step("change-b", "memory.bad_rollback", "b", "new-b"),
            step("fail", "memory.fail", "c", "new-c"),
        )
    )

    assert result.status == TransactionStatus.ROLLBACK_FAILED
    assert state["a"] == "old-a"
    assert state["b"] == "new-b"
    assert result.rollback_errors == ["change-b: rollback failed"]
    assert events[-2:] == ["rollback:b", "rollback:a"]


def test_test_mode_verifies_then_restores_snapshot(tmp_path: Path) -> None:
    state = {"a": "old"}
    events: list[str] = []
    engine = TransactionEngine(
        AdapterRegistry([MemoryAdapter(state, events)]), tmp_path / "journals"
    )

    result = engine.test(transaction(step("change-a", "memory.set", "a", "new")))

    assert result.status == TransactionStatus.VALIDATED
    assert state == {"a": "old"}
    assert events == ["apply:a", "rollback:a"]
    records = [json.loads(line) for line in Path(result.journal_path).read_text().splitlines()]
    assert any(record["event"] == "test_succeeded" for record in records)
    assert records[-1]["status"] == "VALIDATED"


def test_unknown_operation_is_rejected_before_mutation(tmp_path: Path) -> None:
    state = {"a": "old"}
    events: list[str] = []
    engine = TransactionEngine(
        AdapterRegistry([MemoryAdapter(state, events)]), tmp_path / "journals"
    )

    with pytest.raises(ConfigurationError, match="unsupported operation"):
        engine.run(
            transaction(
                step("change-a", "memory.set", "a", "new"),
                step("unknown", "unknown.operation", "a", "other"),
            )
        )

    assert state == {"a": "old"}
    assert events == []


def test_journal_is_owner_only_and_records_terminal_status(tmp_path: Path) -> None:
    state = {"a": "old"}
    events: list[str] = []
    result = TransactionEngine(
        AdapterRegistry([MemoryAdapter(state, events)]), tmp_path / "journals"
    ).run(transaction(step("change-a", "memory.set", "a", "new")))

    journal = Path(result.journal_path)
    assert stat.S_IMODE(journal.stat().st_mode) == 0o600
    records = [json.loads(line) for line in journal.read_text().splitlines()]
    assert records[-1]["event"] == "transaction_finished"
    assert records[-1]["status"] == "COMMITTED"
