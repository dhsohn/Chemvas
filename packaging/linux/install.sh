#!/usr/bin/env bash
# Install the adjacent frozen bundle, or remove this installer's owned payload.
set -euo pipefail
fail() { printf 'Chemvas: %s\n' "$*" >&2; exit 1; }
[[ $(uname -s) == Linux ]] || fail 'This installer requires Linux.'
[[ $# == 0 || ( $# == 1 && $1 == --uninstall ) ]] || fail 'Usage: bash install.sh [--uninstall]'
: "${HOME:?HOME must be set}"
data=${XDG_DATA_HOME:-"$HOME/.local/share"}
bin="$HOME/.local/bin"
# Absolute paths are required by XDG and desktop Exec. Reject unsupported control
# characters, '=' (desktop syntax) and '%' (GLib executable lookup).
for path in "$HOME" "$data"; do
    [[ $path == /* && $path != *$'\n'* && $path != *$'\r'* && $path != *$'\t'* && $path != *=* && $path != *%* ]] || fail 'Use absolute HOME/XDG_DATA_HOME without controls, = or %.'
done
root="$data/chemvas"
launcher="$bin/chemvas"
desktop="$data/applications/chemvas.desktop"
mime="$data/mime/packages/chemvas.xml"
icon="$data/icons/hicolor/256x256/apps/chemvas.png"
for tool in update-mime-database update-desktop-database; do
    command -v "$tool" >/dev/null || fail "Install shared-mime-info and desktop-file-utils first (missing $tool)."
done
mkdir -p "$data"
lock="$data/.chemvas-install.lock"
mkdir "$lock" 2>/dev/null || fail "Installation is locked: $lock (remove the empty lock only after checking no installer is running)."
trap 'rmdir "$lock"' EXIT
[[ ! -L $root ]] || fail "Refusing symlink installation root: $root"
if [[ ${1:-} == --uninstall ]]; then
    [[ -d $root && -f $root/.chemvas-install-v1 && ! -L $root/.chemvas-install-v1 ]] || fail "No owned installation at $root. If an interrupted install left an empty directory, remove it with rmdir before retrying."
    [[ $(cat "$root/.chemvas-install-v1") == "$root" ]] || fail 'Installation location does not match its receipt.'
    if [[ -L $launcher && $(readlink "$launcher") == "$root/app/chemvas" ]]; then rm -- "$launcher"; fi
    # Preserve registrations replaced or edited after this installation.
    for pair in desktop mime icon; do
        case $pair in desktop) target=$desktop;; mime) target=$mime;; icon) target=$icon;; esac
        if [[ -f $target && ! -L $target ]] && cmp -s "$root/integration/$pair" "$target"; then rm -- "$target"; fi
    done
    # The reserved payload directory contains only application files. Documents
    # and Qt settings live outside it and are never traversed by this removal.
    rm -rf -- "$root"
    update-mime-database "$data/mime"
    update-desktop-database "$data/applications"
    printf 'Removed Chemvas. Documents and settings were preserved.\n'
    exit 0
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
[[ -x $source_dir/chemvas/chemvas && -d $source_dir/chemvas/_internal ]] || fail 'Run install.sh from the extracted Chemvas package.'
for path in "$root" "$launcher" "$desktop" "$mime" "$icon"; do
    [[ ! -e $path && ! -L $path ]] || fail "Path already exists; nothing overwritten: $path. Uninstall an owned Chemvas installation before reinstalling."
done
mkdir -p "$bin" "$(dirname "$desktop")" "$(dirname "$mime")" "$(dirname "$icon")"
# The receipt is written before integration so an interrupted install can be
# removed with the same --uninstall command before retrying. A stop before
# the receipt exists leaves an empty root; rmdir is the safe recovery there.
mkdir "$root"
printf '%s\n' "$root" > "$root/.chemvas-install-v1"
cp -- "$source_dir/install.sh" "$root/uninstall.sh"
mkdir "$root/integration"
cp -a -- "$source_dir/chemvas" "$root/app"
cp -- "$source_dir/chemvas.xml" "$root/integration/mime"
cp -- "$source_dir/chemvas.png" "$root/integration/icon"
# Escape desktop string values, then quoted Exec syntax (two parsing layers).
exec_path=${root//\\/\\\\}; exec_path=${exec_path//\\/\\\\}
exec_path=${exec_path//\"/\\\\\"}; exec_path=${exec_path//\$/\\\\\$}; exec_path=${exec_path//\`/\\\\\`};
while IFS= read -r line; do
    if [[ $line == Exec=* ]]; then printf 'Exec="%s/app/chemvas" %%f\n' "$exec_path"; else printf '%s\n' "$line"; fi
done < "$source_dir/chemvas.desktop" > "$root/integration/desktop"
ln -s -- "$root/app/chemvas" "$launcher"
cp -- "$root/integration/desktop" "$desktop"
cp -- "$root/integration/mime" "$mime"
cp -- "$root/integration/icon" "$icon"
update-mime-database "$data/mime"
update-desktop-database "$data/applications"
printf 'Installed Chemvas in %s\nLaunch: %q\nUninstall: bash %q --uninstall\n' "$root" "$launcher" "$root/uninstall.sh"
printf 'If needed, add ~/.local/bin to PATH. Your default CDXML application was not changed.\n'
