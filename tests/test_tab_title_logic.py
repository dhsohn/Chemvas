from __future__ import annotations

from chemvas.ui.tab_title_logic import (
    APP_TITLE_SUFFIX,
    UNSAVED_MARKER,
    decorate_tab_title,
    window_title,
)


def test_clean_tab_title_is_the_plain_name():
    assert decorate_tab_title("Aspirin.chemvas", dirty=False) == "Aspirin.chemvas"


def test_dirty_tab_title_gets_the_unsaved_marker():
    result = decorate_tab_title("Aspirin.chemvas", dirty=True)
    assert result == f"{UNSAVED_MARKER} Aspirin.chemvas"
    assert result.startswith(UNSAVED_MARKER)


def test_window_title_uses_native_modified_placeholder_not_the_dot():
    # The title bar relies on Qt's [*] + setWindowModified for the native hint,
    # so the ● dot (used on tabs) never appears here.
    title = window_title("Canvas 1")
    assert title == f"Canvas 1 — {APP_TITLE_SUFFIX}[*]"
    assert UNSAVED_MARKER not in title
    assert title.endswith("[*]")


def test_marker_is_not_baked_into_the_raw_name():
    # The decorators must never mutate the underlying name — only prefix it — so
    # status messages and "Save changes to {name}?" prompts stay clean.
    name = "My Reaction"
    assert name in decorate_tab_title(name, dirty=True)
    assert decorate_tab_title(name, dirty=False) == name
