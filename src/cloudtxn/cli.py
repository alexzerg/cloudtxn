"""CloudTxn command-line interface."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError

from cloudtxn.adapters.base import AdapterRegistry
from cloudtxn.adapters.fail import FailAdapter
from cloudtxn.adapters.kubernetes import KubernetesScaleAdapter
from cloudtxn.adapters.ssm import SsmPutParameterAdapter
from cloudtxn.engine import TransactionEngine
from cloudtxn.errors import CloudTxnError
from cloudtxn.models import Transaction, TransactionStatus

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _load(path: Path) -> Transaction:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Transaction.model_validate(raw)


def _registry() -> AdapterRegistry:
    return AdapterRegistry(
        [KubernetesScaleAdapter(), SsmPutParameterAdapter(), FailAdapter()]
    )


@app.callback()
def main() -> None:
    """Run verified compensating transactions for curated cloud operations."""


@app.command()
def run(
    transaction_file: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True),
    ],
    journal_dir: Annotated[
        Path,
        typer.Option("--journal-dir"),
    ] = Path(".cloudtxn/runs"),
) -> None:
    """Execute a transaction and print a machine-readable result."""

    try:
        transaction = _load(transaction_file)
        result = TransactionEngine(_registry(), journal_dir).run(transaction)
    except (CloudTxnError, ValidationError, ValueError, OSError) as error:
        typer.echo(json.dumps({"status": "REJECTED", "error": str(error)}, indent=2))
        raise typer.Exit(code=2) from error

    typer.echo(result.model_dump_json(indent=2))
    if result.status == TransactionStatus.ROLLED_BACK:
        raise typer.Exit(code=10)
    if result.status == TransactionStatus.ROLLBACK_FAILED:
        raise typer.Exit(code=20)
