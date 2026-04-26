from __future__ import annotations

from ui.main_window_config import (
    BOND_TOOL_ACTION_SPECS,
    MARK_TOOL_ACTION_SPECS,
    TOOL_ACTION_SPECS,
)


class MainWindowToolActionService:
    @staticmethod
    def _show_status_message(window, message: str) -> None:
        show_status_message = getattr(window, "_show_status_message", None)
        if callable(show_status_message):
            show_status_message(message)
            return
        window.statusBar().showMessage(message)

    def build_checkable_tool_action(
        self,
        window,
        tool_group,
        *,
        key: str,
        label: str,
        icon_method: str,
        tooltip: str,
        callback,
    ) -> tuple[str, object]:
        action = window._new_tool_action(label)
        action.setCheckable(True)
        action.setIcon(getattr(window, icon_method)())
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        tool_group.addAction(action)
        return key, action

    def activate_bond_style_tool(self, window, value: str) -> None:
        window._set_tool_with_status("bond", reset_bond_style=False)
        window._set_bond_style(value)

    def activate_mark_tool(self, window, kind: str) -> None:
        window.canvas.set_mark_kind(kind)
        self._show_status_message(window, "Mark Tool")
        refresh_status_context = getattr(window, "_refresh_status_context", None)
        if callable(refresh_status_context):
            refresh_status_context()

    def build_tool_actions(self, window, tool_group) -> dict[str, object]:
        actions = dict(
            self.build_checkable_tool_action(
                window,
                tool_group,
                key=key,
                label=label,
                icon_method=icon_method,
                tooltip=tooltip,
                callback=lambda tool=tool: window._set_tool_with_status(tool),
            )
            for key, label, tool, icon_method, tooltip in TOOL_ACTION_SPECS
        )
        actions.update(
            dict(
                self.build_checkable_tool_action(
                    window,
                    tool_group,
                    key=key,
                    label=label,
                    icon_method=icon_method,
                    tooltip=tooltip,
                    callback=lambda value=value: self.activate_bond_style_tool(window, value),
                )
                for key, label, value, icon_method, tooltip in BOND_TOOL_ACTION_SPECS
            )
        )
        actions.update(
            dict(
                self.build_checkable_tool_action(
                    window,
                    tool_group,
                    key=key,
                    label=label,
                    icon_method=icon_method,
                    tooltip=tooltip,
                    callback=lambda kind=kind: self.activate_mark_tool(window, kind),
                )
                for key, label, kind, icon_method, tooltip in MARK_TOOL_ACTION_SPECS
            )
        )
        return actions


__all__ = ["MainWindowToolActionService"]
