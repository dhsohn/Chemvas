"""Documentation <-> code synchronization guards.

Each test here pins a *user-facing fact* stated in the docs (README.md,
README.ko.md, docs/REFERENCE.md, CHANGELOG.md) to its single source of truth in
code, so the two cannot drift apart silently. These fill the exact gap that once let the README
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

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

README = ROOT / "README.md"
README_KO = ROOT / "README.ko.md"
REFERENCE = ROOT / "docs" / "REFERENCE.md"
AGENT_CLI = ROOT / "docs" / "AGENT_CLI.md"
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
    src = _read(APP / "chemvas" / "ui" / "main_window_context_bar_page_factories.py")
    # The SMILES insert button is built as action_button("<label>", ...) just
    # before it is tagged with objectName "smiles_render_button".
    anchor = src.index('"smiles_render_button"')
    match = re.search(r'action_button\("([^"]+)"', src[anchor - 400 : anchor])
    assert match, "could not find setText(...) for the SMILES button"
    return match.group(1)


def _dist_name() -> str:
    src = _read(ROOT / "pyproject.toml")
    match = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', src)
    assert match, "could not find project name in pyproject.toml"
    return match.group(1)


def _tool_hotkeys() -> dict[str, str]:
    """Map each tool's UI label to its hotkey, read from the tooltip
    hints in TOOL_ACTION_SPECS (the same strings shown to the user)."""
    src = _read(APP / "chemvas" / "ui" / "main_window_config.py")
    hotkeys: dict[str, str] = {}
    for label, hint in re.findall(
        r'\(\s*"[^"]+",\s*"([^"]+)",\s*"[^"]+",\s*"[^"]+",\s*"([^"]*Shortcut:[^"]*)"',
        src,
    ):
        key = re.search(r"Shortcut:\s*([^),]+)", hint)
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


def test_docs_document_current_file_format_version():
    version = _canvas_file_version()
    # The format example lives in the reference doc...
    text = _collapse(_read(REFERENCE))
    found = re.findall(r'"type"\s*:\s*"chemvas"\s*,\s*"version"\s*:\s*(\d+)', text)
    assert found, f"{REFERENCE.name}: no {{'type':'chemvas',...}} format example found"
    for got in found:
        assert int(got) == version, (
            f"{REFERENCE.name}: file-format example shows version {got}, but the "
            f"app writes CANVAS_FILE_VERSION={version}"
        )
    # ...while the READMEs still name the current document version in prose.
    for path in READMES:
        assert re.search(rf"version\s*{version}\b", _collapse(_read(path))), (
            f"{path.name}: does not state the current .chemvas document version "
            f"(app writes CANVAS_FILE_VERSION={version})"
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


def test_readmes_mark_calculation_handoff_as_an_rdkit_feature() -> None:
    calculation_cli = _read(APP / "chemvas" / "bootstrap" / "calculation_bundle.py")
    assert "from chemvas.core.rdkit_adapter import RDKitAdapter" in calculation_cli

    for path in READMES:
        row = next(
            (line for line in _read(path).splitlines() if "`machine.json`" in line),
            None,
        )
        assert row is not None, f"{path.name}: missing calculation handoff row"
        assert "RDKit" in row, (
            f"{path.name}: calculation handoff uses RDKit but its capability row "
            "does not mark that dependency"
        )
    calculation_docs = _collapse(_read(AGENT_CLI))
    assert 'pip install "chemvas[rdkit]"' in calculation_docs
    for command in ("generate-precomplex", "pack-step"):
        assert re.search(
            rf"{re.escape(command)}[^.]*require(?:s| it)",
            calculation_docs,
            re.IGNORECASE,
        ), f"{AGENT_CLI.name}: does not state that {command} requires RDKit"


def test_packaged_readme_has_no_repository_relative_links() -> None:
    text = _read(README)
    markdown_targets = re.findall(r"!?\[[^\]]*\]\(([^)\s]+)", text)
    html_targets = re.findall(r'\b(?:href|src)="([^"]+)"', text)
    targets = markdown_targets + html_targets
    assert targets, "README.md: no links or images found"
    relative = [target for target in targets if not target.startswith("https://")]
    assert not relative, (
        "README.md is the PyPI long description; repository-relative targets "
        f"would be broken there: {relative}"
    )


def test_docs_embedded_images_exist() -> None:
    """Every image a guide embeds by relative path is in the tree."""
    docs = sorted((ROOT / "docs").glob("*.md"))
    assert docs
    missing: list[str] = []
    embedded = 0
    for path in docs:
        for target in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", _read(path)):
            if target.startswith("https://"):
                continue
            embedded += 1
            if not (path.parent / target).is_file():
                missing.append(f"{path.name}: {target}")
    assert embedded, "no relative image embeds found under docs/"
    assert not missing, f"guides embed images that are not in the tree: {missing}"


def test_reference_matches_atom_and_text_tool_hotkeys():
    hotkeys = _tool_hotkeys()
    for label in ("Atom", "Text"):
        assert label in hotkeys, f"{label!r} tool has no shortcut hint in config"
    text = _collapse(_read(REFERENCE))
    for label in ("Atom", "Text"):
        key = hotkeys[label]
        # e.g. "Atom `A`": label, then the keycap in backticks within a couple
        # of separator chars.
        pattern = re.escape(label) + r"[^`]{0,3}`" + re.escape(key) + "`"
        assert re.search(pattern, text), (
            f"{REFERENCE.name}: does not tie the {label!r} tool to hotkey `{key}` "
            f"(code says {label} = {key})"
        )


def test_reference_names_every_supported_atom_alias() -> None:
    text = _read(REFERENCE)
    atom_labels = re.search(
        r"(?ms)^- \*\*Atom labels\*\*.*?(?=^- \*\*|\Z)",
        text,
    )
    assert atom_labels, f"{REFERENCE.name}: missing Atom labels feature entry"
    documented = tuple(re.findall(r"`([^`]+)`", atom_labels.group(0)))

    assert documented == tuple(ATOM_ALIAS_DEFINITIONS), (
        f"{REFERENCE.name}: Atom labels list {documented!r} does not match the "
        f"canonical aliases {tuple(ATOM_ALIAS_DEFINITIONS)!r}"
    )


# --- Korean twins ----------------------------------------------------------

IMAGE_EMBED = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
MERMAID_FENCE = re.compile(r"(?m)^```mermaid\s*$")
TRANSLATED_ROOT_DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    "RELEASING.md",
    "CODE_OF_CONDUCT.md",
    "examples/README.md",
    "packaging/README.md",
    "packaging/windows/README.md",
    "docs/images/README.md",
)


def _translated_docs() -> list[Path]:
    """Every English guide that ships with a Korean twin: the listed root and
    package READMEs plus every top-level docs/*.md (ADRs are English only)."""
    guides = [ROOT / rel for rel in TRANSLATED_ROOT_DOCS]
    guides += [
        path
        for path in sorted((ROOT / "docs").glob("*.md"))
        if not path.name.endswith(".ko.md")
    ]
    return guides


def _korean_twin(path: Path) -> Path:
    return path.with_name(path.name[: -len(".md")] + ".ko.md")


def test_every_guide_has_a_korean_twin_with_the_same_media() -> None:
    """A Korean reader must get the same figures, GIFs and diagrams as the
    English reader, and each page must link to its other-language twin."""
    guides = _translated_docs()
    assert guides
    for path in guides:
        twin = _korean_twin(path)
        rel = path.relative_to(ROOT).as_posix()
        assert twin.is_file(), f"{rel}: missing Korean twin {twin.name}"
        english = _read(path)
        korean = _read(twin)
        assert sorted(set(IMAGE_EMBED.findall(english))) == sorted(
            set(IMAGE_EMBED.findall(korean))
        ), f"{rel}: the Korean twin does not embed the same images"
        assert len(MERMAID_FENCE.findall(english)) == len(
            MERMAID_FENCE.findall(korean)
        ), f"{rel}: the Korean twin does not carry the same mermaid diagrams"
        assert f"({twin.name})" in english or twin.name in english, (
            f"{rel}: does not link to its Korean twin {twin.name}"
        )
        assert f"({path.name})" in korean or path.name in korean, (
            f"{twin.name}: does not link back to {path.name}"
        )


FENCED_BLOCK = re.compile(r"(?ms)^```([^\n]*)\n(.*?)^```")


def _code_blocks(text: str) -> list[tuple[str, str]]:
    """Fenced blocks other than mermaid diagrams, whose labels are translated."""
    return [
        (label.strip(), body)
        for label, body in FENCED_BLOCK.findall(text)
        if label.strip() != "mermaid"
    ]


def test_korean_twins_keep_commands_and_examples_verbatim() -> None:
    """Commands, JSON requests and file examples are the contract; a Korean
    twin must carry them byte-for-byte, in the same order."""
    for path in _translated_docs():
        rel = path.relative_to(ROOT).as_posix()
        english = _code_blocks(_read(path))
        korean = _code_blocks(_read(_korean_twin(path)))
        assert english == korean, (
            f"{rel}: fenced code blocks differ from the Korean twin "
            f"({len(english)} vs {len(korean)} blocks)"
        )
