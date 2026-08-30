# CloudTxn Bootstrap Plan

1. Create Python package metadata and CLI entry point.
   - Done when `python -m pip install -e '.[dev]'` exits 0.
2. Define versioned YAML schemas, statuses, adapter protocol, and typed errors.
   - Done when malformed or unknown operations are rejected before adapter mutation.
3. Implement append-only journal and transaction engine.
   - Done when unit tests prove commit, reverse compensation, rollback failure, and preflight rejection.
4. Implement Kubernetes scale adapter.
   - Done when adapter snapshots, applies, verifies, compensates, and re-verifies replica count.
5. Implement LocalStack-compatible AWS SSM adapter.
   - Done when adapter restores the original non-secret String parameter value.
6. Implement CLI and deterministic failure adapter.
   - Done when an intentionally failed transaction reports ROLLED_BACK and a journal path.
7. Add local integration environment and demo transaction.
   - Done when `scripts/integration-demo.sh` exits 0 and prints `CLOUDTXN_INTEGRATION_PASS`.
8. Add CI, documentation, and package checks.
   - Done when lint, unit tests, and package build all exit 0.
9. Create public GitHub repository, commit, and push.
   - Done when `gh repo view alexzerg/cloudtxn` succeeds and remote main points to the local commit.
