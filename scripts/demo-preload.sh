#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

docker pull localstack/localstack:4.8.1
docker pull kong:3.9.1
docker pull ollama/ollama:0.11.4
docker pull rancher/k3s:v1.31.5-k3s1
docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml up -d ollama
scripts/model-pull.sh
docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml stop ollama
echo "CLOUDTXN_DEMO_PRELOAD_PASS"
