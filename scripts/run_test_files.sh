#!/usr/bin/env bash
# Run each given test file in its own pytest process, several at a time.
#
# Qt keeps global application state that does not fully reset between test
# modules, so one process per file is a contract rather than a convenience —
# a single shared process passes tests that CI would fail. Concurrency is
# between those processes; it never merges two files into one.
#
# Usage: run_test_files.sh [--python PATH] [--coverage-dir DIR] FILE [FILE...]
# Environment: CHECK_JOBS overrides the concurrency.
set -euo pipefail

PYTHON="${PYTHON_BIN:-python3}"
if [[ "${1:-}" == "--python" ]]; then
  PYTHON="$2"
  shift 2
fi

coverage_dir=""
if [[ "${1:-}" == "--coverage-dir" ]]; then
  coverage_dir="$2"
  shift 2
  mkdir -p "$coverage_dir"
fi
RUNNER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

export PYTHON logs coverage_dir RUNNER_ROOT
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

echo "[tests] $# files, $jobs at a time"

status=0
file_count=$#
run_files() {
  local concurrency="$1" marker="$2" index=0 file
  shift 2
  export marker
  [[ $# -gt 0 ]] || return 0
  for file in "$@"; do
    printf '%s\0%s\0' "$index" "$file"
    ((index += 1))
  done |
  xargs -0 -P "$concurrency" -n2 bash -c '
    index="$1"
    file="$2"
    log="$logs/$index.log"
    command=("$PYTHON")
    pytest_args=(-q -ra --capture=tee-sys "$file")
    if [[ -n "$marker" ]]; then
      pytest_args+=(-m "$marker")
    fi
    if [[ "$marker" == latency ]]; then
      # A runner contract test can itself be measured. Its nested latency
      # process must not inherit automatic coverage subprocess startup.
      unset COVERAGE_PROCESS_START COVERAGE_PROCESS_CONFIG
    fi
    if [[ -n "$coverage_dir" ]]; then
      # The runner also executes external test fixtures from their directory.
      command+=(-m coverage run --rcfile "$RUNNER_ROOT/pyproject.toml" --data-file "$coverage_dir/.coverage" --source "$RUNNER_ROOT/app/chemvas")
    fi
    if "${command[@]}" -m pytest "${pytest_args[@]}" >"$log" 2>&1; then
      printf "[tests] %s: %s\n" "$file" "$(tail -1 "$log")"
      awk '\''/^SKIPPED / { print "[tests] " $0 }'\'' "$log"
      rm -f "$log"
    else
      code=$?
      printf "[tests] FAILED %s\n" "$file" >&2
      printf "[tests] pytest exit code: %s\n" "$code" >&2
      cat "$log" >&2
      exit 1
    fi
  ' _ || status=1
}

# This file has strict UI-thread latency budgets. Keep those assertions intact
# and avoid competing with other test files, especially under instrumentation.
parallel_files=()
serial_files=()
for file in "$@"; do
  if [[ "${file##*/}" == test_ring_changing_correspondence.py ]]; then
    serial_files+=("$file")
  else
    parallel_files+=("$file")
  fi
done
run_files "$jobs" "" ${parallel_files[@]+"${parallel_files[@]}"}
if [[ ${#serial_files[@]} -gt 0 ]]; then
  echo "[tests] Timing-sensitive files: ${#serial_files[@]}, one at a time"
  if [[ -n "$coverage_dir" ]]; then
    run_files 1 "not latency" "${serial_files[@]}"
    echo "[tests] Wall-clock latency tests: no coverage instrumentation"
    coverage_dir="" run_files 1 latency "${serial_files[@]}"
  else
    run_files 1 "" "${serial_files[@]}"
  fi
fi

if [[ "$status" -ne 0 ]]; then
  # Every process runs, so a broken tree reports all of its failures at once
  # rather than only the first one the old sequential loop reached.
  exit 1
fi

echo "[tests] $file_count files passed"
