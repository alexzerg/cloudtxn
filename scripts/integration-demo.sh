#!/usr/bin/env bash
set -euo pipefail

echo "Blocked: this legacy script used the default kubeconfig. Use scripts/sandbox-integration.sh." >&2
exit 2

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
CLUSTER=cloudtxn-demo
CONTEXT=k3d-${CLUSTER}

stop_local_runtime() {
  docker compose stop localstack >/dev/null 2>&1 || true
  k3d cluster stop "$CLUSTER" >/dev/null 2>&1 || true
}
trap stop_local_runtime EXIT

docker compose up -d localstack

for attempt in $(seq 1 60); do
  if aws --endpoint-url http://localhost:4566 ssm describe-parameters >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "LocalStack did not become ready" >&2
    exit 1
  fi
  sleep 1
done

if k3d cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -Fxq "$CLUSTER"; then
  k3d cluster start "$CLUSTER" >/dev/null
else
  k3d cluster create "$CLUSTER" --agents 1 --wait >/dev/null
fi

kubectl --context "$CONTEXT" apply -f demo/deployment.yaml >/dev/null
kubectl --context "$CONTEXT" rollout status deployment/cloudtxn-demo --timeout=120s >/dev/null
kubectl --context "$CONTEXT" scale deployment cloudtxn-demo --replicas=1 >/dev/null
kubectl --context "$CONTEXT" rollout status deployment/cloudtxn-demo --timeout=120s >/dev/null

aws --endpoint-url http://localhost:4566 ssm put-parameter \
  --name /cloudtxn/demo --type String --value before --overwrite >/dev/null

set +e
OUTPUT=$(.venv/bin/cloudtxn run examples/failing-transaction.yaml 2>&1)
STATUS=$?
set -e
printf '%s\n' "$OUTPUT"

if [ "$STATUS" -ne 10 ]; then
  echo "Expected CloudTxn rollback exit 10, got $STATUS" >&2
  exit 1
fi

REPLICAS=$(kubectl --context "$CONTEXT" get deployment cloudtxn-demo \
  --output jsonpath='{.spec.replicas}')
PARAMETER=$(aws --endpoint-url http://localhost:4566 ssm get-parameter \
  --name /cloudtxn/demo --query 'Parameter.Value' --output text)

if [ "$REPLICAS" != "1" ]; then
  echo "Expected 1 replica after compensation, got $REPLICAS" >&2
  exit 1
fi
if [ "$PARAMETER" != "before" ]; then
  echo "Expected SSM value before after compensation, got $PARAMETER" >&2
  exit 1
fi
if ! printf '%s\n' "$OUTPUT" | grep -Fq '"status": "ROLLED_BACK"'; then
  echo "Missing ROLLED_BACK result" >&2
  exit 1
fi

printf 'KUBERNETES_REPLICAS=%s\n' "$REPLICAS"
printf 'SSM_PARAMETER=%s\n' "$PARAMETER"
echo 'CLOUDTXN_INTEGRATION_PASS'
