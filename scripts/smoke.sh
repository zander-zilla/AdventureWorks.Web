#!/usr/bin/env bash
# Smoke test for the BEFORE app: pages render, demo login works, an order is written to SQL Server.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:5080}"
JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT
token() { sed -n 's/.*name="__RequestVerificationToken" type="hidden" value="\([^"]*\)".*/\1/p' | sed -n 1p; }
for p in / /Products /Customers /ProductCategories; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$p"); echo "GET $p -> $code"; [ "$code" = 200 ]
done
T=$(curl -s -c "$JAR" -b "$JAR" "$BASE/Account/Login" | token)
curl -s -o /dev/null -c "$JAR" -b "$JAR" -X POST "$BASE/Account/Login" \
  --data-urlencode "email=catherine0@adventure-works.com" --data-urlencode 'password=Demo!2026' --data-urlencode "__RequestVerificationToken=$T"
SHOP=$(curl -s -c "$JAR" -b "$JAR" "$BASE/Shop")
grep -q "signed in as Catherine Abel" <<<"$SHOP" || { echo "login failed"; exit 1; }
T=$(token <<<"$SHOP")
BEFORE=$(curl -s -b "$JAR" "$BASE/Shop/MyOrders" | grep -c "<td>SO" || true)
PID=$(sed -n 's/.*name="productId" value="\([0-9]*\)".*/\1/p' <<<"$SHOP" | sed -n 1p)
curl -s -L -c "$JAR" -b "$JAR" "$BASE/Shop/Order" -d "productId=$PID&quantity=2" \
  --data-urlencode "__RequestVerificationToken=$T" > /tmp/aw-order.html
grep -o 'Order [0-9]* placed[^<]*' /tmp/aw-order.html || true
AFTER=$(grep -c "<td>SO" /tmp/aw-order.html || true)
echo "orders for demo customer: $BEFORE -> $AFTER"; [ "$AFTER" -gt "$BEFORE" ] || { echo "order failed"; exit 1; }
echo "SMOKE OK"
