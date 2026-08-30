"""Schema boundary tests."""

import pytest
from pydantic import ValidationError

from cloudtxn.adapters.ssm import SsmPutConfig
from cloudtxn.models import Transaction


def test_rejects_unknown_transaction_fields() -> None:
    with pytest.raises(ValidationError):
        Transaction.model_validate(
            {
                "apiVersion": "cloudtxn.io/v1",
                "id": "demo",
                "steps": [{"id": "x", "operation": "test.fail", "config": {}}],
                "unsafe": True,
            }
        )


def test_ssm_bootstrap_schema_rejects_secure_string() -> None:
    with pytest.raises(ValidationError):
        SsmPutConfig.model_validate(
            {
                "name": "/demo",
                "value": "secret",
                "parameter_type": "SecureString",
            }
        )
