import os


DEFAULT_SAVE_EXTENSION = ".ldraw"


def resolve_save_path(current_path: str | None = None, dialog_path: str | None = None) -> str | None:
    if current_path:
        return current_path
    return resolve_save_as_path(dialog_path)


def resolve_save_as_path(dialog_path: str | None) -> str | None:
    if not dialog_path:
        return None
    if os.path.splitext(dialog_path)[1]:
        return dialog_path
    return f"{dialog_path}{DEFAULT_SAVE_EXTENSION}"


def resolve_load_path(dialog_path: str | None) -> str | None:
    if not dialog_path:
        return None
    return dialog_path
