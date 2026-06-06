from __future__ import annotations

from PyQt6.QtGui import QAction

from ui.main_window_config import (
    BOND_TOOL_ACTION_SPECS,
    MARK_TOOL_ACTION_SPECS,
    RING_FILL_TOOL_ACTION_SPEC,
    TEMPLATE_TOOL_ACTION_SPEC,
    TOOL_ACTION_SPECS,
)


class MainWindowToolActionService:
    def __init__(
        self,
        *,
        tool_mode_controller_for_window,
        tool_state_service,
        context_page_state_service,
        icon_factory_for_window,
        status_service,
    ) -> None:
        self._tool_mode_controller_for_window = tool_mode_controller_for_window
        self._tool_state = tool_state_service
        self._context_page_state = context_page_state_service
        self._icon_factory_for_window = icon_factory_for_window
        self._status = status_service

    def _tool_mode_controller(self, window):
        return self._tool_mode_controller_for_window(window)

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
    ) -> tuple[str, QAction]:
        icon = getattr(self._icon_factory_for_window(window), icon_method)()
        action = QAction(icon, label, window)
        action.setCheckable(True)
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        tool_group.addAction(action)
        return key, action

    def activate_bond_style_tool(self, window, value: str) -> None:
        self._context_page_state.set_tool_with_status(window, "bond", reset_bond_style=False)
        self._tool_state.set_bond_style(window, value)

    def activate_mark_tool(self, window, kind: str) -> None:
        self._tool_mode_controller(window).set_mark_kind(kind)
        window.statusBar().showMessage("Mark Tool")
        self._status.refresh_status_context(window)

    def activate_template_tool(self, window) -> None:
        self._context_page_state.show_context_page(window, "template")
        window.statusBar().showMessage("Template Tool")
        self._status.refresh_status_context(window)

    def activate_ring_fill_tool(self, window) -> None:
        self._context_page_state.show_context_page(window, "ring_fill")
        window.statusBar().showMessage("Ring Fill Tool")
        self._status.refresh_status_context(window)

    def build_tool_actions(self, window, tool_group) -> dict[str, QAction]:
        actions = dict(
            self.build_checkable_tool_action(
                window,
                tool_group,
                key=key,
                label=label,
                icon_method=icon_method,
                tooltip=tooltip,
                callback=lambda tool=tool: self._context_page_state.set_tool_with_status(window, tool),
            )
            for key, label, tool, icon_method, tooltip in TOOL_ACTION_SPECS
        )
        key, label, icon_method, tooltip = TEMPLATE_TOOL_ACTION_SPEC
        _, template_action = self.build_checkable_tool_action(
            window,
            tool_group,
            key=key,
            label=label,
            icon_method=icon_method,
            tooltip=tooltip,
            callback=lambda: self.activate_template_tool(window),
        )
        actions[key] = template_action
        key, label, icon_method, tooltip = RING_FILL_TOOL_ACTION_SPEC
        _, ring_fill_action = self.build_checkable_tool_action(
            window,
            tool_group,
            key=key,
            label=label,
            icon_method=icon_method,
            tooltip=tooltip,
            callback=lambda: self.activate_ring_fill_tool(window),
        )
        actions[key] = ring_fill_action
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
