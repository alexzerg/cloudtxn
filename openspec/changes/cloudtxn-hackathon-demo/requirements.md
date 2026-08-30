# CloudTxn Hackathon Demo Requirements

## Product

CloudTxn must be presented as a Business Web App that compiles a natural-language incident runbook into a validated transaction, previews compensations, executes only allowlisted sandbox operations, and displays a live evidence timeline.

## Hackathon Fit

- API: Kubernetes API, LocalStack AWS SSM API, Kong proxy/Admin API, Ollama API.
- Cloud: one transaction spans independent Kubernetes and AWS-compatible control planes.
- AI: a local model converts natural-language intent into a constrained typed plan and explanation.
- Web App: browser workflow for prompt, preview, approval, execution, and rollback evidence.

## Isolation

1. Never read, mutate, or select the user's default kubeconfig.
2. Never read the user's AWS profiles or credentials.
3. Never contact GCP or a non-loopback AWS-compatible endpoint.
4. Store all demo configuration and mutable state under `.sandbox/`.
5. Bind every published demo port to `127.0.0.1`.
6. Create k3d with default-kubeconfig updates and context switching disabled.
7. Reject Kubernetes contexts and SSM endpoints that do not exactly match the sandbox allowlist.
8. Keep cleanup explicit and separately confirmed.
9. Print the isolated kubeconfig path for OpenLens import.

## Demo Success

A natural-language runbook is compiled by Ollama, validated, executed through the web app, intentionally fails, restores Kubernetes and SSM pre-state, and displays `ROLLED_BACK` with zero rollback errors.
