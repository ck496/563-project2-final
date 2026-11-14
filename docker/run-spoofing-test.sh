#!/usr/bin/env bash
# Spoofing test (S11 test 6): verify that bad or missing tokens get 401.
# Run while a game is in progress: bash docker/run-spoofing-test.sh

SERVER="${WW_SERVER_URL:-http://localhost:8000}"

echo "=== Spoofing test against $SERVER ==="

echo -n "Bad token  -> "
code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$SERVER/vote/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-token-abc" \
  -d '{"target": 1}')
echo "$code (expect 401)"

echo -n "No token   -> "
code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$SERVER/vote/" \
  -H "Content-Type: application/json" \
  -d '{"target": 1}')
echo "$code (expect 401)"

echo -n "Bad header -> "
code=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$SERVER/vote/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Token fake" \
  -d '{"target": 1}')
echo "$code (expect 401)"

echo "=== Done ==="
