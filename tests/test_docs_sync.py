"""Documentation <-> code synchronization guards.

Each test here pins a *user-facing fact* stated in the docs (README.md,
README.ko.md, CHANGELOG.md) to its single source of truth in code, so the two
cannot drift apart silently. These fill the exact gap that once let the README
advertise the SMILES button as "Render" (code: "Insert"), a version-1 file
format (code: 4), PyPI as a future roadmap item (already published), and a
fused "Atom/Text" hotkey (code: Atom `A`, Text `T`).

Following test_architecture_boundaries: derive the expected value from code and
assert the docs *contain* it. Do NOT freeze prose wording -- an innocent rewrite
that preserves the fact must keep passing. If a doc claim cannot be tied back to
a code source of truth, it does not belong here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

README = ROOT / "README.md"
README_KO = ROOT / "README.ko.md"
CHANGELOG = ROOT / "CHANGELOG.md"
READMES = (README, README_KO)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collapse(text: str) -> str:
    """Flatten whitespace so a fact split across wrapped lines still matches."""
    return re.sub(r"\s+", " ", text)


# --- source-of-truth extractors -------------------------------------------


def _app_version() -> str:
    src = _read(APP / "chemvas" / "__init__.py")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', src)
    assert match, "could not find __version__ in chemvas/__init__.py"
    return match.group(1)


def _canvas_file_version() -> int:
    src = _read(APP / "chemvas" / "domain" / "document" / "state.py")
    match = re.search(r"(?m)^CANVAS_FILE_VERSION\s*=\s*(\d+)", src)
    assert match, "could not find CANVAS_FILE_VERSION in domain/document/state.py"
    return int(match.group(1))


def _smiles_button_label() -> str:
    src = _read(APP / "chemvas" / "ui" / "main_window_panel_toolbar.py")
    # The SMILES insert button is tagged with objectName "smiles_render_button";
    # its displayed label is the setText(...) right after.
    anchor = src.index('"smiles_render_button"')
    match = re.search(r'setText\("([^"]+)"\)', src[anchor : anchor + 400])
    assert match, "could not find setText(...) for the SMILES button"
    return match.group(1)


def _dist_name() -> str:
    src = _read(ROOT / "pyproject.toml")
    match = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', src)
    assert match, "could not find project name in pyproject.toml"
    return match.group(1)


def _tool_hotkeys() -> dict[str, str]:
    """Map each tool's UI label to its ChemDraw hotkey, read from the tooltip
    hints in TOOL_ACTION_SPECS (the same strings shown to the user)."""
    src = _read(APP / "chemvas" / "ui" / "main_window_config.py")
    hotkeys: dict[str, str] = {}
    for label, hint in re.findall(
        r'\(\s*"[^"]+",\s*"([^"]+)",\s*"[^"]+",\s*"[^"]+",\s*"([^"]*ChemDraw:[^"]*)"',
        src,
    ):
        key = re.search(r"ChemDraw:\s*([^),]+)", hint)
        if key:
            hotkeys[label] = key.group(1).strip()
    return hotkeys


# --- guards ----------------------------------------------------------------


def test_changelog_latest_release_matches_package_version():
    version = _app_version()
    released = re.findall(r"(?m)^## \[(\d+\.\d+\.\d+)\]", _read(CHANGELOG))
    assert released, "no released version heading (## [x.y.z]) in CHANGELOG.md"
    assert released[0] == version, (
        f"CHANGELOG newest release [{released[0]}] != chemvas.__version__ "
        f"({version}) -- bump them together when cutting a release"
    )


def test_readmes_document_current_file_format_version():
    version = _canvas_file_version()
    for path in READMES:
        text = _collapse(_read(path))
        found = re.findall(r'"type"\s*:\s*"chemvas"\s*,\s*"version"\s*:\s*(\d+)', text)
        assert found, f"{path.name}: no {{'type':'chemvas',...}} format example found"
        for got in found:
            assert int(got) == version, (
                f"{path.name}: file-format example shows version {got}, but the "
                f"app writes CANVAS_FILE_VERSION={version}"
            )


def test_readmes_name_the_actual_smiles_button_label():
    label = _smiles_button_label()
    for path in READMES:
        assert label in _collapse(_read(path)), (
            f"{path.name}: the SMILES button reads {label!r} in the UI, but that "
            f"label does not appear in the README"
        )


def test_readmes_show_the_published_install_command():
    name = _dist_name()
    for path in READMES:
        assert f"pip install {name}" in _collapse(_read(path)), (
            f"{path.name}: missing the 'pip install {name}' install command"
        )


def test_readmes_match_atom_and_text_tool_hotkeys():
    hotkeys = _tool_hotkeys()
    for label in ("Atom", "Text"):
        assert label in hotkeys, f"{label!r} tool has no ChemDraw hint in config"
    for path in READMES:
        text = _collapse(_read(path))
        for label in ("Atom", "Text"):
            key = hotkeys[label]
            # e.g. "Atom `A`" (en) or "Atom(`A`)" (ko): label, then the keycap in
            # backticks within a couple of separator chars.
            pattern = re.escape(label) + r"[^`]{0,3}`" + re.escape(key) + "`"
            assert re.search(pattern, text), (
                f"{path.name}: does not tie the {label!r} tool to hotkey `{key}` "
                f"(code says {label} = {key})"
            )
