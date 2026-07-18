"""Pure helpers for rendering document chrome (tab text + window title).

The unsaved marker is applied only at the *display* layer — the raw document
display name stays clean (it is reused verbatim in status messages and "Save
changes to {name}?" prompts). Keeping this logic Qt-free makes it directly
unit-testable and keeps the marker glyph in one place.
"""

from __future__ import annotations

# U+25CF BLACK CIRCLE — a compact, high-contrast "unsaved" dot, the same
# convention used by editors like VS Code for modified tabs.
UNSAVED_MARKER = "●"

APP_TITLE_SUFFIX = "Chemvas"


def decorate_tab_title(display_name: str, *, dirty: bool) -> str:
    """Tab label for a document, prefixed with the unsaved dot when dirty."""
    if dirty:
        return f"{UNSAVED_MARKER} {display_name}"
    return display_name


def window_title(display_name: str) -> str:
    """Main-window title, e.g. ``Aspirin.chemvas — Chemvas[*]``.

    The trailing ``[*]`` is Qt's window-modified placeholder: paired with
    ``setWindowModified(dirty)``, the platform renders a native modified hint
    (e.g. the dot in the macOS close button) and strips the placeholder text
    when clean. Unlike a tab, the title bar has this native affordance, so no
    ``●`` prefix is added here — the dot lives on the tab only.
    """
    return f"{display_name} — {APP_TITLE_SUFFIX}[*]"


__all__ = [
    "APP_TITLE_SUFFIX",
    "UNSAVED_MARKER",
    "decorate_tab_title",
    "window_title",
]
