#!/usr/bin/env bash
# Use a standalone CPython environment; Conda builds can mix incompatible expat.
set -euo pipefail
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || { echo 'Build on Linux x86_64.' >&2; exit 1; }
[[ $# == 1 ]] || { echo 'Usage: bash packaging/linux/build.sh NEW_OUTPUT_DIRECTORY' >&2; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
python=${PYTHON_BIN:-python3}
"$python" -c 'import sys; from pathlib import Path; assert not (Path(sys.base_prefix)/"conda-meta").exists(), "Use standalone CPython, not Conda"'
[[ ! -e $1 && ! -L $1 ]] || { echo 'Output directory must not exist.' >&2; exit 1; }
mkdir -p -- "$1"
out=$(cd -- "$1" && pwd -P)
version=$(PYTHONPATH="$repo/app" "$python" -c 'from chemvas import __version__; print(__version__)')
"$python" -m PyInstaller --workpath "$out/work" --distpath "$out/bundle" "$repo/packaging/chemvas.spec"
package="$out/Chemvas-$version-linux-x86_64"
mkdir "$package"
cp -a -- "$out/bundle/chemvas" "$package/chemvas"
cp -- "$repo/packaging/linux/"{install.sh,chemvas.desktop,chemvas.xml,README.md,README.ko.md} "$package/"
cp -- "$repo/app/chemvas/assets/icon/chemvas-256.png" "$package/chemvas.png"
"$package/chemvas/chemvas" --version
# Fail packaging if a required distribution notice was dropped by freezing.
for distribution in pyqt6 pyqt6_qt6 pyqt6_sip pillow; do
    found=false
    while IFS= read -r -d '' metadata; do
        if [[ -n $(find "$metadata" -type f -iname '*license*' -size +0c -print -quit) ]]; then found=true; fi
    done < <(find "$package/chemvas/_internal" -maxdepth 1 -type d -iname "${distribution}-*.dist-info" -print0)
    $found || { echo "Missing notice: $distribution" >&2; exit 1; }
done
tar -czf "$out/Chemvas-$version-linux-x86_64.tar.gz" -C "$out" "$(basename "$package")"
sha256sum "$out/Chemvas-$version-linux-x86_64.tar.gz"
