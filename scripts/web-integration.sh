#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

scripts/sandbox-up.sh >/dev/null
for attempt in $(seq 1 30); do
  curl -fsS "$CLOUDTXN_KONG_URL/api/health" >/dev/null 2>&1 && break
  [ "$attempt" -lt 30 ] || { echo "Kong health timeout" >&2; exit 1; }
  sleep 1
done

kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  scale deployment cloudtxn-demo --replicas=1 >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  rollout status deployment/cloudtxn-demo --timeout=120s >/dev/null
aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" ssm put-parameter \
  --name /cloudtxn/demo --type String --value before --overwrite >/dev/null

curl -fsS --max-time 180 \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Scale the cloudtxn-demo deployment to 3 replicas, set /cloudtxn/demo to after, then simulate a failure so the transaction rolls back."}' \
  "$CLOUDTXN_KONG_URL/api/compile" > "$CLOUDTXN_SANDBOX_ROOT/compiled-plan-proof.json"
jq '{transaction:.transaction}' "$CLOUDTXN_SANDBOX_ROOT/compiled-plan-proof.json" \
  > "$CLOUDTXN_SANDBOX_ROOT/run-request-proof.json"
curl -fsS --max-time 180 \
  -H 'Content-Type: application/json' \
  --data-binary "@$CLOUDTXN_SANDBOX_ROOT/run-request-proof.json" \
  "$CLOUDTXN_KONG_URL/api/run" > "$CLOUDTXN_SANDBOX_ROOT/run-response-proof.json"

RUN_ID=$(jq -r '.transaction.id' "$CLOUDTXN_SANDBOX_ROOT/compiled-plan-proof.json")
FAILED_STEP=$(jq -r '.result.failed_step' "$CLOUDTXN_SANDBOX_ROOT/run-response-proof.json")
APPLIED=$(jq '[.events[] | select(.event == "step_applied")] | length' "$CLOUDTXN_SANDBOX_ROOT/run-response-proof.json")
VERIFIED=$(jq '[.events[] | select(.event == "step_verified")] | length' "$CLOUDTXN_SANDBOX_ROOT/run-response-proof.json")
COMPENSATED=$(jq '[.events[] | select(.event == "compensation_verified")] | length' "$CLOUDTXN_SANDBOX_ROOT/run-response-proof.json")
REPLICAS=$(kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  get deployment cloudtxn-demo --output jsonpath='{.spec.replicas}')
PARAMETER=$(aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" ssm get-parameter \
  --name /cloudtxn/demo --query 'Parameter.Value' --output text)

printf 'RUN_ID=%s\n' "$RUN_ID"
printf 'FAILED_STEP=%s\n' "$FAILED_STEP"
printf 'APPLIED_EVENTS=%s\n' "$APPLIED"
printf 'VERIFIED_EVENTS=%s\n' "$VERIFIED"
printf 'COMPENSATION_VERIFIED_EVENTS=%s\n' "$COMPENSATED"
printf 'KUBERNETES_REPLICAS=%s\n' "$REPLICAS"
printf 'SSM_PARAMETER=%s\n' "$PARAMETER"

printf '%s' "$RUN_ID" | grep -Eq '^demo-[0-9a-f]{12}$'
[ "$FAILED_STEP" = "step-3-test-fail" ]
[ "$APPLIED" = "3" ]
[ "$VERIFIED" = "2" ]
[ "$COMPENSATED" = "3" ]
jq -e '.result.status == "ROLLED_BACK" and (.result.rollback_errors | length == 0)' \
  "$CLOUDTXN_SANDBOX_ROOT/run-response-proof.json" >/dev/null
[ "$REPLICAS" = "1" ]
[ "$PARAMETER" = "before" ]
echo "CLOUDTXN_WEB_ROLLBACK_PASS"
