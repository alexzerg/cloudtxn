# CloudTxn Bootstrap Verification Plan

- Confirm no GCP dependency and no real AWS account mutation.
- Confirm all external commands use argument arrays without a shell.
- Confirm unknown adapters fail before the first mutation.
- Confirm rollback order is the reverse of completed apply order.
- Confirm ROLLBACK_FAILED is distinct from ROLLED_BACK.
- Confirm journal permissions are owner-only.
- Confirm SSM SecureString is rejected by the bootstrap adapter.
- Confirm integration final Kubernetes and SSM state equals captured initial state.
- Confirm README does not promise universal or guaranteed rollback.
