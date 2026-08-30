"""Versioned transaction models."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class TransactionStatus(str, Enum):
    """Terminal transaction states."""

    COMMITTED = "COMMITTED"
    VALIDATED = "VALIDATED"
    ROLLED_BACK = "ROLLED_BACK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class Step(BaseModel):
    """One typed operation in a transaction."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    operation: str = Field(min_length=1)
    config: dict[str, Any]


class Transaction(BaseModel):
    """CloudTxn YAML schema version 1."""

    model_config = ConfigDict(extra="forbid")

    api_version: str = Field(alias="apiVersion", pattern=r"^cloudtxn.io/v1$")
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    steps: list[Step] = Field(min_length=1)


class TransactionResult(BaseModel):
    """Machine-readable execution result."""

    status: TransactionStatus
    transaction_id: str
    failed_step: Optional[str] = None
    error: Optional[str] = None
    rollback_errors: list[str] = Field(default_factory=list)
    journal_path: str
