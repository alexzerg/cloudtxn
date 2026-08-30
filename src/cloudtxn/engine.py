"""CloudTxn execution and reverse compensation state machine."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cloudtxn.adapters.base import Adapter, AdapterRegistry, Snapshot
from cloudtxn.journal import Journal
from cloudtxn.models import Step, Transaction, TransactionResult, TransactionStatus


@dataclass
class AppliedStep:
    """A step that may require compensation."""

    step: Step
    adapter: Adapter
    snapshot: Snapshot


class TransactionEngine:
    """Execute typed steps and compensate completed mutations in reverse order."""

    def __init__(self, registry: AdapterRegistry, journal_root: Path) -> None:
        self.registry = registry
        self.journal_root = journal_root

    def _preflight(self, transaction: Transaction) -> list[Adapter]:
        adapters: list[Adapter] = []
        seen_ids = set()
        for step in transaction.steps:
            if step.id in seen_ids:
                raise ValueError(f"duplicate step id: {step.id}")
            seen_ids.add(step.id)
            adapter = self.registry.get(step.operation)
            adapter.validate(step.config)
            adapters.append(adapter)
        return adapters

    def _compensate(self, applied: list[AppliedStep], journal: Journal) -> list[str]:
        rollback_errors: list[str] = []
        for completed in reversed(applied):
            journal.append("compensation_started", step_id=completed.step.id)
            try:
                completed.adapter.compensate(completed.step.config, completed.snapshot)
                completed.adapter.verify_compensation(
                    completed.step.config, completed.snapshot
                )
                journal.append("compensation_verified", step_id=completed.step.id)
            except Exception as rollback_error:
                message = f"{completed.step.id}: {rollback_error}"
                rollback_errors.append(message)
                journal.append(
                    "compensation_failed",
                    step_id=completed.step.id,
                    error=str(rollback_error),
                )
        return rollback_errors

    def _execute(self, transaction: Transaction, *, commit: bool) -> TransactionResult:
        adapters = self._preflight(transaction)
        journal = Journal(self.journal_root, transaction.id)
        applied: list[AppliedStep] = []
        current_step: Optional[Step] = None
        journal.append(
            "transaction_started",
            transaction_id=transaction.id,
            execution_mode="apply" if commit else "test",
        )

        try:
            for step, adapter in zip(transaction.steps, adapters):
                current_step = step
                journal.append("step_started", step_id=step.id, operation=step.operation)
                snapshot = adapter.snapshot(step.config)
                journal.append("step_snapshotted", step_id=step.id, snapshot=snapshot)
                applied.append(AppliedStep(step, adapter, snapshot))
                journal.append("step_apply_started", step_id=step.id)
                adapter.apply(step.config)
                journal.append("step_applied", step_id=step.id)
                adapter.verify(step.config)
                journal.append("step_verified", step_id=step.id)
        except Exception as error:  # adapter boundaries normalize failures into a result
            journal.append(
                "transaction_failed",
                step_id=current_step.id if current_step else None,
                error=str(error),
            )
            rollback_errors = self._compensate(applied, journal)
            status = (
                TransactionStatus.ROLLBACK_FAILED
                if rollback_errors
                else TransactionStatus.ROLLED_BACK
            )
            journal.append("transaction_finished", status=status.value)
            return TransactionResult(
                status=status,
                transaction_id=transaction.id,
                failed_step=current_step.id if current_step else None,
                error=str(error),
                rollback_errors=rollback_errors,
                journal_path=str(journal.path),
            )

        if commit:
            journal.append("transaction_finished", status=TransactionStatus.COMMITTED.value)
            return TransactionResult(
                status=TransactionStatus.COMMITTED,
                transaction_id=transaction.id,
                journal_path=str(journal.path),
            )

        journal.append("test_succeeded", transaction_id=transaction.id)
        rollback_errors = self._compensate(applied, journal)
        status = (
            TransactionStatus.ROLLBACK_FAILED
            if rollback_errors
            else TransactionStatus.VALIDATED
        )
        journal.append("transaction_finished", status=status.value)
        return TransactionResult(
            status=status,
            transaction_id=transaction.id,
            rollback_errors=rollback_errors,
            journal_path=str(journal.path),
        )

    def run(self, transaction: Transaction) -> TransactionResult:
        """Apply a transaction and commit when every verification succeeds."""

        return self._execute(transaction, commit=True)

    def test(self, transaction: Transaction) -> TransactionResult:
        """Apply, verify, and always compensate a transaction before returning."""

        return self._execute(transaction, commit=False)
