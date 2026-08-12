#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "[check] ERROR: no Python interpreter is available." >&2
  echo "[check] Activate a development environment or set PYTHON_BIN." >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys' >/dev/null 2>&1; then
  echo "[check] ERROR: $PYTHON is not an executable Python interpreter." >&2
  exit 1
fi

# Without the environment variable the machine.json assertion in
# tests/test_calculation_step_cli.py passes while validating nothing, so the
# gate resolves the canonical validator itself and exports it for the whole
# test pass.
CONTRACT_REPO="${FACTORY_MACHINE_CONTRACT_REPO:-$HOME/machine_contracts}"
CONTRACT_VALIDATOR="$CONTRACT_REPO/scripts/validate.py"
if [[ ! -f "$CONTRACT_VALIDATOR" ]]; then
  echo "[check] ERROR: contract validator not found at $CONTRACT_VALIDATOR." >&2
  echo "[check] Clone dhsohn/machine-contracts there, or set FACTORY_MACHINE_CONTRACT_REPO." >&2
  exit 1
fi
export FACTORY_MACHINE_CONTRACT_VALIDATOR="$CONTRACT_VALIDATOR"

if ! "$PYTHON" -c 'import jsonschema' >/dev/null 2>&1; then
  echo "[check] ERROR: the contract validator dependency 'jsonschema' is missing." >&2
  echo "[check] Install the development dependencies with: $PYTHON -m pip install -e '.[dev]'" >&2
  exit 1
fi

echo "[check] Using Python: $("$PYTHON" -c 'import sys; print(sys.executable)')"

pinned="$(sed -n 's/^ *ref: *\([0-9a-f]\{40\}\).*/\1/p' .github/workflows/ci.yml | head -1)"
local_head="$(git -C "$CONTRACT_REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
if [[ -n "$pinned" && "$pinned" != "$local_head" ]]; then
  echo "[check] NOTE: contract clone is at ${local_head:0:7}, CI pins ${pinned:0:7}."
fi

echo "[check] Ruff"
"$PYTHON" -m ruff check .

echo "[check] Ruff format"
"$PYTHON" -m ruff format --check .

echo "[check] mypy"
"$PYTHON" -m mypy

# Qt keeps global application state that does not fully reset between test
# modules, so CI runs every test_*.py in its own pytest process and one shared
# process is not the gate. Arguments narrow the loop to the given files.
echo "[check] Tests, one process per file"
if [[ $# -gt 0 ]]; then
  files=("$@")
else
  mapfile -t files < <(find tests -maxdepth 1 -name 'test_*.py' | sort)
fi
total="${#files[@]}"
index=0
log="$(mktemp)"
trap 'rm -f "$log"' EXIT
for f in "${files[@]}"; do
  index=$((index + 1))
  QT_QPA_PLATFORM=offscreen "$PYTHON" -m pytest -q "$f" > "$log" 2>&1 || {
    echo "[check] FAILED in $f ($index/$total):" >&2
    tail -30 "$log" >&2
    exit 1
  }
  printf '[check] %3d/%d %s: %s\n' "$index" "$total" "$f" "$(tail -1 "$log")"
done
