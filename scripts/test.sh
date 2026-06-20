#!/usr/bin/env bash
# test.sh — run the determinism-layer test harness (registry §3). Local + os-ci.
# Tests live in scripts/test/*.bats and exercise the OS scripts (not the product).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v bats >/dev/null 2>&1 || { echo "bats not found — install: sudo apt-get install -y bats (or: npm i -g bats)" >&2; exit 127; }
exec bats "$DIR/test"/*.bats
