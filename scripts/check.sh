#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Prints "MAJOR.MINOR" for an interpreter, or nothing when it does not run.
python_version() {
  local version
  version="$("$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || return 0
  printf '%s' "${version%$'\r'}"
}

# Succeeds when "MAJOR.MINOR" meets the floor read from requires-python.
python_version_ok() {
  [[ "$1" =~ ^([0-9]+)\.([0-9]+)$ ]] || return 1
  local major="${BASH_REMATCH[1]}" minor="${BASH_REMATCH[2]}"
  ((major > required_major || (major == required_major && minor >= required_minor)))
}

venv_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    printf '%s' "$ROOT/.venv/bin/python"
  elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
    printf '%s' "$ROOT/.venv/Scripts/python.exe"
  fi
}

# Without an explicit interpreter the gate owns a checkout-local .venv: it is
# created from the first interpreter that meets requires-python and kept in
# step with the development extras, so a fresh clone or worktree needs no
# setup and never runs on an interpreter the project does not support.
prepare_local_venv() {
  local required
  required="$(sed -n 's/^requires-python *= *">= *\([0-9][0-9]*\.[0-9][0-9]*\)" *$/\1/p' pyproject.toml)"
  if [[ ! "$required" =~ ^([0-9]+)\.([0-9]+)$ ]]; then
    echo "[check] ERROR: cannot read a '>=MAJOR.MINOR' requires-python from pyproject.toml." >&2
    exit 1
  fi
  required_major="${BASH_REMATCH[1]}"
  required_minor="${BASH_REMATCH[2]}"

  # A linked .venv belongs to another checkout; installing this one's extras
  # into it would repoint that checkout's editable install here.
  if [[ -L "$ROOT/.venv" ]]; then
    echo "[check] ERROR: $ROOT/.venv is a symbolic link to $(readlink "$ROOT/.venv")." >&2
    echo "[check] The gate installs only into this checkout's own environment and leaves the link alone." >&2
    echo "[check] Remove the link so the gate can create .venv here, or set PYTHON_BIN." >&2
    exit 1
  fi

  local python version prefix
  python="$(venv_python)"
  if [[ -n "$python" ]]; then
    version="$(python_version "$python")"
    if ! python_version_ok "$version"; then
      echo "[check] ERROR: $ROOT/.venv runs Python ${version:-that does not start}, but the project requires >=$required." >&2
      echo "[check] Remove .venv so the gate can recreate it, or set PYTHON_BIN." >&2
      exit 1
    fi
  elif [[ -e "$ROOT/.venv" ]]; then
    echo "[check] ERROR: $ROOT/.venv exists but has no usable Python interpreter." >&2
    echo "[check] Remove .venv so the gate can recreate it, or set PYTHON_BIN." >&2
    exit 1
  else
    local candidates=() tried=() seen=" " name dir candidate
    local names=(python3.13 python3.12 python3 python)
    local dirs=(/usr/local/bin /opt/homebrew/bin)
    if [[ -n "${HOME:-}" ]]; then
      dirs+=("$HOME/.local/bin" "$HOME/miniconda3/bin" "$HOME/anaconda3/bin")
    fi
    dirs+=(/opt/conda/bin)
    for name in "${names[@]}"; do
      if candidate="$(command -v "$name" 2>/dev/null)"; then
        candidates+=("$candidate")
      fi
    done
    for dir in "${dirs[@]}"; do
      for name in "${names[@]}"; do
        if [[ -x "$dir/$name" ]]; then
          candidates+=("$dir/$name")
        fi
      done
    done
    for candidate in ${candidates[@]+"${candidates[@]}"}; do
      if [[ "$seen" == *" $candidate "* ]]; then
        continue
      fi
      seen+="$candidate "
      version="$(python_version "$candidate")"
      if ! python_version_ok "$version"; then
        tried+=("$candidate (${version:-does not run})")
        continue
      fi
      echo "[check] Creating .venv with $candidate (Python $version)"
      if "$candidate" -m venv "$ROOT/.venv" && [[ -n "$(venv_python)" ]]; then
        python="$(venv_python)"
        break
      fi
      # Only reached when no .venv existed, so what is left here is this
      # attempt's own partial environment.
      if [[ ! -L "$ROOT/.venv" ]]; then
        rm -rf "$ROOT/.venv"
      fi
      tried+=("$candidate ($version, could not create a virtual environment)")
    done
    if [[ -z "$python" ]]; then
      echo "[check] ERROR: no Python interpreter satisfies requires-python >=$required." >&2
      echo "[check] Searched PATH and ${dirs[*]} for ${names[*]}." >&2
      if [[ ${#tried[@]} -gt 0 ]]; then
        echo "[check] Unsuitable:" >&2
        printf '[check]   %s\n' "${tried[@]}" >&2
      fi
      echo "[check] Install Python $required or newer, or set PYTHON_BIN." >&2
      exit 1
    fi
  fi

  if ! "$python" -c 'import os, sys; sys.exit(0 if os.path.samefile(sys.prefix, sys.argv[1]) else 1)' "$ROOT/.venv" >/dev/null 2>&1; then
    prefix="$("$python" -c 'import sys; print(sys.prefix)' 2>/dev/null)" || true
    prefix="${prefix%$'\r'}"
    echo "[check] ERROR: $python runs from ${prefix:-an unknown prefix}, not from $ROOT/.venv." >&2
    echo "[check] Remove .venv so the gate can recreate it, or set PYTHON_BIN." >&2
    exit 1
  fi

  # The stamp records the pyproject.toml the extras were installed from, so a
  # dependency change reinstalls them and an unchanged one costs nothing.
  local stamp="$ROOT/.venv/.check-dev-install" expected
  expected="$(cksum < pyproject.toml)"
  if [[ "$(cat "$stamp" 2>/dev/null)" != "$expected" ]] ||
    ! "$python" -c 'import jsonschema, mypy, pytest, ruff, PIL, PyQt6' >/dev/null 2>&1; then
    echo "[check] Installing development dependencies into .venv"
    rm -f "$stamp"
    if ! "$python" -m pip install --disable-pip-version-check -q -e '.[dev]'; then
      echo "[check] ERROR: installing the development dependencies into .venv failed." >&2
      exit 1
    fi
    printf '%s\n' "$expected" >"$stamp"
  fi
  PYTHON="$python"
}

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/Scripts/python.exe" ]]; then
  PYTHON="$VIRTUAL_ENV/Scripts/python.exe"
else
  prepare_local_venv
fi
if ! "$PYTHON" -c 'import sys' >/dev/null 2>&1; then
  echo "[check] ERROR: $PYTHON is not an executable Python interpreter." >&2
  exit 1
fi

# Without the environment variable the machine.json assertion in
# tests/test_calculation_step_cli.py passes while validating nothing, so the
# gate resolves the canonical validator itself and exports it for the whole
# test pass.
CONTRACT_REPO="${FACTORY_MACHINE_CONTRACT_REPO:-${HOME:-}/machine_contracts}"
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
platform="$("$PYTHON" -c 'import sys; print(sys.platform)')"
platform="${platform%$'\r'}"
case "$platform" in
  linux) echo "[check] Scope: Linux/WSL common suite and Linux filesystem cases (Qt offscreen)." ;;
  darwin) echo "[check] Scope: macOS common suite (Qt offscreen) and serial Cocoa menu/focus workflows." ;;
  win32) echo "[check] Scope: Windows common suite and native cases (Windows Qt, serial window input)." ;;
  *) echo "[check] Scope: $platform common suite (Qt offscreen); platform support is not established." ;;
esac
echo "[check] Platform/dependency skips are reported by pytest; native packaging and RDKit have dedicated CI jobs."

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

# scripts/run_test_files.sh owns how the files are run — one pytest process
# each, several at a time — so this script, the CI test job and the RDKit job
# cannot drift apart on it. Arguments narrow the run to the given files.
echo "[check] Tests"
# Subprocess CLI tests must exercise this checkout, even when its interpreter
# comes from an editable installation in a different registered worktree.
export PYTHONPATH="$ROOT/app${PYTHONPATH:+:$PYTHONPATH}"
if [[ $# -gt 0 ]]; then
  files=("$@")
else
  # Keep recursive discovery aligned with CI so a test remains part of the
  # gate if its feature package places it below tests/.
  files=()
  while IFS= read -r file; do
    files+=("$file")
  done < <(find tests -name 'test_*.py' | sort)
fi

# macOS offscreen cannot restore popup focus like Cocoa. These shown-window
# workflow files run against Cocoa, one at a time so windows do not steal focus.
common_backend=offscreen
if [[ "$platform" == "win32" ]]; then
  # Match the product's Windows font engine; offscreen cannot resolve its raw
  # glyph fonts. Native windows share desktop focus, so run one file at a time.
  common_backend=windows
  export CHECK_JOBS=1
fi
common_files=()
cocoa_files=()
for file in "${files[@]}"; do
  if [[ "$platform" == "darwin" ]]; then
    case "${file##*/}" in
      test_note_formatting_workflows.py|test_note_appearance_workflows.py)
        cocoa_files+=("$file")
        continue
        ;;
    esac
  fi
  common_files+=("$file")
done
status=0
if [[ ${#common_files[@]} -gt 0 ]]; then
  QT_QPA_PLATFORM="$common_backend" bash "$ROOT/scripts/run_test_files.sh" --python "$PYTHON" "${common_files[@]}" || status=1
fi
if [[ ${#cocoa_files[@]} -gt 0 ]]; then
  echo "[check] Cocoa workflows: ${#cocoa_files[@]} files, serial native window input."
  QT_QPA_PLATFORM=cocoa CHECK_JOBS=1 bash "$ROOT/scripts/run_test_files.sh" --python "$PYTHON" "${cocoa_files[@]}" || status=1
fi
exit "$status"
