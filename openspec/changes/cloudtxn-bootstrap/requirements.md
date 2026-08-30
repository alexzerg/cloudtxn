# CloudTxn Bootstrap Requirements

## Goal

Prove that a typed cloud transaction can mutate two local control planes and restore both to their exact pre-transaction state when a later step fails.

## Functional Requirements

1. Accept a versioned YAML transaction containing ordered typed steps.
2. Require every executable adapter to implement snapshot, apply, verify, compensate, and verify-compensation operations.
3. Persist an append-only local journal for every state transition.
4. Compensate successful steps in reverse order after any apply or verification failure.
5. Refuse unsupported or explicitly irreversible operation types.
6. Support Kubernetes Deployment replica changes through kubectl.
7. Support AWS SSM parameter value changes through an endpoint configurable for LocalStack.
8. Provide an intentional failure adapter for deterministic integration testing.
9. Never require Google Cloud, paid cloud resources, or real AWS credentials for the demo.

## Non-Goals

- Universal rollback for arbitrary shell commands.
- Compensation for destructive data operations.
- Production-ready distributed locking.
- Kong integration in the first vertical slice.
- Automatic AI-generated compensations.

## Success Condition

A local integration command must exit 0 and show that Kubernetes replicas and the SSM parameter value after compensation equal their recorded pre-transaction values.
