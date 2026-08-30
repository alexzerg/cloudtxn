#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/sandbox-env.sh"

response=$(curl -fsS -X POST "$CLOUDTXN_KONG_URL/api/demo/reset")
printf '%s\n' "$response" | jq .

jq -e '
  .status == "DEGRADED_READY" and
  .payment_api_replicas == 1 and
  .payment_reconciler_replicas == 1 and
  .provider == "primary" and
  .payment_fallback == false and
  .checkout_http == 503 and
  .evidence.blocker.application_name == "payment-reconciler" and
  .evidence.database_lock.mode == "AccessExclusiveLock" and
  .evidence.database_lock.granted == true
' <<<"$response" >/dev/null

printf 'DEMO_RESET_READY\n'
