# CloudTxn Bootstrap Research

## Existing Approaches

- Terraform and CloudFormation can reconcile declarative resources they own, but do not provide a transaction for arbitrary cross-control-plane incident operations.
- Kubernetes rollout undo is limited to supported workload rollout history and is not a general inverse for kubectl operations.
- Temporal and saga orchestration support compensating transactions, but compensations are application code written manually for each workflow.
- Rundeck and StackStorm workflows can execute rollback handlers, but the runbook author must implement and verify those handlers.
- Cloud audit logs preserve history but do not capture minimal pre-state and execute a verified inverse operation.

## Design Boundary

CloudTxn does not claim universal rollback. An operation is transactional only when a curated adapter can:

1. capture the exact relevant pre-state;
2. apply a typed mutation;
3. verify its postcondition;
4. apply a typed compensation;
5. verify restoration.

Unknown and irreversible operations are rejected before the first mutation.

## First Vertical Slice

- Kubernetes Deployment replica count through kubectl and a local k3d cluster.
- AWS SSM String parameter value through AWS CLI and LocalStack.
- Intentional failure adapter to trigger reverse compensation.
- Local append-only journal with restrictive permissions.
