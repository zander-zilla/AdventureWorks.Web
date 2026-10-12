#!/usr/bin/env bash
# Package the CDC Lambda (phase 7 Terraform consumes dist/aw-cdc-lambda.zip). Python 3.12, x86_64.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; OUT="$ROOT/dist/aw-cdc-lambda"; rm -rf "$OUT"; mkdir -p "$OUT"
cp "$ROOT/cdc/lambda/handler.py" "$OUT/"
cp -r "$ROOT/cdc/awcdc" "$OUT/awcdc"
cp "$ROOT/scripts/loader/awmap.py" "$ROOT/scripts/loader/sqlsrc.py" "$OUT/"
cp "$ROOT/design/mapping/mapping.json" "$ROOT/design/mapping/cdc-refresh.yaml" "$ROOT/design/mapping/cdc-enrichment.yaml" "$OUT/awcdc/"
pip install -q --target "$OUT" --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 "pymssql==2.*" "pyyaml==6.*"
(cd "$OUT" && find . -name __pycache__ -prune -exec rm -rf {} + && zip -qr ../aw-cdc-lambda.zip .)
ls -la "$ROOT/dist/aw-cdc-lambda.zip"
