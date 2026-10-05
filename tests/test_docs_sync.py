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
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QKeyEvent, QKeySequence
from PyQt6.QtTest import QTest

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.domain.document import VALID_BOND_STYLES, Atom, Bond, MoleculeModel
from chemvas.ui.canvas.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.window.main_window_config import TOOL_ACTION_SPECS
from tests.canvas_factory import build_canvas_view
from tests.runtime_services import shortcut_service_for

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

README = ROOT / "README.md"
README_KO = ROOT / "README.ko.md"
REFERENCE = ROOT / "docs" / "REFERENCE.md"
REFERENCE_KO = ROOT / "docs" / "REFERENCE.ko.md"
AGENT_CLI = ROOT / "docs" / "AGENT_CLI.md"
CHANGELOG = ROOT / "CHANGELOG.md"
READMES = (README, README_KO)
FIRST_SCHEME = ROOT / "docs" / "FIRST_SCHEME.md"
FIRST_SCHEME_KO = ROOT / "docs" / "FIRST_SCHEME.ko.md"


@pytest.fixture
def canvas(qt_application):
    view = build_canvas_view()
    yield view
    schedule_canvas_deletion_for(view)
    qt_application.sendPostedEvents(view, QEvent.Type.DeferredDelete)


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
    src = _read(APP / "chemvas" / "domain" / "document" / "schema.py")
    match = re.search(r"(?m)^CANVAS_FILE_VERSION\s*=\s*(\d+)", src)
    assert match, "could not find CANVAS_FILE_VERSION in domain/document/state.py"
    return int(match.group(1))


def _dist_name() -> str:
    src = _read(ROOT / "pyproject.toml")
    match = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', src)
    assert match, "could not find project name in pyproject.toml"
    return match.group(1)


def _tool_hotkeys() -> dict[str, str]:
    """Map each tool's UI label to its hotkey, read from the tooltip
    hints in TOOL_ACTION_SPECS (the same strings shown to the user)."""
    src = _read(APP / "chemvas" / "ui" / "window" / "main_window_config.py")
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
    if ".dev" in version:
        assert "## [Unreleased]" in _read(CHANGELOG)
        assert tuple(map(int, version.split(".dev")[0].split("."))) > tuple(
            map(int, released[0].split("."))
        )
        return
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


def test_readmes_show_the_published_install_command():
    name = _dist_name()
    for path in READMES:
        assert f"pip install {name}" in _collapse(_read(path)), (
            f"{path.name}: missing the 'pip install {name}' install command"
        )


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


def _cited_tool_hotkeys(text: str) -> list[tuple[str, str]]:
    """Every toolbar tool a guide names in bold with a keycap right after it,
    e.g. "**Select** tool (`Space`)"."""
    labels = "|".join(re.escape(label) for _key, label, *_ in TOOL_ACTION_SPECS)
    return re.findall(rf"\*\*({labels})\*\*[^`]{{0,10}}`([^`]+)`", _collapse(text))


def _stale_tool_hotkeys(canvas, text: str) -> list[tuple[str, str]]:
    """Press each cited keycap on the canvas and return the citations whose
    key does not switch to the tool the guide names."""
    tools = {label: tool for _key, label, tool, _icon, _tip in TOOL_ACTION_SPECS}
    stale = []
    for label, keycap in _cited_tool_hotkeys(text):
        # Start from another tool so that a key doing nothing is caught.
        canvas.services.tool_mode_controller.set_tool(
            next(tool for tool in tools.values() if tool != tools[label])
        )
        combination = QKeySequence(keycap)[0]
        QTest.keyClick(canvas, combination.key(), combination.keyboardModifiers())
        if canvas.services.tool_controller.active.name != tools[label]:
            stale.append((label, keycap))
    return stale


def test_first_scheme_guides_match_tool_key_bindings(canvas):
    english = _cited_tool_hotkeys(_read(FIRST_SCHEME))
    assert english, f"{FIRST_SCHEME.name}: names no tool with its hotkey"
    assert _cited_tool_hotkeys(_read(FIRST_SCHEME_KO)) == english, (
        f"{FIRST_SCHEME_KO.name} cites other tool hotkeys than {FIRST_SCHEME.name}"
    )
    assert _stale_tool_hotkeys(canvas, _read(FIRST_SCHEME)) == [], (
        f"{FIRST_SCHEME.name}: these keys do not select the tool cited with them"
    )


def test_tool_key_binding_check_flags_one_stale_citation(canvas):
    # Every citation counts: one stale keycap is not hidden by a correct one.
    text = "Pick the **Select** tool (`Space`), then **Select** (`S`) again."
    assert _stale_tool_hotkeys(canvas, text) == [("Select", "S")]


_BOND_ORDER_NAMES = {1: "single", 2: "double", 3: "triple"}
# The words a bond is named with, e.g. "Bold double" or "dotted".
_BOND_WORDS = {word for style in VALID_BOND_STYLES for word in style.split("_")}


def _bond_styled_by(keycap: str) -> tuple[str, int] | None:
    """Press ``keycap`` over a single bond and return the (style, order) its
    binding applies, or None when the key does not restyle the bond."""
    applied: list[tuple[str, int]] = []
    canvas = SimpleNamespace(
        model=MoleculeModel(
            atoms={1: Atom("C", 0.0, 0.0), 2: Atom("C", 40.0, 0.0)},
            bonds=[Bond(1, 2, 1)],
        ),
        services=SimpleNamespace(structure_build_service=mock.Mock()),
    )
    service = shortcut_service_for(
        canvas,
        scene_transform_controller=SimpleNamespace(
            apply_bond_style=lambda _bond_id, style, order: applied.append(
                (style, order)
            )
        ),
        tool_mode_controller=None,
    )
    combination = QKeySequence(keycap)[0]
    service.handle_bond_hotkey(
        QKeyEvent(
            QEvent.Type.KeyPress,
            combination.key(),
            combination.keyboardModifiers(),
            keycap[-1],
        ),
        0,
    )
    return applied[0] if applied else None


def _bond_hotkey_lists(path: Path, drawing: str, editing: str) -> tuple[str, str]:
    """The bond entry of a reference's drawing features and its hovered-bond
    shortcut line, found by the patterns of their bold headings."""
    text = _read(path)
    entry = re.search(rf"(?ms)^- \*\*{drawing}\*\*.*?(?=^- \*\*|\Z)", text)
    line = re.search(rf"(?m)^- \*\*{editing}\b.*$", text)
    assert entry and line, f"{path.name}: missing a bond hotkey list"
    return entry[0], line[0]


def _cited_bond_hotkeys(drawing: str, editing: str) -> list[tuple[str, str]]:
    """The (keycap, name) pairs a reference's bond lists cite."""
    # "`d` (dotted)" in the drawing features, "Dotted `d`" in the shortcuts.
    cited = re.findall(r"`([^`]+)` \(([^)]+)\)", drawing)
    cited += [
        (keycap, name)
        for name, keycap in re.findall(r"(?:: |, )([^`,:]+?) `([^`]+)`", editing)
    ]
    return cited


def _misnamed_bond_hotkeys(
    cited: list[tuple[str, str]],
) -> list[tuple[str, str, tuple[str, int] | None]]:
    """Press each cited key over a bond and return the citations whose name is
    not the bond it draws, with the (style, order) the key applies, or None when
    it restyles nothing although it is named after a bond."""
    misnamed: list[tuple[str, str, tuple[str, int] | None]] = []
    for keycap, name in cited:
        # "bond" names no particular bond, as in "Dotted bond `d`".
        words = set(re.findall(r"[a-z]+", name.lower())) - {"bond"}
        bond = _bond_styled_by(keycap)
        if bond is None:
            # Such a key may only be cited for an action on the hovered bond,
            # e.g. "double-bond alignment" or "Ring fusion", not under a bond name.
            if words <= _BOND_WORDS:
                misnamed.append((keycap, name, None))
            continue
        style, order = bond
        # The name says what kind of bond the key draws and, beyond a single
        # bond, its order, and every other word it uses fits that bond too.
        required = {style.split("_")[0]}
        if order > 1:
            required.add(_BOND_ORDER_NAMES[order])
        if not required <= words <= {*style.split("_"), _BOND_ORDER_NAMES[order]}:
            misnamed.append((keycap, name, bond))
    return misnamed


def test_reference_names_bond_hotkeys_after_the_bond_they_draw() -> None:
    cited = _cited_bond_hotkeys(*_bond_hotkey_lists(REFERENCE, "Bonds", "Bond Editing"))
    assert _misnamed_bond_hotkeys(cited) == [], (
        f"{REFERENCE.name}: these keys do not draw the bond they are named after"
    )
    assert any(_bond_styled_by(keycap) for keycap, _name in cited), (
        f"{REFERENCE.name}: names no bond with its hotkey"
    )


@pytest.mark.parametrize(
    ("cited", "rewritten", "misnamed"),
    [
        # Rewrites that keep the fact.
        ("Dotted `d`", "Dotted bond `d`", []),
        ("`2` (double)", "`2` (double bond)", []),
        # A name that leaves out the order or kind of bond the key draws.
        ("Bold double `Shift+B`", "Bold `Shift+B`", [("Shift+B", "Bold")]),
        ("Dotted double `Shift+D`", "Dotted `Shift+D`", [("Shift+D", "Dotted")]),
        ("Bold double `Shift+B`", "Double `Shift+B`", [("Shift+B", "Double")]),
        # A name for another bond than the key draws.
        ("Dotted `d`", "Dotted line `d`", [("d", "Dotted line")]),
    ],
)
def test_bond_hotkey_check_judges_the_bond_named_not_the_wording(
    cited: str, rewritten: str, misnamed: list[tuple[str, str]]
) -> None:
    lists = _bond_hotkey_lists(REFERENCE, "Bonds", "Bond Editing")
    assert sum(text.count(cited) for text in lists) == 1
    drawing, editing = (text.replace(cited, rewritten) for text in lists)
    flagged = _misnamed_bond_hotkeys(_cited_bond_hotkeys(drawing, editing))
    assert [(keycap, name) for keycap, name, _bond in flagged] == misnamed


def test_korean_reference_cites_the_same_bond_hotkeys() -> None:
    english = _bond_hotkey_lists(REFERENCE, "Bonds", "Bond Editing")
    korean = _bond_hotkey_lists(REFERENCE_KO, r"결합 \(Bonds\)", "결합 편집")
    # The names are translated; the keycaps and their order are not.
    for english_list, korean_list in zip(english, korean, strict=True):
        assert re.findall(r"`([^`]+)`", korean_list) == re.findall(
            r"`([^`]+)`", english_list
        ), f"{REFERENCE_KO.name} cites other bond hotkeys than {REFERENCE.name}"


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
    "SECURITY.md",
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
