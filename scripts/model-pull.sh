#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"
docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml exec -T ollama \
  ollama pull "$CLOUDTXN_OLLAMA_MODEL"
echo "CLOUDTXN_MODEL_READY=$CLOUDTXN_OLLAMA_MODEL"
