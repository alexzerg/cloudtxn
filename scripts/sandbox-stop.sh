#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml stop
k3d cluster stop "$CLOUDTXN_SANDBOX_CLUSTER"
echo "CLOUDTXN_SANDBOX_STOPPED"
