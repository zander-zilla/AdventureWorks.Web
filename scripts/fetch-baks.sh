#!/usr/bin/env bash
# Downloads the official AdventureWorks 2022 backups (microsoft/sql-server-samples releases).
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/docker/before/baks"
mkdir -p "$DIR"
BASE=https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks
for f in AdventureWorks2022.bak AdventureWorksDW2022.bak AdventureWorksLT2022.bak; do
  [ -s "$DIR/$f" ] || curl -fsSL -o "$DIR/$f" "$BASE/$f"
done
ls -la "$DIR"
