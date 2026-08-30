#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=sandbox-env.sh
source "$ROOT/scripts/sandbox-env.sh"
cd "$ROOT"
umask 077

mkdir -p \
  "$CLOUDTXN_SANDBOX_ROOT/aws" \
  "$CLOUDTXN_SANDBOX_ROOT/journals" \
  "$CLOUDTXN_SANDBOX_ROOT/ollama"
cat > "$AWS_CONFIG_FILE" <<'CONFIG'
[default]
region = us-east-1
output = json
CONFIG
cat > "$AWS_SHARED_CREDENTIALS_FILE" <<'CREDENTIALS'
[default]
aws_access_key_id = cloudtxn-demo
aws_secret_access_key = cloudtxn-demo
CREDENTIALS
: > "$KUBECONFIG"
chmod 600 "$KUBECONFIG" "$AWS_CONFIG_FILE" "$AWS_SHARED_CREDENTIALS_FILE"

if k3d cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -Fxq "$CLOUDTXN_SANDBOX_CLUSTER"; then
  k3d cluster start "$CLOUDTXN_SANDBOX_CLUSTER" >/dev/null
else
  KUBECONFIG="$KUBECONFIG" k3d cluster create "$CLOUDTXN_SANDBOX_CLUSTER" \
    --agents 1 \
    --api-port 127.0.0.1:16443 \
    --kubeconfig-update-default=false \
    --kubeconfig-switch-context=false \
    --wait >/dev/null
fi

KUBECONFIG="$KUBECONFIG" k3d kubeconfig get "$CLOUDTXN_SANDBOX_CLUSTER" > "$KUBECONFIG"
CONTAINER_KUBECONFIG="$CLOUDTXN_SANDBOX_ROOT/kubeconfig-container"
cp "$KUBECONFIG" "$CONTAINER_KUBECONFIG"
kubectl --kubeconfig "$CONTAINER_KUBECONFIG" config set-cluster \
  "k3d-$CLOUDTXN_SANDBOX_CLUSTER" \
  --server="https://k3d-$CLOUDTXN_SANDBOX_CLUSTER-server-0:6443" \
  --insecure-skip-tls-verify=true >/dev/null
chmod 600 "$KUBECONFIG" "$CONTAINER_KUBECONFIG"

docker compose -p "$COMPOSE_PROJECT_NAME" -f sandbox/compose.yaml up -d --build

for attempt in $(seq 1 30); do
  if curl -fsS "$CLOUDTXN_OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Sandbox Ollama did not become ready" >&2
    exit 1
  fi
  sleep 1
done
curl -fsS --max-time 90 -X POST "$CLOUDTXN_OLLAMA_URL/api/generate" \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg model "$CLOUDTXN_OLLAMA_MODEL" \
    '{model:$model,prompt:"Return OK",stream:false,keep_alive:"30m",options:{num_predict:2}}')" \
  >/dev/null

docker build -f sandbox/PaymentLab.Dockerfile -t cloudtxn-payment-lab:demo . >/dev/null
k3d image import cloudtxn-payment-lab:demo -c "$CLOUDTXN_SANDBOX_CLUSTER" >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  apply -f demo/payment-lab.yaml >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  rollout status deployment/postgres --timeout=45s >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  scale deployment/payment-reconciler --replicas=0 >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  rollout status deployment/payment-api --timeout=45s >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  scale deployment/payment-reconciler --replicas=1 >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  rollout status deployment/payment-reconciler --timeout=30s >/dev/null

kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  apply -f demo/deployment.yaml >/dev/null
kubectl --kubeconfig "$KUBECONFIG" --context "$CLOUDTXN_ALLOWED_KUBE_CONTEXT" \
  rollout status deployment/cloudtxn-demo --timeout=120s >/dev/null

for attempt in $(seq 1 60); do
  if aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" \
    ssm describe-parameters >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "Sandbox LocalStack did not become ready" >&2
    exit 1
  fi
  sleep 1
done

aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" ssm put-parameter \
  --name /cloudtxn/demo --type String --value before --overwrite >/dev/null
aws --endpoint-url "$CLOUDTXN_ALLOWED_SSM_ENDPOINT" ssm put-parameter \
  --name /payments/provider --type String --value primary --overwrite >/dev/null

for attempt in $(seq 1 60); do
  if curl -fsS "$CLOUDTXN_KONG_URL/api/health" >/dev/null 2>&1; then
    curl -fsS -X POST "$CLOUDTXN_KONG_URL/payments/reset" >/dev/null
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "Sandbox Kong did not become ready" >&2
    exit 1
  fi
  sleep 1
done

printf 'CLOUDTXN_SANDBOX_READY\n'
printf 'OpenLens kubeconfig: %s\n' "$KUBECONFIG"
printf 'Kubernetes context: %s\n' "$CLOUDTXN_ALLOWED_KUBE_CONTEXT"
printf 'Kong URL: %s\n' "$CLOUDTXN_KONG_URL"
printf 'Ollama URL: %s\n' "$CLOUDTXN_OLLAMA_URL"
