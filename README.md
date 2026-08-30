# CloudTxn

CloudTxn is a GitOps safety gate for incident-response pull requests. It reads a constrained change from a real GitHub PR, converts it into a typed transaction, applies it to an isolated environment, verifies the customer-facing outcome, and either records it as safe or compensates every mutation in reverse order.

The local AI is evidence-grounded: Ollama receives PostgreSQL diagnostics and may propose only allowlisted changes. It cannot choose credentials, endpoints, Kubernetes contexts, arbitrary shell commands, or rollback logic.

## Demo story

A PostgreSQL `AccessExclusiveLock` held by `payment-reconciler` degrades checkout.

1. An engineer opens a plausible PR that scales `payment-api`, switches the payment provider, and enables fallback.
2. CloudTxn inspects the PR's `gitops/payment-incident.yaml` and compiles a typed multi-system transaction.
3. The PR is deployed as a reversible test. Checkout remains HTTP 503, so Kubernetes, SSM, and feature-flag snapshots are restored automatically.
4. Ollama analyzes real PostgreSQL activity and identifies `payment-reconciler` as the lock owner.
5. An AI remediation PR pauses that reconciler.
6. CloudTxn tests the AI PR, observes checkout HTTP 200, restores the test snapshot, and enables **Safe to merge**.
7. Promotion applies the same typed transaction and commits only after the business-health gate passes.

## Local architecture

- GitHub PRs provide the GitOps change proposals.
- Ollama with Qwen2.5-Coder performs local diagnosis.
- Kong is the only published application/API endpoint.
- k3d provides the isolated Kubernetes environment.
- PostgreSQL provides a real lock-backed incident.
- LocalStack provides an AWS-compatible SSM API.
- A local feature-flag API represents another independent control plane.
- OpenLens visualizes Kubernetes scaling and compensation.

No paid cloud account, production credentials, or external AI API is required.

## Quick start

Prerequisites: Docker, k3d, kubectl, AWS CLI, Python 3.9+, Node.js, and jq.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
make demo-preload
make demo-up
```

Open <http://127.0.0.1:18000/>. For OpenLens, import `.sandbox/kubeconfig` explicitly; do not use the default kubeconfig for this demo.

## Transaction contract

Every adapter implements:

```text
validate → snapshot → apply → verify → commit
                              └ failure → compensate in reverse → verify restoration
```

A safe PR test uses the same operations but always restores captured snapshots after verification. A successful test therefore produces `VALIDATED`; promotion reruns the typed transaction and may produce `COMMITTED`.

| Operation | Snapshot and compensation |
|---|---|
| `kubernetes.scale_deployment` | Capture and restore Deployment replicas |
| `aws.ssm_put_parameter` | Capture and restore a non-secret SSM String value |
| `feature_flag.set` | Capture and restore the previous flag state |
| `http.assert_payment_health` | Poll the real checkout endpoint through Kong |

Unknown operations, repositories, resources, contexts, and irreversible actions are rejected before execution.

## Lifecycle

```bash
make demo-status
make demo-check
make demo-stop
make demo-down CONFIRM=DELETE-CLOUDTXN-SANDBOX
```

Destruction is restricted to the `cloudtxn-sandbox-demo` k3d cluster, the `cloudtxn-sandbox` Compose project, and the repository-local `.sandbox/` directory.

## Roadmap

GitHub Actions status checks, PR comments, journal artifacts, merge-queue protection, and Argo CD/Flux preview-environment adapters are tracked in [`todo.md`](todo.md).
