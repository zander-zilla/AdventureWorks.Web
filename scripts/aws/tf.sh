#!/usr/bin/env bash
# TF_STATE_BUCKET (env) overrides the bucket in infra/envs/<env>.s3.tfbackend.
# Wrapper: terraform for one environment. Usage: scripts/aws/tf.sh <env> <init|plan|apply|destroy|output ...> [args]
set -euo pipefail
ENV="${1:?env}"; shift; CMD="${1:?command}"; shift
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; TF=(terraform -chdir="$ROOT/infra/live")
case "$CMD" in
  init) B=(); if [ -n "${TF_STATE_BUCKET:-}" ]; then B=(-backend-config="bucket=$TF_STATE_BUCKET"); fi
        "${TF[@]}" init -reconfigure -input=false -backend-config="../envs/$ENV.s3.tfbackend" "${B[@]}" "$@" ;;
  plan|apply|destroy|refresh) "${TF[@]}" "$CMD" -input=false -var-file="../envs/$ENV.tfvars" "$@" ;;
  *) "${TF[@]}" "$CMD" "$@" ;;
esac
