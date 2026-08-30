#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

if [ "$CLOUDTXN_SANDBOX_CLUSTER" != "cloudtxn-sandbox-demo" ]; then
  echo "Refusing unexpected cluster name: $CLOUDTXN_SANDBOX_CLUSTER" >&2
  exit 2
fi
if [ "$COMPOSE_PROJECT_NAME" != "cloudtxn-sandbox" ]; then
  echo "Refusing unexpected Compose project: $COMPOSE_PROJECT_NAME" >&2
  exit 2
fi
if [ "$CLOUDTXN_SANDBOX_ROOT" != "$ROOT/.sandbox" ]; then
  echo "Refusing unexpected sandbox root: $CLOUDTXN_SANDBOX_ROOT" >&2
  exit 2
fi

printf 'This deletes only CloudTxn sandbox resources:\n'
printf '  k3d cluster: %s\n' "$CLOUDTXN_SANDBOX_CLUSTER"
printf '  Docker Compose project: %s\n' "$COMPOSE_PROJECT_NAME"
printf '  Directory: %s\n' "$CLOUDTXN_SANDBOX_ROOT"
answer=${CONFIRM:-}
if [ -z "$answer" ]; then
  read -r -p 'Type DELETE-CLOUDTXN-SANDBOX to continue: ' answer
fi
if [ "$answer" != "DELETE-CLOUDTXN-SANDBOX" ]; then
  echo "Cancelled"
  exit 1
fi

docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml down --volumes --remove-orphans
KUBECONFIG="$KUBECONFIG" k3d cluster delete "$CLOUDTXN_SANDBOX_CLUSTER"
if [ -d "$CLOUDTXN_SANDBOX_ROOT" ]; then
  find "$CLOUDTXN_SANDBOX_ROOT" -depth -delete
fi

CLUSTERS=$(k3d cluster list --no-headers 2>/dev/null | awk '{print $1}')
if grep -Fxq "$CLOUDTXN_SANDBOX_CLUSTER" <<< "$CLUSTERS"; then
  echo "Sandbox cluster still exists" >&2
  exit 1
fi
CONTAINERS=$(docker ps -a --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" -q)
if [ -n "$CONTAINERS" ]; then
  echo "Sandbox containers still exist" >&2
  exit 1
fi
if [ -e "$CLOUDTXN_SANDBOX_ROOT" ]; then
  echo "Sandbox directory still exists" >&2
  exit 1
fi
echo "CLOUDTXN_SANDBOX_DESTROYED"
