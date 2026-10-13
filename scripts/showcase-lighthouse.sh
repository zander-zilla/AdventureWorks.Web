#!/usr/bin/env bash
# C2-1: Lighthouse before/after for the showcase (before = frozen Chapter 1 at /c1/, after = Chapter 2 at /).
# Usage: scripts/showcase-lighthouse.sh [base-url] [out-dir]   (default: serves showcase/dist on :4190). No AWS.
set -euo pipefail
cd "$(dirname "$0")/.."
BASE="${1:-}"; OUT="${2:-lighthouse}"; mkdir -p "$OUT"
if [ -z "$BASE" ]; then
  python3 showcase/serve.py --port 4190 >/dev/null 2>&1 & SRV=$!; trap 'kill $SRV' EXIT; BASE=http://localhost:4190/; sleep 1
fi
CHROME_PATH="${CHROME_PATH:-$(node -e "console.log(require('$PWD/src/web/node_modules/playwright-core').chromium.executablePath())")}"
export CHROME_PATH
for v in before:c1/ after:; do
  name=${v%%:*}; path=${v#*:}
  npx --yes lighthouse@12 "$BASE$path" --quiet --output=json --output=html --output-path="$OUT/$name" \
    --chrome-flags="--headless=new --no-sandbox" --preset=desktop --only-categories=performance,accessibility,best-practices,seo
done
python3 - "$OUT" <<'PY'
import json, sys
out = sys.argv[1]; rows = {}
for n in ("before", "after"):
    r = json.load(open(f"{out}/{n}.report.json"))
    rows[n] = {k: round(c["score"] * 100) for k, c in r["categories"].items()}
json.dump(rows, open(f"{out}/scores.json", "w"), indent=1)
print("| Category | Before (Chapter 1, /c1/) | After (Chapter 2, /) |\n|---|---|---|")
for k in rows["before"]:
    print(f"| {k} | {rows['before'][k]} | {rows['after'][k]} |")
PY
