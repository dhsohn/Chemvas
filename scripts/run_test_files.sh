#!/usr/bin/env bash
# Run each given test file in its own pytest process, several at a time.
#
# Qt keeps global application state that does not fully reset between test
# modules, so one process per file is a contract rather than a convenience —
# a single shared process passes tests that CI would fail. Concurrency is
# between those processes; it never merges two files into one.
#
# Usage: run_test_files.sh [--python PATH] FILE [FILE...]
# Environment: CHECK_JOBS overrides the concurrency.
set -euo pipefail

PYTHON="${PYTHON_BIN:-python3}"
if [[ "${1:-}" == "--python" ]]; then
  PYTHON="$2"
  shift 2
fi

if [[ $# -eq 0 ]]; then
  echo "[tests] ERROR: no test files given." >&2
  exit 2
fi

# The heaviest module peaks near 1.2 GB, so the cap stops a wide machine from
# starting hundreds of them for no gain. The slowest single file is the floor
# regardless of how many run beside it.
jobs="${CHECK_JOBS:-$(nproc 2>/dev/null || echo 4)}"
if [[ ! "$jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo "[tests] ERROR: CHECK_JOBS must be a positive integer." >&2
  exit 2
fi
if [[ ${#jobs} -gt 1 || "$jobs" == "9" ]]; then
  jobs=8
fi

logs="$(mktemp -d)"
trap 'rm -rf "$logs"' EXIT

export PYTHON logs
export QT_QPA_PLATFORM=offscreen

echo "[tests] $# files, $jobs at a time"

status=0
index=0
for file in "$@"; do
  printf '%s\0%s\0' "$index" "$file"
  ((index += 1))
done |
  xargs -0 -P "$jobs" -n2 bash -c '
    index="$1"
    file="$2"
    log="$logs/$index.log"
    if "$PYTHON" -m pytest -q "$file" >"$log" 2>&1; then
      printf "[tests] %s: %s\n" "$file" "$(tail -1 "$log")"
      rm -f "$log"
    else
      printf "[tests] FAILED %s\n" "$file" >&2
      exit 1
    fi
  ' _ || status=$?

if [[ "$status" -ne 0 ]]; then
  # Every process runs, so a broken tree reports all of its failures at once
  # rather than only the first one the old sequential loop reached.
  for log in "$logs"/*.log; do
    [[ -e "$log" ]] || continue
    echo "[tests] ---------- $(basename "$log" .log)" >&2
    tail -30 "$log" >&2
  done
  exit 1
fi

echo "[tests] $# files passed"
