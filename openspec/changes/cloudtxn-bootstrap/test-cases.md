# CloudTxn Bootstrap Test Cases

## Scenario: Successful transaction

Given a transaction with reversible steps
When every apply and verification succeeds
Then the transaction status is COMMITTED
And compensation is not executed

## Scenario: Failed transaction compensates in reverse order

Given Kubernetes replicas are 1
And LocalStack SSM parameter /cloudtxn/demo equals before
And a transaction scales replicas to 3, changes the parameter to after, then fails
When CloudTxn executes the transaction
Then the SSM parameter is restored to before
And Kubernetes replicas are restored to 1
And the transaction status is ROLLED_BACK
And the journal records compensation in reverse step order

## Scenario: Compensation failure is explicit

Given an adapter cannot verify its compensation
When rollback runs
Then the transaction status is ROLLBACK_FAILED
And the CLI exits non-zero

## Scenario: Unsupported operation is rejected

Given a transaction contains an unregistered adapter type
When CloudTxn validates the plan
Then no mutation occurs
And the CLI exits non-zero
