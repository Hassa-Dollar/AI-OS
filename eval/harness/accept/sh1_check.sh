#!/usr/bin/env bash
# SH-1 hidden acceptance (black-box): boot on a FRESH database configured only through components/api/.env,
# then healthz + sign-up must succeed; package.json must not contain allowScripts.
# usage: sh1_check.sh <workspace> <node-bin-dir>
set -u
WS="$1"; NODE_BIN="$2"; API="$WS/components/api"; PORT=$((20000 + RANDOM % 20000))
TMP=$(mktemp -d); PID=""
cleanup() { [ -n "$PID" ] && kill "$PID" 2>/dev/null; rm -f "$API/.env"; rm -rf "$TMP"; }
trap cleanup EXIT
fail=0; ok() { echo "PASS $1"; }; bad() { echo "FAIL $1"; fail=1; }

if grep -q '"allowScripts"' "$API/package.json"; then bad "allowScripts still in package.json"; else ok "no allowScripts"; fi

cat > "$API/.env" <<EOF
PORT=$PORT
DATABASE_PATH=$TMP/fresh.db
BETTER_AUTH_SECRET=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')
BETTER_AUTH_URL=http://localhost:$PORT
EOF
(cd "$API" && exec env -i PATH="$NODE_BIN:/usr/bin:/bin" HOME="$TMP" ./node_modules/.bin/tsx src/server.ts >"$TMP/server.log" 2>&1) &
PID=$!
for _ in $(seq 1 60); do curl -fs "http://localhost:$PORT/healthz" >/dev/null 2>&1 && break; sleep 0.5; done

code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/healthz")
if [ "$code" = 200 ]; then ok "healthz 200 on PORT from .env"; else bad "healthz=$code (.env not loaded or server down)"; fi

code=$(curl -s -o "$TMP/signup.json" -w '%{http_code}' -X POST "http://localhost:$PORT/api/auth/sign-up/email" \
  -H 'content-type: application/json' -H 'origin: http://localhost:5173' \
  -d '{"name":"Acc","email":"acc@example.test","password":"correct-horse-battery-9"}')
if [ "$code" = 200 ]; then ok "sign-up 200 on fresh DB"; else bad "sign-up=$code"; head -c 300 "$TMP/signup.json"; echo; tail -n 5 "$TMP/server.log"; fi
exit $fail
