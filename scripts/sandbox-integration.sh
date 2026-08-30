#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"

scripts/sandbox-up.sh >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  scale deployment cloudtxn-demo --replicas=1 >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  rollout status deployment/cloudtxn-demo --timeout=120s >/dev/null
aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" ssm put-parameter \
  --name /cloudtxn/demo --type String --value before --overwrite >/dev/null

set +e
OUTPUT=$(.venv/bin/cloudtxn run examples/sandbox-failing-transaction.yaml \
  --journal-dir "$CLOUDTXN_SANDBOX_ROOT/journals" 2>&1)
STATUS=$?
set -e
printf '%s\n' "$OUTPUT"

[ "$STATUS" -eq 10 ] || { echo "Expected rollback exit 10, got $STATUS" >&2; exit 1; }
REPLICAS=$(kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  get deployment cloudtxn-demo --output jsonpath='{.spec.replicas}')
PARAMETER=$(aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" ssm get-parameter \
  --name /cloudtxn/demo --query 'Parameter.Value' --output text)
[ "$REPLICAS" = "1" ] || { echo "Replica compensation failed: $REPLICAS" >&2; exit 1; }
[ "$PARAMETER" = "before" ] || { echo "SSM compensation failed: $PARAMETER" >&2; exit 1; }
printf '%s\n' "$OUTPUT" | grep -Fq '"status": "ROLLED_BACK"'
printf 'KUBERNETES_REPLICAS=%s\n' "$REPLICAS"
printf 'SSM_PARAMETER=%s\n' "$PARAMETER"
echo 'CLOUDTXN_SANDBOX_INTEGRATION_PASS'
