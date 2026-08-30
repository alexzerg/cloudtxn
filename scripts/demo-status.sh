#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

printf '%s\n' '--- CloudTxn sandbox ---'
k3d cluster list | grep -E "NAME|$CLOUDTXN_SANDBOX_CLUSTER" || true
docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml ps
printf 'Web UI: %s\n' "$CLOUDTXN_KONG_URL"
printf 'OpenLens kubeconfig: %s\n' "$KUBECONFIG"
printf 'OpenLens context: %s\n' "$CLOUDTXN_ALLOWED_KUBE_CONTEXT"
