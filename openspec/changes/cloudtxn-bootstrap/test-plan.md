# CloudTxn Bootstrap Test Plan

## Unit Gate

Command: `.venv/bin/pytest -q`
Expected: exit 0 and all tests pass.

## Static Gate

Command: `.venv/bin/ruff check .`
Expected: exit 0 and `All checks passed!`.

Command: `.venv/bin/mypy src`
Expected: exit 0 and `Success: no issues found`.

## Package Gate

Command: `.venv/bin/python -m build`
Expected: exit 0 and wheel plus source distribution are created.

## Integration Gate

Command: `scripts/integration-demo.sh`
Expected: exit 0 and output contains `CLOUDTXN_INTEGRATION_PASS`.

The integration script may create or start a local k3d cluster and LocalStack container. It must not contact a paid cloud account and must stop, not delete, the local runtime after verification.
