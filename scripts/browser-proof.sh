#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

npx --yes playwright@1.55.0 screenshot \
  --device='Desktop Chrome' \
  --full-page \
  "$CLOUDTXN_KONG_URL" \
  "$CLOUDTXN_SANDBOX_ROOT/cloudtxn-home.png"
file "$CLOUDTXN_SANDBOX_ROOT/cloudtxn-home.png"
echo "CLOUDTXN_BROWSER_PROOF_PASS"
