# CloudTxn Hackathon Story

## Elevator Pitch

CloudTxn turns a natural-language incident runbook into an approved, typed transaction across cloud control planes. Every allowlisted operation captures pre-state, verifies the mutation, and carries a deterministic compensation. If a later step fails, CloudTxn restores prior state in reverse order and produces an evidence journal.

## API + Cloud + AI

- **AI:** local Ollama/Qwen compiles human intent into a constrained JSON-schema plan. It cannot select credentials, endpoints, contexts, shell commands, or rollback logic.
- **API:** Kong fronts the Business Web App; Bruno verifies the API; adapters call Kubernetes and AWS-compatible SSM APIs.
- **Cloud:** the demo mutates independent Kubernetes and AWS-compatible control planes and proves cross-system compensation.

## Safety Boundary

The demo is intentionally local. It uses an isolated k3d cluster, LocalStack, Kong, Ollama, repo-local credentials, and a repo-local kubeconfig. Runtime guards reject non-sandbox Kubernetes contexts and non-sandbox SSM endpoints.

## Demo Arc

1. Show one replica in OpenLens and SSM value `before`.
2. Enter a natural-language mitigation runbook in the Web App.
3. Show AI-compiled typed operations and deterministic compensation preview.
4. Approve execution.
5. Watch Kubernetes scale to three and SSM change to `after`.
6. Trigger an intentional third-step failure.
7. Show reverse compensation, OpenLens returning to one replica, SSM returning to `before`, and the evidence journal reporting zero rollback errors.

## Submission Positioning

CloudTxn is a Business Web App built from scratch. The public repository contains one-command local reproduction, tests, screenshots, and an API collection. Kong and Bruno are used as functional components rather than decorative sponsor integrations.
