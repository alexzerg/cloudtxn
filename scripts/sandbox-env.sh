#!/usr/bin/env bash
# shellcheck shell=bash

CLOUDTXN_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export CLOUDTXN_ROOT
export CLOUDTXN_SANDBOX_ROOT="$CLOUDTXN_ROOT/.sandbox"
export KUBECONFIG="$CLOUDTXN_SANDBOX_ROOT/kubeconfig"
export AWS_CONFIG_FILE="$CLOUDTXN_SANDBOX_ROOT/aws/config"
export AWS_SHARED_CREDENTIALS_FILE="$CLOUDTXN_SANDBOX_ROOT/aws/credentials"
export AWS_ACCESS_KEY_ID=cloudtxn-demo
export AWS_SECRET_ACCESS_KEY=cloudtxn-demo
export AWS_DEFAULT_REGION=us-east-1
export AWS_EC2_METADATA_DISABLED=true
export CLOUDTXN_DEMO_MODE=1
export CLOUDTXN_DEMO_FAST=1
export CLOUDTXN_SANDBOX_CLUSTER=cloudtxn-sandbox-demo
export CLOUDTXN_ALLOWED_KUBE_CONTEXT=k3d-cloudtxn-sandbox-demo
export CLOUDTXN_ALLOWED_SSM_ENDPOINT=http://127.0.0.1:14566
export CLOUDTXN_OLLAMA_URL=http://127.0.0.1:11434
export CLOUDTXN_OLLAMA_MODEL=qwen2.5-coder:0.5b
export CLOUDTXN_KONG_URL=http://127.0.0.1:18000
export COMPOSE_PROJECT_NAME=cloudtxn-sandbox
