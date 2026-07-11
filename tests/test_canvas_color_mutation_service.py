import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsEllipseItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import CompositeCommand, UpdateAtomColorCommand
    from core.model import Atom, Bond
    from ui.bond_graphics_access import add_bond_graphics_for
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_color_mutation_service import (
        CanvasColorMutationService,
        UpdateBondColorCommand,
        UpdateNoteColorCommand,
    )
    from ui.canvas_history_state import CanvasHistoryState
    from ui.canvas_lifecycle import schedule_canvas_deletion_for
    from ui.canvas_smiles_input_state import CanvasSmilesInputState
    from ui.canvas_view import CanvasView
    from ui.graphics_items import AtomDotItem
    from ui.history_commands import UpdateSceneItemCommand
    from ui.note_item import NoteItem
    from ui.note_item_access import (
        committed_note_html_for,
        committed_note_text_for,
        set_committed_note_html_for,
        set_committed_note_text_for,
    )
    from ui.scene_item_state import note_state_dict_for


def _history_service(push=None):
    return SimpleNamespace(push=push if push is not None else mock.Mock())


def _set_atom_graphics(canvas, items=None, dots=None) -> None:
    set_atom_items_for(canvas, dict(items or {}))
    set_atom_dots_for(canvas, dict(dots or {}))


def _color_service_for(canvas, *, graph_service=None) -> CanvasColorMutationService:
    if graph_service is None:
        graph_service = SimpleNamespace(
            bond_sets_for_atoms=mock.Mock(return_value=(set(), set()))
        )
    return CanvasColorMutationService(
        canvas,
        graph_service=graph_service,
        history_service=canvas.services.history_service,
    )


class _FailOnceHistoryState:
    def __init__(self, fail_field: str, history: list, redo_stack: list) -> None:
        self.fail_field = fail_field
        self.read_counts = {"history": 0, "redo_stack": 0}
        self._history = history
        self._redo_stack = redo_stack

    def _read(self, field: str, value: list) -> list:
        self.read_counts[field] += 1
        if self.fail_field == field and self.read_counts[field] == 1:
            raise AttributeError(f"live history {field} capture failed")
        return value

    @property
    def history(self) -> list:
        return self._read("history", self._history)

    @history.setter
    def history(self, value: list) -> None:
        self._history = value

    @property
    def redo_stack(self) -> list:
        return self._read("redo_stack", self._redo_stack)

    @redo_stack.setter
    def redo_stack(self, value: list) -> None:
        self._redo_stack = value


class _FailOnceHistoryService:
    def __init__(self, fail_field: str, history: list, redo_stack: list) -> None:
        self.fail_field = fail_field
        self.state_reads = 0
        self._state = _FailOnceHistoryState(fail_field, history, redo_stack)
        self.push_calls = 0
        self.push_error: BaseException | None = None

    @property
    def state(self) -> _FailOnceHistoryState:
        self.state_reads += 1
        if self.fail_field == "state" and self.state_reads == 1:
            raise AttributeError("live history state capture failed")
        return self._state

    def push(self, command) -> None:
        self.push_calls += 1
        self._state._history.append(command)
        self._state._redo_stack.clear()
        if self.push_error is not None:
            error = self.push_error
            self.push_error = None
            raise error


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas color mutation tests"
)
class CanvasColorMutationServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _dispose_canvas(self, canvas) -> None:
        schedule_canvas_deletion_for(canvas)
        QCoreApplication.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_single_color_rejects_successful_non_target_peer_mutation(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        peer = QGraphicsPathItem()
        peer.setData(0, "shape")
        peer_brush = QBrush(QColor("#111111"))
        QGraphicsPathItem.setBrush(peer, peer_brush)

        class MutatingShape(QGraphicsPathItem):
            def setBrush(self, brush) -> None:
                QGraphicsPathItem.setBrush(self, brush)
                QGraphicsPathItem.setBrush(peer, QBrush(QColor("#ff00ff")))

        target = MutatingShape()
        target.setData(0, "shape")
        target_brush = QBrush(QColor("#222222"))
        QGraphicsPathItem.setBrush(target, target_brush)
        canvas.scene().addItem(target)
        canvas.scene().addItem(peer)
        history = canvas.services.history_service.state

        with self.assertRaisesRegex(RuntimeError, "non-target graphics color"):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                target,
                QColor("#123456"),
            )

        self.assertEqual(QGraphicsPathItem.brush(target), target_brush)
        self.assertEqual(QGraphicsPathItem.brush(peer), peer_brush)
        self.assertEqual(history.history, [])
        self.assertEqual(history.redo_stack, [])

    def test_color_batch_rejects_successful_non_target_peer_mutation(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        peer = QGraphicsPathItem()
        peer.setData(0, "shape")
        peer_brush = QBrush(QColor("#111111"))
        QGraphicsPathItem.setBrush(peer, peer_brush)

        class MutatingShape(QGraphicsPathItem):
            def setBrush(self, brush) -> None:
                QGraphicsPathItem.setBrush(self, brush)
                QGraphicsPathItem.setBrush(peer, QBrush(QColor("#ff00ff")))

        first = MutatingShape()
        second = QGraphicsPathItem()
        for item, value in ((first, "#222222"), (second, "#333333")):
            item.setData(0, "shape")
            QGraphicsPathItem.setBrush(item, QBrush(QColor(value)))
            canvas.scene().addItem(item)
        first_brush = QBrush(QGraphicsPathItem.brush(first))
        second_brush = QBrush(QGraphicsPathItem.brush(second))
        canvas.scene().addItem(peer)
        history = canvas.services.history_service.state

        with self.assertRaisesRegex(RuntimeError, "non-target graphics color"):
            canvas.services.canvas_color_mutation_service.apply_color_to_items(
                [first, second],
                QColor("#123456"),
            )

        self.assertEqual(QGraphicsPathItem.brush(first), first_brush)
        self.assertEqual(QGraphicsPathItem.brush(second), second_brush)
        self.assertEqual(QGraphicsPathItem.brush(peer), peer_brush)
        self.assertEqual(history.history, [])
        self.assertEqual(history.redo_stack, [])

    def test_scene_peer_capture_cannot_redefine_history_baseline(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        history = canvas.services.history_service.state
        sentinel = object()

        class HistoryPoisoningNote(NoteItem):
            armed = True

            def committed_text(self) -> str:
                if self.armed:
                    self.armed = False
                    history.history.append(sentinel)
                return super().committed_text()

        peer = HistoryPoisoningNote(canvas)
        peer.setPlainText("peer")
        peer.setData(0, "note")
        canvas.scene().addItem(peer)
        target = QGraphicsPathItem()
        target.setData(0, "shape")
        target_brush = QBrush(QGraphicsPathItem.brush(target))
        canvas.scene().addItem(target)

        with self.assertRaisesRegex(RuntimeError, "raw history stack contents"):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                target,
                QColor("#123456"),
            )

        self.assertEqual(QGraphicsPathItem.brush(target), target_brush)
        self.assertEqual(history.history, [])
        self.assertEqual(history.redo_stack, [])

    def test_actual_qt_history_alias_replacement_rolls_back_single_and_batch(
        self,
    ) -> None:
        for batch in (False, True):
            with self.subTest(batch=batch):
                canvas = CanvasView()
                self.addCleanup(self._dispose_canvas, canvas)
                atom_ids = [
                    canvas.services.canvas_atom_mutation_service.add_atom(
                        "C",
                        float(index * 20),
                        0.0,
                    )
                    for index in range(2 if batch else 1)
                ]
                items = [atom_dots_for(canvas)[atom_id] for atom_id in atom_ids]
                original_history = canvas.services.history_service
                original_history.state.history.clear()
                original_history.state.redo_stack.clear()
                replacement_history = SimpleNamespace(
                    state=CanvasHistoryState(),
                    push=lambda _command: None,
                )
                callback_calls = [0]

                def replace_canvas_history_aliases(
                    _canvas=canvas,
                    _replacement_history=replacement_history,
                    _callback_calls=callback_calls,
                ) -> None:
                    _callback_calls[0] += 1
                    _canvas.services.history_service = _replacement_history
                    _canvas.runtime_state.history_service = _replacement_history

                original_history.set_change_callback(replace_canvas_history_aliases)
                try:
                    with self.assertRaises(RuntimeError):
                        if batch:
                            canvas.services.canvas_color_mutation_service.apply_color_to_items(
                                items,
                                QColor("#ff0000"),
                            )
                        else:
                            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                                items[0],
                                QColor("#ff0000"),
                            )
                finally:
                    original_history.set_change_callback(None)

                self.assertGreaterEqual(callback_calls[0], 1)
                self.assertIs(canvas.services.history_service, original_history)
                self.assertIs(
                    canvas.runtime_state.history_service,
                    original_history,
                )
                self.assertEqual(original_history.state.history, [])
                self.assertEqual(original_history.state.redo_stack, [])
                self.assertEqual(replacement_history.state.history, [])
                self.assertTrue(
                    all(
                        canvas.model.atoms[atom_id].color == "#000000"
                        for atom_id in atom_ids
                    )
                )

    def test_actual_qt_history_injected_absent_policy_is_rejected(self) -> None:
        class InjectingHistory:
            def __init__(self, policy_name: str, injected_value: object) -> None:
                self.state = SimpleNamespace(history=[], redo_stack=[])
                self.policy_name = policy_name
                self.injected_value = injected_value

            def is_enabled(self) -> bool:
                return bool(getattr(self.state, "enabled", True))

            def set_enabled(self, enabled: bool) -> None:
                self.state.enabled = enabled

            def push(self, command) -> bool:
                self.state.history.append(command)
                self.state.redo_stack.clear()
                setattr(
                    self.state,
                    self.policy_name,
                    self.injected_value,
                )
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        for policy_name, injected_value in (
            ("enabled", False),
            ("limit", 0),
        ):
            with self.subTest(policy=policy_name):
                canvas = CanvasView()
                self.addCleanup(self._dispose_canvas, canvas)
                atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
                    "C",
                    0.0,
                    0.0,
                )
                item = atom_dots_for(canvas)[atom_id]
                history = InjectingHistory(policy_name, injected_value)
                service = CanvasColorMutationService(
                    canvas,
                    graph_service=SimpleNamespace(
                        bond_sets_for_atoms=lambda _atom_ids: (set(), set())
                    ),
                    history_service=history,
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    rf"raw history policy '{policy_name}' changed",
                ):
                    service.apply_color_to_item(item, QColor("#ff0000"))

                self.assertEqual(canvas.model.atoms[atom_id].color, "#000000")
                self.assertEqual(history.state.history, [])
                self.assertEqual(history.state.redo_stack, [])
                self.assertFalse(hasattr(history.state, policy_name))
                self.assertFalse(hasattr(history.state, f"_{policy_name}"))

    def test_actual_qt_history_publication_runs_after_runtime_rollback_and_reasserts(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom = canvas.model.atoms[atom_id]
        atom_item = atom_dots_for(canvas)[atom_id]
        before_color = atom.color
        history = canvas.services.history_service
        history_list = history.state.history
        redo_list = history.state.redo_stack
        history_entry = object()
        redo_entry = object()
        history_list.append(history_entry)
        redo_list.append(redo_entry)
        published_colors: list[str | None] = []

        def corrupt_after_publication() -> None:
            published_colors.append(atom.color)
            atom.color = "#abcdef"
            history_list.append(object())

        history.set_change_callback(corrupt_after_publication)
        primary = KeyboardInterrupt("color history push interrupted")

        def append_then_fail(command) -> None:
            history_list.append(command)
            redo_list.clear()
            raise primary

        with (
            mock.patch.object(history, "push", side_effect=append_then_fail),
            self.assertRaises(KeyboardInterrupt) as caught,
        ):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                atom_item,
                QColor("#123456"),
            )

        self.assertIs(caught.exception, primary)
        self.assertEqual(published_colors, [before_color])
        self.assertEqual(atom.color, before_color)
        self.assertEqual(history_list, [history_entry])
        self.assertEqual(redo_list, [redo_entry])
        history.set_change_callback(None)

    def test_failed_color_push_reasserts_policy_after_rollback_notification(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        original_brush = QBrush(QColor("#101010"))
        QGraphicsPathItem.setBrush(shape, original_brush)
        canvas.scene().addItem(shape)
        history_entry = object()
        redo_entry = object()
        state = CanvasHistoryState(
            history=[history_entry],
            redo_stack=[redo_entry],
        )
        primary = RuntimeError("color history push failed")

        class History:
            def __init__(self) -> None:
                self.state = state
                self.notification_calls = 0

            def is_enabled(self) -> bool:
                return bool(self.state.enabled)

            def set_enabled(self, enabled: bool) -> None:
                self.state.enabled = bool(enabled)

            def push(self, command) -> bool:
                self.state.history.append(command)
                self.state.redo_stack.clear()
                raise primary

            def notify_change(self) -> None:
                self.notification_calls += 1
                self.state.enabled = False
                self.state.limit = 1

        history = History()
        canvas.services.canvas_color_mutation_service.history = history

        with self.assertRaises(RuntimeError) as caught:
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                shape,
                QColor("#2f6ed3"),
            )

        self.assertIs(caught.exception, primary)
        self.assertEqual(history.notification_calls, 1)
        self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)
        self.assertEqual(state.history, [history_entry])
        self.assertEqual(state.redo_stack, [redo_entry])
        self.assertTrue(state.enabled)
        self.assertEqual(state.limit, 100)

    def test_noop_color_batch_rechecks_runtime_after_live_history_verifier(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        service = canvas.services.canvas_color_mutation_service
        color = QColor("#2f6ed3")
        original_brush = QBrush(
            service._pastel_fill(color, service.SHAPE_FILL_TINT)
        )
        poisoned_brush = QBrush(QColor("#ff00ff"))
        history_holder: dict[str, object] = {}

        class NoopShape(QGraphicsPathItem):
            def setBrush(self, brush) -> None:
                QGraphicsPathItem.setBrush(self, brush)
                history = history_holder.get("history")
                if history is not None:
                    object.__setattr__(history, "armed", True)

        shape = NoopShape()
        shape.setData(0, "shape")
        QGraphicsPathItem.setBrush(shape, original_brush)
        canvas.scene().addItem(shape)
        state = CanvasHistoryState()

        class History:
            def __init__(self) -> None:
                object.__setattr__(self, "state", state)
                object.__setattr__(self, "armed", False)
                object.__setattr__(self, "poison_calls", 0)

            def __getattribute__(self, name):
                if name == "state":
                    namespace = object.__getattribute__(self, "__dict__")
                    if dict.get(namespace, "armed", False):
                        namespace["armed"] = False
                        namespace["poison_calls"] += 1
                        QGraphicsPathItem.setBrush(shape, poisoned_brush)
                    return namespace["state"]
                return object.__getattribute__(self, name)

            @staticmethod
            def push(_command) -> bool:
                raise AssertionError("a no-op color batch must not publish history")

        history = History()
        history_holder["history"] = history
        service.history = history

        with self.assertRaisesRegex(
            RuntimeError,
            "graphics brush did not match its savepoint",
        ):
            service.apply_color_to_items([shape], color)

        self.assertEqual(history.poison_calls, 1)
        self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_successful_history_observer_cannot_rewrite_published_atom_color(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom = canvas.model.atoms[atom_id]
        atom_item = atom_dots_for(canvas)[atom_id]
        before_color = atom.color
        history = canvas.services.history_service
        history_items = tuple(history.state.history)
        redo_items = tuple(history.state.redo_stack)
        published_colors: list[str | None] = []

        def rewrite_published_runtime() -> None:
            published_colors.append(atom.color)
            atom.color = "#abcdef"

        history.set_change_callback(rewrite_published_runtime)

        with self.assertRaisesRegex(
            RuntimeError,
            "atom color changed after history publication",
        ):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                atom_item,
                QColor("#123456"),
            )

        self.assertEqual(published_colors, ["#123456", before_color])
        self.assertEqual(atom.color, before_color)
        self.assertEqual(tuple(history.state.history), history_items)
        self.assertEqual(tuple(history.state.redo_stack), redo_items)
        history.set_change_callback(None)

    def test_successful_history_observer_cannot_rewrite_color_command_payload(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        atom_id = canvas.services.canvas_atom_mutation_service.add_atom(
            "C",
            0.0,
            0.0,
        )
        atom = canvas.model.atoms[atom_id]
        atom_item = atom_dots_for(canvas)[atom_id]
        before_color = atom.color
        history = canvas.services.history_service
        before_history = tuple(history.state.history)
        before_redo = tuple(history.state.redo_stack)
        published: list[UpdateAtomColorCommand] = []

        def rewrite_command() -> None:
            command = history.state.history[-1]
            assert isinstance(command, UpdateAtomColorCommand)
            published.append(command)
            command.after_color = "#abcdef"

        history.set_change_callback(rewrite_command)
        try:
            with self.assertRaisesRegex(RuntimeError, "history command field"):
                canvas.services.canvas_color_mutation_service.apply_color_to_item(
                    atom_item,
                    QColor("#123456"),
                )

            self.assertEqual(atom.color, before_color)
            self.assertEqual(published[0].after_color, "#123456")
            self.assertEqual(tuple(history.state.history), before_history)
            self.assertEqual(tuple(history.state.redo_stack), before_redo)
        finally:
            history.set_change_callback(None)

    def test_history_restore_setter_cannot_poison_final_qt_color_runtime(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        before_brush = QBrush(QColor("#101010"))
        QGraphicsPathItem.setBrush(shape, before_brush)
        canvas.scene().addItem(shape)
        history_entry = object()
        redo_entry = object()

        class PoisoningHistoryState:
            def __init__(self) -> None:
                object.__setattr__(self, "armed", False)
                object.__setattr__(self, "history", [history_entry])
                object.__setattr__(self, "redo_stack", [redo_entry])

            def __setattr__(self, name, value) -> None:
                object.__setattr__(self, name, value)
                if name in {"history", "redo_stack"} and object.__getattribute__(
                    self,
                    "armed",
                ):
                    QGraphicsPathItem.setBrush(
                        shape,
                        QBrush(QColor("#ff00ff")),
                    )

        primary = KeyboardInterrupt("color history push interrupted")
        state = PoisoningHistoryState()

        class PoisoningHistoryService:
            def __init__(self) -> None:
                self.state = state

            def push(self, command) -> None:
                state.history.append(command)
                state.redo_stack.clear()
                state.armed = True
                raise primary

            def notify_change(self) -> None:
                return None

        service = canvas.services.canvas_color_mutation_service
        service.history = PoisoningHistoryService()

        with self.assertRaises(KeyboardInterrupt) as caught:
            service.apply_color_to_item(shape, QColor("#2f6ed3"))

        self.assertIs(caught.exception, primary)
        self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
        self.assertEqual(state.history, [history_entry])
        self.assertEqual(state.redo_stack, [redo_entry])

    def test_batch_exact_rollback_uses_qt_base_pen_getters(self) -> None:
        first = QGraphicsPathItem()
        first.setData(0, "shape")
        first_pen = QPen(QColor("#101010"))
        QGraphicsPathItem.setPen(first, first_pen)

        class PoisoningPenItem(QGraphicsPathItem):
            armed = False
            override_reads = 0

            def pen(self):
                self.override_reads += 1
                value = super().pen()
                if self.armed:
                    QGraphicsPathItem.setPen(first, QPen(QColor("#ff00ff")))
                return value

        second = PoisoningPenItem()
        second.setData(0, "shape")
        second_pen = QPen(QColor("#202020"))
        QGraphicsPathItem.setPen(second, second_pen)
        service = CanvasColorMutationService(
            SimpleNamespace(),
            graph_service=SimpleNamespace(),
            history_service=None,
        )
        rollback = service._batch_runtime_rollback(
            [first, second],
            expand_ring_structures=False,
        )
        assert rollback is not None
        QGraphicsPathItem.setPen(first, QPen(QColor("#1111ff")))
        QGraphicsPathItem.setPen(second, QPen(QColor("#1111ff")))
        second.armed = True

        rollback()

        self.assertEqual(QGraphicsPathItem.pen(first), first_pen)
        self.assertEqual(QGraphicsPathItem.pen(second), second_pen)
        self.assertEqual(second.override_reads, 1)

    def test_false_history_push_is_allowed_only_when_history_is_disabled(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        canvas.scene().addItem(shape)
        service = canvas.services.canvas_color_mutation_service
        history = canvas.services.history_service
        before = QBrush(QGraphicsPathItem.brush(shape))

        with mock.patch.object(history, "push", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "push was rejected"):
                service.apply_color_to_item(shape, QColor("#2f6ed3"))
        self.assertEqual(QGraphicsPathItem.brush(shape), before)

        history.set_enabled(False)
        service.apply_color_to_item(shape, QColor("#2f6ed3"))
        self.assertNotEqual(QGraphicsPathItem.brush(shape), before)
        self.assertFalse(history.can_undo())

        # The decision is frozen before push. A rejected implementation cannot
        # disable history as a side effect and thereby legitimize its own False.
        history.set_enabled(True)
        accepted_brush = QBrush(QGraphicsPathItem.brush(shape))

        def disable_then_reject(_command) -> bool:
            history.set_enabled(False)
            return False

        with mock.patch.object(history, "push", side_effect=disable_then_reject):
            with self.assertRaisesRegex(RuntimeError, "push was rejected"):
                service.apply_color_to_item(shape, QColor("#d84a3a"))
        self.assertEqual(QGraphicsPathItem.brush(shape), accepted_brush)
        self.assertTrue(history.is_enabled())
        self.assertFalse(history.can_undo())

    def test_apply_color_and_fill_helpers_cover_bond_atom_ring_and_commands(
        self,
    ) -> None:
        scene = QGraphicsScene()

        bond_item = QGraphicsPathItem()
        bond_item.setData(0, "bond")
        bond_item.setData(1, 0)
        scene.addItem(bond_item)
        bond_pushes = []
        bond_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1, color="#000000")]),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="smiles"),
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            services=SimpleNamespace(
                history_service=_history_service(bond_pushes.append)
            ),
        )
        set_bond_items_for(bond_canvas, {0: [bond_item]})
        _color_service_for(bond_canvas).apply_color_to_item(
            bond_item, QColor("#ff0000")
        )
        self.assertEqual(bond_canvas.model.bonds[0].color, "#ff0000")
        self.assertEqual(bond_item.pen().color().name(), "#ff0000")
        self.assertIsInstance(bond_pushes.pop(), UpdateBondColorCommand)

        atom_item = QGraphicsTextItem("O")
        atom_item.setData(0, "atom")
        atom_item.setData(1, 7)
        scene.addItem(atom_item)
        dot_item = mock.Mock()
        atom_pushes = []
        atom_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            services=SimpleNamespace(
                history_service=_history_service(atom_pushes.append),
                atom_label_service=SimpleNamespace(
                    implicit_carbon_dot_brush=mock.Mock(return_value="dot-brush")
                ),
            ),
        )
        _set_atom_graphics(atom_canvas, {7: atom_item}, {7: dot_item})
        _color_service_for(atom_canvas).apply_color_to_item(
            atom_item, QColor("#00aa00")
        )
        self.assertEqual(atom_canvas.model.atoms[7].color, "#00aa00")
        self.assertEqual(atom_item.defaultTextColor().name(), "#00aa00")
        dot_item.setBrush.assert_called_once_with("dot-brush")
        self.assertIsInstance(atom_pushes.pop(), UpdateAtomColorCommand)

        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)
        recurse_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}
            ),
            services=SimpleNamespace(
                history_service=_history_service(),
            ),
        )
        graph_service = SimpleNamespace(
            bond_sets_for_atoms=mock.Mock(return_value=({3}, set()))
        )
        _set_atom_graphics(recurse_canvas, {1: object()}, {2: object()})
        set_bond_items_for(recurse_canvas, {3: [object()]})
        recurse_service = _color_service_for(
            recurse_canvas, graph_service=graph_service
        )
        recurse_service.apply_color_to_item = mock.Mock()
        recurse_service._apply_ring_structure_color(ring_item, QColor("#336699"))
        graph_service.bond_sets_for_atoms.assert_called_once_with({1, 2})
        self.assertEqual(
            recurse_service.apply_color_to_item.call_args_list,
            [
                mock.call(atom_items_for(recurse_canvas)[1], QColor("#336699")),
                mock.call(atom_dots_for(recurse_canvas)[2], QColor("#336699")),
                mock.call(bond_items_for(recurse_canvas)[3][0], QColor("#336699")),
            ],
        )

        fill_pushes = []
        fill_canvas = SimpleNamespace(
            services=SimpleNamespace(
                history_service=_history_service(fill_pushes.append)
            ),
        )
        _color_service_for(fill_canvas).apply_ring_fill_color(
            ring_item, QColor("#123456"), alpha=2.0
        )
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 1.0)
        self.assertIsInstance(fill_pushes.pop(), UpdateSceneItemCommand)

        _color_service_for(atom_canvas).apply_color_to_item(None, QColor("#ffffff"))
        _color_service_for(fill_canvas).apply_ring_fill_color(None, QColor("#ffffff"))

    def test_coloring_a_ring_pushes_a_single_composite_command(self) -> None:
        scene = QGraphicsScene()
        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)

        label_a = QGraphicsTextItem("C")
        label_a.setData(0, "atom")
        label_a.setData(1, 1)
        scene.addItem(label_a)
        label_b = QGraphicsTextItem("O")
        label_b.setData(0, "atom")
        label_b.setData(1, 2)
        scene.addItem(label_b)
        bond_item = QGraphicsPathItem()
        bond_item.setData(0, "bond")
        bond_item.setData(1, 0)
        scene.addItem(bond_item)

        pushes: list = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)},
                bonds=[Bond(1, 2, 1, color="#000000")],
            ),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input=None),
            services=SimpleNamespace(
                history_service=_history_service(pushes.append),
                atom_label_service=SimpleNamespace(
                    implicit_carbon_dot_brush=mock.Mock(return_value=QBrush())
                ),
            ),
        )
        _set_atom_graphics(canvas, {1: label_a, 2: label_b})
        set_bond_items_for(canvas, {0: [bond_item]})
        graph_service = SimpleNamespace(
            bond_sets_for_atoms=mock.Mock(return_value=({0}, set()))
        )
        service = _color_service_for(canvas, graph_service=graph_service)

        service.apply_color_to_item(ring_item, QColor("#ff8800"))

        # One ring click == one undo step, even though it touches every atom and bond.
        self.assertEqual(len(pushes), 1)
        composite = pushes[0]
        self.assertIsInstance(composite, CompositeCommand)
        self.assertEqual(len(composite.commands), 3)
        # History service is restored after the bundled mutation.
        self.assertIs(service.history, canvas.services.history_service)

    def test_apply_color_to_items_pushes_one_command_for_multiple_selected_items(
        self,
    ) -> None:
        scene = QGraphicsScene()
        pushes = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)
        first = QGraphicsPathItem()
        first.setData(0, "shape")
        scene.addItem(first)
        second = QGraphicsPathItem()
        second.setData(0, "shape")
        scene.addItem(second)

        service.apply_color_to_items([first, second], QColor("#2f6ed3"))

        self.assertEqual(len(pushes), 1)
        self.assertIsInstance(pushes[0], CompositeCommand)
        self.assertEqual(len(pushes[0].commands), 2)
        self.assertNotEqual(first.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertNotEqual(second.brush().style(), Qt.BrushStyle.NoBrush)

    def test_live_capture_getter_failure_aborts_before_mutation_and_retry_succeeds(
        self,
    ) -> None:
        class _FailOnceGetterShape(QGraphicsPathItem):
            def __init__(self) -> None:
                super().__init__()
                self.failure_name: str | None = None
                self.failure: BaseException | None = None
                self.mutation_count = 0

            def _fail_if_requested(self, name: str) -> None:
                if self.failure_name != name or self.failure is None:
                    return
                failure = self.failure
                self.failure = None
                raise failure

            def data(self, role: int):
                self._fail_if_requested("data")
                return super().data(role)

            def brush(self):
                self._fail_if_requested("brush")
                return super().brush()

            def pen(self):
                self._fail_if_requested("pen")
                return super().pen()

            def setBrush(self, brush) -> None:
                self.mutation_count += 1
                QGraphicsPathItem.setBrush(self, brush)

        for getter_name in ("data", "brush", "pen"):
            for error_type in (TypeError, RuntimeError):
                with self.subTest(getter=getter_name, error=error_type.__name__):
                    scene = QGraphicsScene()
                    pushes = []
                    canvas = SimpleNamespace(
                        scene=lambda scene=scene: scene,
                        model=SimpleNamespace(atoms={}, bonds=[]),
                        services=SimpleNamespace(
                            history_service=_history_service(pushes.append)
                        ),
                    )
                    _set_atom_graphics(canvas)
                    set_bond_items_for(canvas, {})
                    service = _color_service_for(canvas)
                    shape = _FailOnceGetterShape()
                    shape.setData(0, "shape")
                    scene.addItem(shape)
                    before_brush = QBrush(QGraphicsPathItem.brush(shape))
                    shape.failure_name = getter_name
                    shape.failure = error_type(f"live {getter_name} capture failed")

                    with self.assertRaisesRegex(
                        error_type,
                        f"live {getter_name} capture failed",
                    ):
                        service.apply_color_to_items([shape], QColor("#2f6ed3"))

                    self.assertEqual(shape.mutation_count, 0)
                    self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
                    self.assertEqual(pushes, [])

                    service.apply_color_to_items([shape], QColor("#2f6ed3"))

                    self.assertEqual(shape.mutation_count, 1)
                    self.assertNotEqual(QGraphicsPathItem.brush(shape), before_brush)
                    self.assertEqual(len(pushes), 1)

    def test_batch_capture_failure_unwinds_poisoned_earlier_target_before_retry(
        self,
    ) -> None:
        scene = QGraphicsScene()
        pushes = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)
        first = QGraphicsPathItem()
        first.setData(0, "shape")
        scene.addItem(first)
        first_brush = QBrush(QColor("#123456"))
        poisoned_brush = QBrush(QColor("#ff0000"))
        QGraphicsPathItem.setBrush(first, first_brush)
        primary = KeyboardInterrupt("second capture poisoned first")

        class _PoisoningSecondShape(QGraphicsPathItem):
            armed = True

            def brush(self):
                if self.armed:
                    self.armed = False
                    QGraphicsPathItem.setBrush(first, poisoned_brush)
                    raise primary
                return QGraphicsPathItem.brush(self)

        second = _PoisoningSecondShape()
        second.setData(0, "shape")
        scene.addItem(second)

        with self.assertRaises(KeyboardInterrupt) as raised:
            service.apply_color_to_items([first, second], QColor("#2f6ed3"))

        self.assertIs(raised.exception, primary)
        self.assertEqual(QGraphicsPathItem.brush(first), first_brush)
        self.assertEqual(pushes, [])

        service.apply_color_to_items([first, second], QColor("#2f6ed3"))

        self.assertNotEqual(QGraphicsPathItem.brush(first), first_brush)
        self.assertEqual(len(pushes), 1)

    def test_batch_preflight_getters_cannot_poison_real_history(self) -> None:
        for getter_name in ("data", "brush"):
            with self.subTest(getter=getter_name):
                canvas = CanvasView()
                self.addCleanup(self._dispose_canvas, canvas)
                history = canvas.services.history_service
                sentinel = object()

                def poison_history(
                    _history=history,
                    _sentinel=sentinel,
                ) -> None:
                    _history.state.history.append(_sentinel)

                class _HistoryPoisoningShape(QGraphicsPathItem):
                    armed = True

                    def data(
                        self,
                        role: int,
                        _getter_name=getter_name,
                        _poison=poison_history,
                    ):
                        if _getter_name == "data" and self.armed:
                            self.armed = False
                            _poison()
                        return QGraphicsPathItem.data(self, role)

                    def brush(
                        self,
                        _getter_name=getter_name,
                        _poison=poison_history,
                    ):
                        if _getter_name == "brush" and self.armed:
                            self.armed = False
                            _poison()
                        return QGraphicsPathItem.brush(self)

                shape = _HistoryPoisoningShape()
                shape.setData(0, "shape")
                canvas.scene().addItem(shape)
                before_brush = QBrush(QGraphicsPathItem.brush(shape))

                with self.assertRaisesRegex(
                    RuntimeError,
                    "history stack contents",
                ):
                    canvas.services.canvas_color_mutation_service.apply_color_to_items(
                        [shape],
                        QColor("#2f6ed3"),
                    )

                self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
                self.assertEqual(history.state.history, [])
                self.assertEqual(history.state.redo_stack, [])

    def test_history_capture_getter_cannot_redefine_precolor_runtime(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        original_brush = QBrush(QColor("#123456"))
        poisoned_brush = QBrush(QColor("#ff0000"))
        QGraphicsPathItem.setBrush(shape, original_brush)
        canvas.scene().addItem(shape)
        state = CanvasHistoryState()
        push = mock.Mock()

        class History:
            def __init__(self) -> None:
                self._state = state
                self.armed = True

            @property
            def state(self):
                if self.armed:
                    self.armed = False
                    QGraphicsPathItem.setBrush(shape, poisoned_brush)
                return self._state

            @staticmethod
            def is_enabled() -> bool:
                return True

            def push(self, command) -> bool:
                push(command)
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        canvas.services.canvas_color_mutation_service.history = History()

        with self.assertRaisesRegex(RuntimeError, "did not match its savepoint"):
            canvas.services.canvas_color_mutation_service.apply_color_to_items(
                [shape],
                QColor("#2f6ed3"),
            )

        push.assert_not_called()
        self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_preflight_note_runtime_restore_cannot_be_final_history_writer(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        state = CanvasHistoryState()
        sentinel = object()

        class RollbackPoisoningNote(NoteItem):
            def __init__(self) -> None:
                super().__init__(canvas)
                self.poison_on_restore = False

            def setHtml(self, html: str) -> None:
                super().setHtml(html)
                if self.poison_on_restore:
                    state.history.append(sentinel)

        note = RollbackPoisoningNote()
        note.setPlainText("preflight")
        note.setData(0, "note")
        canvas.scene().addItem(note)
        original_color = QColor(QGraphicsTextItem.defaultTextColor(note))
        push = mock.Mock()

        class History:
            def __init__(self) -> None:
                self._state = state
                self.armed = True

            @property
            def state(self):
                if self.armed:
                    self.armed = False
                    QGraphicsTextItem.setDefaultTextColor(note, QColor("#ff0000"))
                    note.poison_on_restore = True
                return self._state

            @staticmethod
            def is_enabled() -> bool:
                return True

            def push(self, command) -> bool:
                push(command)
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        canvas.services.canvas_color_mutation_service.history = History()

        with self.assertRaisesRegex(RuntimeError, "note color runtime"):
            canvas.services.canvas_color_mutation_service.apply_color_to_items(
                [note],
                QColor("#2f6ed3"),
            )

        push.assert_not_called()
        self.assertEqual(
            QGraphicsTextItem.defaultTextColor(note),
            original_color,
        )
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_mutation_failure_note_restore_cannot_be_final_history_writer(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        history = canvas.services.history_service
        state = history.state
        sentinel = object()
        primary = RuntimeError("color mutation failed")

        class RollbackPoisoningNote(NoteItem):
            def __init__(self) -> None:
                super().__init__(canvas)
                self.poison_on_restore = False

            def setHtml(self, html: str) -> None:
                super().setHtml(html)
                if self.poison_on_restore:
                    state.history.append(sentinel)

        note = RollbackPoisoningNote()
        note.setPlainText("mutation")
        note.setData(0, "note")
        canvas.scene().addItem(note)
        original_color = QColor(QGraphicsTextItem.defaultTextColor(note))
        service = canvas.services.canvas_color_mutation_service

        def fail_mutation(_item, _color) -> None:
            QGraphicsTextItem.setDefaultTextColor(note, QColor("#ff0000"))
            note.poison_on_restore = True
            raise primary

        with (
            mock.patch.object(service, "apply_color_to_item", side_effect=fail_mutation),
            self.assertRaises(RuntimeError) as caught,
        ):
            service.apply_color_to_items([note], QColor("#2f6ed3"))

        self.assertIs(caught.exception, primary)
        self.assertEqual(
            QGraphicsTextItem.defaultTextColor(note),
            original_color,
        )
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_single_color_push_rejects_successful_extra_stack_entry(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        original_brush = QBrush(QColor("#123456"))
        QGraphicsPathItem.setBrush(shape, original_brush)
        canvas.scene().addItem(shape)
        state = CanvasHistoryState()
        sentinel = object()

        class History:
            def __init__(self) -> None:
                self.state = state

            @staticmethod
            def is_enabled() -> bool:
                return True

            @staticmethod
            def push(command) -> bool:
                state.history.extend((command, sentinel))
                state.redo_stack.clear()
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        canvas.services.canvas_color_mutation_service.history = History()

        with self.assertRaisesRegex(RuntimeError, "history stack contents"):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                shape,
                QColor("#2f6ed3"),
            )

        self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_batch_runtime_verifier_cannot_poison_published_history(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        history = canvas.services.history_service
        service = canvas.services.canvas_color_mutation_service
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        canvas.scene().addItem(shape)
        before_brush = QBrush(QGraphicsPathItem.brush(shape))
        sentinel = object()

        def poison_history(*_args, **_kwargs) -> None:
            history.state.history.append(sentinel)

        with (
            mock.patch.object(
                service,
                "_verify_published_color_result",
                side_effect=poison_history,
            ),
            self.assertRaisesRegex(RuntimeError, "history stack contents"),
        ):
            service.apply_color_to_items([shape], QColor("#2f6ed3"))

        self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
        self.assertEqual(history.state.history, [])
        self.assertEqual(history.state.redo_stack, [])

    def test_unsupported_batch_capture_unwinds_poisoned_earlier_target(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        first = QGraphicsPathItem()
        first.setData(0, "shape")
        first_brush = QBrush(QColor("#123456"))
        poisoned_brush = QBrush(QColor("#ff0000"))
        QGraphicsPathItem.setBrush(first, first_brush)
        canvas.scene().addItem(first)

        class _PoisoningUnsupportedItem(QGraphicsPathItem):
            armed = True

            def data(self, role: int):
                if role == 0:
                    if self.armed:
                        self.armed = False
                        QGraphicsPathItem.setBrush(first, poisoned_brush)
                    return "extension"
                return QGraphicsPathItem.data(self, role)

        unsupported = _PoisoningUnsupportedItem()
        canvas.scene().addItem(unsupported)

        canvas.services.canvas_color_mutation_service.apply_color_to_items(
            [first, unsupported],
            QColor("#2f6ed3"),
        )
        self.assertNotEqual(QGraphicsPathItem.brush(first), first_brush)

        canvas.services.history_service.undo()

        self.assertEqual(QGraphicsPathItem.brush(first), first_brush)
        self.assertNotEqual(QGraphicsPathItem.brush(first), poisoned_brush)

    def test_final_history_getter_cannot_poison_single_or_batch_color(self) -> None:
        for operation in ("single", "batch"):
            with self.subTest(operation=operation):
                canvas = CanvasView()
                self.addCleanup(self._dispose_canvas, canvas)
                shape = QGraphicsPathItem()
                shape.setData(0, "shape")
                original_brush = QBrush(QColor("#123456"))
                poisoned_brush = QBrush(QColor("#ff0000"))
                QGraphicsPathItem.setBrush(shape, original_brush)
                canvas.scene().addItem(shape)

                class State:
                    def __init__(self) -> None:
                        self.history = []
                        self.redo_stack = []
                        self.enabled = True
                        self.limit = 100
                        self.armed = False
                        self.reads = 0

                    def __getattribute__(
                        self,
                        name,
                        _shape=shape,
                        _poisoned_brush=poisoned_brush,
                    ):
                        if name == "history":
                            namespace = object.__getattribute__(self, "__dict__")
                            if dict.get(namespace, "armed", False):
                                namespace["reads"] += 1
                                if namespace["reads"] == 13:
                                    QGraphicsPathItem.setBrush(
                                        _shape,
                                        _poisoned_brush,
                                    )
                            return namespace["history"]
                        return object.__getattribute__(self, name)

                state = State()

                class History:
                    def __init__(self, _state=state) -> None:
                        self.state = _state

                    @staticmethod
                    def is_enabled() -> bool:
                        return True

                    @staticmethod
                    def set_enabled(_value: bool) -> None:
                        return None

                    @staticmethod
                    def push(command, _state=state) -> bool:
                        namespace = object.__getattribute__(_state, "__dict__")
                        namespace["history"].append(command)
                        namespace["redo_stack"].clear()
                        namespace["armed"] = True
                        return True

                    @staticmethod
                    def notify_change() -> None:
                        return None

                service = canvas.services.canvas_color_mutation_service
                service.history = History()
                with self.assertRaises(RuntimeError):
                    if operation == "single":
                        service.apply_color_to_item(shape, QColor("#2f6ed3"))
                    else:
                        service.apply_color_to_items([shape], QColor("#2f6ed3"))

                namespace = object.__getattribute__(state, "__dict__")
                self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)
                self.assertEqual(namespace["history"], [])
                self.assertEqual(namespace["redo_stack"], [])

    def test_single_color_capture_getter_cannot_redefine_history_baseline(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        original_brush = QBrush(QColor("#123456"))
        QGraphicsPathItem.setBrush(shape, original_brush)
        canvas.scene().addItem(shape)
        state = CanvasHistoryState()
        sentinel = object()
        push = mock.Mock()

        class History:
            def __init__(self) -> None:
                self.state = state
                self.armed = True

            def __getattribute__(self, name):
                if name == "state":
                    namespace = object.__getattribute__(self, "__dict__")
                    value = namespace["state"]
                    if namespace["armed"]:
                        namespace["armed"] = False
                        value.history.append(sentinel)
                    return value
                return object.__getattribute__(self, name)

            @staticmethod
            def is_enabled() -> bool:
                return True

            @staticmethod
            def set_enabled(_value: bool) -> None:
                return None

            def push(self, command) -> bool:
                push(command)
                state.history.append(command)
                state.redo_stack.clear()
                return True

            @staticmethod
            def notify_change() -> None:
                return None

        canvas.services.canvas_color_mutation_service.history = History()

        with self.assertRaisesRegex(RuntimeError, "raw history stack contents"):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                shape,
                QColor("#2f6ed3"),
            )

        push.assert_not_called()
        self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)
        self.assertEqual(state.history, [])
        self.assertEqual(state.redo_stack, [])

    def test_live_descriptor_attribute_error_aborts_before_color_mutation(
        self,
    ) -> None:
        for getter_name in ("data", "brush", "pen"):
            with self.subTest(getter=getter_name):
                base_getter = getattr(QGraphicsPathItem, getter_name)

                def read_getter(
                    item,
                    *,
                    getter_name=getter_name,
                    base_getter=base_getter,
                ):
                    item.lookup_count += 1
                    if item.lookup_failures:
                        item.lookup_failures -= 1
                        raise AttributeError(f"live {getter_name} descriptor failed")
                    return lambda *args: base_getter(item, *args)

                class _FailOnceDescriptorShape(QGraphicsPathItem):
                    def __init__(self) -> None:
                        super().__init__()
                        self.lookup_count = 0
                        self.lookup_failures = 0
                        self.mutation_count = 0

                    def setBrush(self, brush) -> None:
                        self.mutation_count += 1
                        QGraphicsPathItem.setBrush(self, brush)

                setattr(
                    _FailOnceDescriptorShape,
                    getter_name,
                    property(read_getter),
                )

                scene = QGraphicsScene()
                pushes = []
                canvas = SimpleNamespace(
                    scene=lambda scene=scene: scene,
                    model=SimpleNamespace(atoms={}, bonds=[]),
                    services=SimpleNamespace(
                        history_service=_history_service(pushes.append)
                    ),
                )
                _set_atom_graphics(canvas)
                set_bond_items_for(canvas, {})
                service = _color_service_for(canvas)
                shape = _FailOnceDescriptorShape()
                shape.setData(0, "shape")
                scene.addItem(shape)
                before_brush = QBrush(QGraphicsPathItem.brush(shape))
                shape.lookup_failures = 1

                with self.assertRaises(AttributeError) as raised:
                    service.apply_color_to_items([shape], QColor("#2f6ed3"))

                self.assertIn(getter_name, str(raised.exception))
                self.assertEqual(shape.lookup_count, 1)
                self.assertEqual(shape.mutation_count, 0)
                self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
                self.assertEqual(pushes, [])

                service.apply_color_to_items([shape], QColor("#2f6ed3"))

                self.assertGreaterEqual(shape.lookup_count, 2)
                self.assertEqual(shape.mutation_count, 1)
                self.assertNotEqual(QGraphicsPathItem.brush(shape), before_brush)
                self.assertEqual(len(pushes), 1)

    def test_scene_item_state_capture_failure_restores_preflight_runtime(
        self,
    ) -> None:
        scene = QGraphicsScene()
        original_brush = QBrush(QColor("#123456"))
        poisoned_brush = QBrush(QColor("#ff00ff"))

        class _PoisoningStateCaptureShape(QGraphicsPathItem):
            def __init__(self) -> None:
                super().__init__()
                self.brush_reads = 0

            def brush(self):
                self.brush_reads += 1
                if self.brush_reads == 2:
                    QGraphicsPathItem.setBrush(self, poisoned_brush)
                    raise RuntimeError("shape state capture poisoned runtime")
                return QGraphicsPathItem.brush(self)

        shape = _PoisoningStateCaptureShape()
        shape.setData(0, "shape")
        QGraphicsPathItem.setBrush(shape, original_brush)
        scene.addItem(shape)
        canvas = SimpleNamespace(scene=lambda: scene)
        service = CanvasColorMutationService(
            canvas,
            graph_service=SimpleNamespace(),
            history_service=None,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "shape state capture poisoned runtime",
        ):
            service.apply_color_to_item(shape, QColor("#2f6ed3"))

        self.assertEqual(shape.brush_reads, 2)
        self.assertEqual(QGraphicsPathItem.brush(shape), original_brush)

    def test_retry_then_second_failure_restores_first_shape_exactly(self) -> None:
        class _FirstShape(QGraphicsPathItem):
            brush_failures = 1

            def __init__(self) -> None:
                super().__init__()
                self.mutation_count = 0

            def brush(self):
                if self.brush_failures:
                    self.brush_failures -= 1
                    raise RuntimeError("first shape capture failed once")
                return super().brush()

            def setBrush(self, brush) -> None:
                self.mutation_count += 1
                QGraphicsPathItem.setBrush(self, brush)

        class _SecondShape(QGraphicsPathItem):
            fail_after_set = False

            def __init__(self) -> None:
                super().__init__()
                self.mutation_count = 0

            def setBrush(self, brush) -> None:
                self.mutation_count += 1
                QGraphicsPathItem.setBrush(self, brush)
                if self.fail_after_set:
                    raise SystemExit("second shape mutation terminated")

        scene = QGraphicsScene()
        pushes = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)
        first = _FirstShape()
        second = _SecondShape()
        for shape in (first, second):
            shape.setData(0, "shape")
            scene.addItem(shape)
        first_brush = QBrush(QColor("#123456"))
        first_pen = QPen(QColor("#654321"))
        first_pen.setWidthF(2.75)
        second_brush = QBrush(QColor("#abcdef"))
        QGraphicsPathItem.setBrush(first, first_brush)
        QGraphicsPathItem.setPen(first, first_pen)
        QGraphicsPathItem.setBrush(second, second_brush)

        with self.assertRaisesRegex(RuntimeError, "capture failed once"):
            service.apply_color_to_items([first, second], QColor("#2f6ed3"))

        self.assertEqual(first.mutation_count, 0)
        self.assertEqual(second.mutation_count, 0)
        second.fail_after_set = True

        with self.assertRaisesRegex(SystemExit, "second shape mutation terminated"):
            service.apply_color_to_items([first, second], QColor("#2f6ed3"))

        self.assertEqual(first.mutation_count, 1)
        self.assertEqual(second.mutation_count, 1)
        self.assertEqual(QGraphicsPathItem.brush(first), first_brush)
        self.assertEqual(QGraphicsPathItem.pen(first), first_pen)
        self.assertEqual(QGraphicsPathItem.brush(second), second_brush)
        self.assertEqual(pushes, [])

    def test_color_batch_skips_sip_deleted_item_and_mutates_live_item(self) -> None:
        scene = QGraphicsScene()
        pushes = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)
        deleted = QGraphicsPathItem()
        deleted.setData(0, "shape")
        scene.addItem(deleted)
        scene.removeItem(deleted)
        sip.delete(deleted)
        live = QGraphicsPathItem()
        live.setData(0, "shape")
        scene.addItem(live)

        service.apply_color_to_items([deleted, live], QColor("#2f6ed3"))

        self.assertTrue(sip.isdeleted(deleted))
        self.assertNotEqual(live.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(len(pushes), 1)

    def test_color_batch_rolls_back_prior_items_when_an_intermediate_item_raises(
        self,
    ) -> None:
        pushes = []
        canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        service = _color_service_for(canvas)
        values = {"first": "before", "second": "before"}

        class _ValueCommand:
            def __init__(self, key: str, before: str, after: str) -> None:
                self.key = key
                self.before = before
                self.after = after

            def undo(self, target_canvas) -> None:
                self.assert_canvas(target_canvas)
                values[self.key] = self.before

            def redo(self, target_canvas) -> None:
                self.assert_canvas(target_canvas)
                values[self.key] = self.after

            @staticmethod
            def assert_canvas(target_canvas) -> None:
                if target_canvas is not canvas:
                    raise AssertionError(
                        "transaction rolled back against the wrong canvas"
                    )

        def mutate(item, color) -> None:
            if item == "second":
                raise RuntimeError("injected second-item failure")
            before = values[item]
            values[item] = color.name()
            service.history.push(_ValueCommand(item, before, values[item]))

        service.apply_color_to_item = mock.Mock(side_effect=mutate)

        with self.assertRaisesRegex(RuntimeError, "second-item failure"):
            service.apply_color_to_items(["first", "second"], QColor("#d84a3a"))

        self.assertEqual(values, {"first": "before", "second": "before"})
        self.assertEqual(pushes, [])
        self.assertIs(service.history, canvas.services.history_service)

    def test_color_batch_failure_restores_exact_note_editing_runtime(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        service = canvas.services.canvas_color_mutation_service
        note = QGraphicsTextItem("Hello World")
        note.setData(0, "note")
        canvas.scene().addItem(note)
        cursor = note.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
        note.setTextCursor(cursor)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        before_state = note_state_dict_for(canvas, note)
        before_html = note.toHtml()
        before_cursor = (cursor.anchor(), cursor.position(), cursor.hasSelection())
        before_flags = note.textInteractionFlags()

        failing_item = QGraphicsPathItem()
        failing_item.setData(0, "shape")
        canvas.scene().addItem(failing_item)
        real_apply = service.apply_color_to_item

        def apply_then_fail(item, color) -> None:
            if item is failing_item:
                raise RuntimeError("injected later-item failure")
            real_apply(item, color)

        service.apply_color_to_item = mock.Mock(side_effect=apply_then_fail)

        with self.assertRaisesRegex(RuntimeError, "later-item failure"):
            service.apply_color_to_items([note, failing_item], QColor("#e53935"))

        restored_cursor = note.textCursor()
        self.assertEqual(note_state_dict_for(canvas, note), before_state)
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(
            (
                restored_cursor.anchor(),
                restored_cursor.position(),
                restored_cursor.hasSelection(),
            ),
            before_cursor,
        )
        self.assertEqual(note.textInteractionFlags(), before_flags)
        self.assertFalse(canvas.services.history_service.can_undo())
        del service.apply_color_to_item

    def test_color_batch_failure_preserves_bond_graphics_identity_and_selection(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        atom_a = canvas.services.canvas_atom_mutation_service.add_atom("C", 0.0, 0.0)
        atom_b = canvas.services.canvas_atom_mutation_service.add_atom("C", 40.0, 0.0)
        bond_id = canvas.services.canvas_bond_mutation_service.add_bond(atom_a, atom_b)
        add_bond_graphics_for(canvas, bond_id)
        bond_item = bond_items_for(canvas)[bond_id][0]
        bond_item.setSelected(True)
        before_pen = bond_item.pen()
        before_color = canvas.model.bonds[bond_id].color

        failing_item = QGraphicsPathItem()
        failing_item.setData(0, "shape")
        canvas.scene().addItem(failing_item)
        service = canvas.services.canvas_color_mutation_service
        real_apply = service.apply_color_to_item

        def apply_then_fail(item, color) -> None:
            if item is failing_item:
                raise RuntimeError("injected later-item failure")
            real_apply(item, color)

        service.apply_color_to_item = mock.Mock(side_effect=apply_then_fail)

        with self.assertRaisesRegex(RuntimeError, "later-item failure"):
            service.apply_color_to_items([bond_item, failing_item], QColor("#d84a3a"))

        self.assertIs(bond_items_for(canvas)[bond_id][0], bond_item)
        self.assertIs(bond_item.scene(), canvas.scene())
        self.assertTrue(bond_item.isSelected())
        self.assertEqual(bond_item.pen(), before_pen)
        self.assertEqual(canvas.model.bonds[bond_id].color, before_color)
        self.assertFalse(canvas.services.history_service.can_undo())
        del service.apply_color_to_item

        # Successful history playback is also color-only: it must not rebuild
        # topology graphics or discard their selection state.
        service.apply_color_to_item(bond_item, QColor("#d84a3a"))
        self.assertIs(bond_items_for(canvas)[bond_id][0], bond_item)
        self.assertTrue(bond_item.isSelected())

        canvas.services.history_service.undo()
        self.assertIs(bond_items_for(canvas)[bond_id][0], bond_item)
        self.assertIs(bond_item.scene(), canvas.scene())
        self.assertTrue(bond_item.isSelected())
        self.assertEqual(canvas.model.bonds[bond_id].color, before_color)
        self.assertEqual(bond_item.pen(), before_pen)

        canvas.services.history_service.redo()
        self.assertIs(bond_items_for(canvas)[bond_id][0], bond_item)
        self.assertIs(bond_item.scene(), canvas.scene())
        self.assertTrue(bond_item.isSelected())
        self.assertEqual(canvas.model.bonds[bond_id].color, "#d84a3a")
        self.assertEqual(bond_item.pen().color().name(), "#d84a3a")

    def test_color_batch_restores_history_stacks_when_push_mutates_then_raises(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        service = canvas.services.canvas_color_mutation_service
        shapes = []
        for offset in (0.0, 20.0):
            shape = QGraphicsPathItem()
            shape.setData(0, "shape")
            shape.setPos(offset, 0.0)
            canvas.scene().addItem(shape)
            shapes.append(shape)

        history_service = canvas.services.history_service
        state = history_service.state
        old_history_entry = object()
        old_redo_entry = object()
        state.history.append(old_history_entry)
        state.redo_stack.append(old_redo_entry)
        history_list = state.history
        redo_list = state.redo_stack

        def append_then_raise(command) -> None:
            state.history.append(command)
            state.redo_stack.clear()
            raise RuntimeError("injected post-append failure")

        history_service.push = append_then_raise

        with self.assertRaisesRegex(RuntimeError, "post-append failure"):
            service.apply_color_to_items(shapes, QColor("#2f6ed3"))

        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(state.history, [old_history_entry])
        self.assertEqual(state.redo_stack, [old_redo_entry])
        self.assertTrue(
            all(shape.brush().style() == Qt.BrushStyle.NoBrush for shape in shapes)
        )
        del history_service.push

    def test_direct_color_restores_history_stacks_when_push_mutates_then_raises(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        service = canvas.services.canvas_color_mutation_service
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        canvas.scene().addItem(shape)
        history_service = canvas.services.history_service
        state = history_service.state
        old_history_entry = object()
        old_redo_entry = object()
        state.history.append(old_history_entry)
        state.redo_stack.append(old_redo_entry)
        history_list = state.history
        redo_list = state.redo_stack

        def append_then_raise(command) -> None:
            state.history.append(command)
            state.redo_stack.clear()
            raise RuntimeError("injected post-append failure")

        history_service.push = append_then_raise

        with self.assertRaisesRegex(RuntimeError, "post-append failure"):
            service.apply_color_to_item(shape, QColor("#2f6ed3"))

        self.assertIs(state.history, history_list)
        self.assertIs(state.redo_stack, redo_list)
        self.assertEqual(state.history, [old_history_entry])
        self.assertEqual(state.redo_stack, [old_redo_entry])
        self.assertEqual(shape.brush().style(), Qt.BrushStyle.NoBrush)
        del history_service.push

    def test_color_history_descriptor_capture_and_control_flow_retry(self) -> None:
        cases = (
            ("state", KeyboardInterrupt),
            ("history", SystemExit),
            ("redo_stack", KeyboardInterrupt),
        )
        for fail_field, error_type in cases:
            with self.subTest(field=fail_field, error=error_type.__name__):
                scene = QGraphicsScene()
                old_history_entry = object()
                old_redo_entry = object()
                history = [old_history_entry]
                redo_stack = [old_redo_entry]
                history_service = _FailOnceHistoryService(
                    fail_field,
                    history,
                    redo_stack,
                )
                canvas = SimpleNamespace(
                    scene=lambda scene=scene: scene,
                    model=SimpleNamespace(atoms={}, bonds=[]),
                    services=SimpleNamespace(history_service=history_service),
                )
                _set_atom_graphics(canvas)
                set_bond_items_for(canvas, {})
                service = _color_service_for(canvas)
                shape = QGraphicsPathItem()
                shape.setData(0, "shape")
                before_brush = QBrush(QColor("#123456"))
                QGraphicsPathItem.setBrush(shape, before_brush)
                scene.addItem(shape)

                with self.assertRaisesRegex(
                    AttributeError,
                    f"{fail_field} capture failed",
                ):
                    service.apply_color_to_item(shape, QColor("#2f6ed3"))

                self.assertEqual(history_service.push_calls, 0)
                self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
                self.assertIs(history_service._state._history, history)
                self.assertIs(history_service._state._redo_stack, redo_stack)
                self.assertEqual(history, [old_history_entry])
                self.assertEqual(redo_stack, [old_redo_entry])

                primary_error = error_type("color history push interrupted")
                history_service.push_error = primary_error
                with self.assertRaises(error_type) as raised:
                    service.apply_color_to_item(shape, QColor("#2f6ed3"))

                self.assertIs(raised.exception, primary_error)
                self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
                self.assertIs(history_service._state._history, history)
                self.assertIs(history_service._state._redo_stack, redo_stack)
                self.assertEqual(history, [old_history_entry])
                self.assertEqual(redo_stack, [old_redo_entry])

                service.apply_color_to_item(shape, QColor("#2f6ed3"))

                self.assertNotEqual(QGraphicsPathItem.brush(shape), before_brush)
                self.assertEqual(len(history), 2)
                self.assertEqual(redo_stack, [])

    def test_color_batch_history_capture_failure_restores_runtime_before_retry(
        self,
    ) -> None:
        scene = QGraphicsScene()
        old_history_entry = object()
        old_redo_entry = object()
        history = [old_history_entry]
        redo_stack = [old_redo_entry]
        history_service = _FailOnceHistoryService(
            "state",
            history,
            redo_stack,
        )
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=history_service),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)
        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        before_brush = QBrush(QColor("#123456"))
        QGraphicsPathItem.setBrush(shape, before_brush)
        scene.addItem(shape)

        with self.assertRaisesRegex(AttributeError, "state capture failed"):
            service.apply_color_to_items([shape], QColor("#2f6ed3"))

        self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
        self.assertEqual(history_service.push_calls, 0)
        self.assertEqual(history, [old_history_entry])
        self.assertEqual(redo_stack, [old_redo_entry])

        primary_error = SystemExit("batch history push terminated")
        history_service.push_error = primary_error
        with self.assertRaises(SystemExit) as raised:
            service.apply_color_to_items([shape], QColor("#2f6ed3"))

        self.assertIs(raised.exception, primary_error)
        self.assertEqual(QGraphicsPathItem.brush(shape), before_brush)
        self.assertIs(history_service._state._history, history)
        self.assertIs(history_service._state._redo_stack, redo_stack)
        self.assertEqual(history, [old_history_entry])
        self.assertEqual(redo_stack, [old_redo_entry])

        service.apply_color_to_items([shape], QColor("#2f6ed3"))

        self.assertNotEqual(QGraphicsPathItem.brush(shape), before_brush)
        self.assertEqual(len(history), 2)
        self.assertEqual(redo_stack, [])

    def test_apply_color_to_item_washes_shape_fill_and_records_history(self) -> None:
        scene = QGraphicsScene()
        pushes: list = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        shape = QGraphicsPathItem()
        shape.setData(0, "shape")
        scene.addItem(shape)

        picked = QColor("#d84a3a")
        service.apply_color_to_item(shape, picked)

        # Shapes are background panels: the picked colour is diluted toward the
        # white sheet and applied opaque, so molecules on top stay readable and
        # nothing shows through the panel.
        fill = shape.brush().color()
        tint = CanvasColorMutationService.SHAPE_FILL_TINT
        self.assertEqual(fill.alphaF(), 1.0)
        self.assertEqual(fill.red(), round(255 - (255 - picked.red()) * tint))
        self.assertEqual(fill.green(), round(255 - (255 - picked.green()) * tint))
        self.assertEqual(fill.blue(), round(255 - (255 - picked.blue()) * tint))
        self.assertEqual(len(pushes), 1)
        self.assertIsInstance(pushes[0], UpdateSceneItemCommand)

    def test_apply_ring_fill_color_applies_opaque_pastel(self) -> None:
        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        pushes: list = []
        canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        service = _color_service_for(canvas)

        picked = QColor("#d84a3a")
        service.apply_ring_fill_color(ring_item, picked)

        fill = ring_item.brush().color()
        self.assertEqual(fill.alphaF(), 1.0)
        self.assertEqual(fill.red(), round(255 - (255 - picked.red()) * 0.25))
        self.assertEqual(fill.green(), round(255 - (255 - picked.green()) * 0.25))
        self.assertEqual(fill.blue(), round(255 - (255 - picked.blue()) * 0.25))
        self.assertEqual(len(pushes), 1)
        self.assertIsInstance(pushes[0], UpdateSceneItemCommand)

    def test_apply_ring_fill_color_to_items_pushes_one_command(self) -> None:
        rings = [
            QGraphicsPolygonItem(
                QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
            ),
            QGraphicsPolygonItem(
                QPolygonF([QPointF(2.0, 0.0), QPointF(3.0, 0.0), QPointF(2.0, 1.0)])
            ),
        ]
        for ring in rings:
            ring.setData(0, "ring")
        pushes = []
        canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        service = _color_service_for(canvas)

        service.apply_ring_fill_color_to_items(rings, QColor("#f4d06f"))

        self.assertEqual(len(pushes), 1)
        self.assertIsInstance(pushes[0], CompositeCommand)
        self.assertEqual(len(pushes[0].commands), 2)
        self.assertTrue(all(ring.brush().color().alphaF() == 1.0 for ring in rings))

    def test_ring_fill_batch_rolls_back_current_item_after_mutation_then_exception(
        self,
    ) -> None:
        class _FailingRing(QGraphicsPolygonItem):
            fail_after_set = False

            def setBrush(self, brush) -> None:
                QGraphicsPolygonItem.setBrush(self, brush)
                if self.fail_after_set:
                    raise RuntimeError("injected failure after brush mutation")

        first = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        second = _FailingRing(
            QPolygonF([QPointF(2.0, 0.0), QPointF(3.0, 0.0), QPointF(2.0, 1.0)])
        )
        for ring in (first, second):
            ring.setData(0, "ring")

        def restore_scene_item(item, state) -> None:
            color_name = state.get("color")
            if color_name is None:
                brush = QBrush()
            else:
                color = QColor(color_name)
                color.setAlphaF(float(state.get("alpha", 0.0)))
                brush = QBrush(color)
            # Bypass the injected override: this is the canonical history restore
            # port, whose job is to reinstate the captured state.
            QGraphicsPolygonItem.setBrush(item, brush)

        pushes = []
        history_service = _history_service(pushes.append)
        canvas = SimpleNamespace(
            services=SimpleNamespace(
                history_service=history_service,
                scene_item_controller=SimpleNamespace(
                    apply_scene_item_state=restore_scene_item
                ),
            ),
        )
        service = _color_service_for(canvas)
        second.fail_after_set = True

        with self.assertRaisesRegex(RuntimeError, "after brush mutation"):
            service.apply_ring_fill_color_to_items([first, second], QColor("#f4d06f"))

        self.assertEqual(first.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(second.brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(pushes, [])
        self.assertIs(service.history, history_service)

    def test_apply_color_to_item_colors_note_text_and_records_history(self) -> None:
        scene = QGraphicsScene()
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            push_command=push_command,
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        note = QGraphicsTextItem("memo")
        note.setData(0, "note")
        scene.addItem(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())

        service.apply_color_to_item(note, QColor("#cc3344"))

        self.assertEqual(note.defaultTextColor().name(), "#cc3344")
        self.assertIn("#cc3344", note.toHtml())
        self.assertEqual(push_command.call_count, 1)
        self.assertIsInstance(push_command.call_args.args[0], UpdateNoteColorCommand)

    def test_apply_color_to_note_recolors_only_selected_text(self) -> None:
        scene = QGraphicsScene()
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            push_command=push_command,
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        note = QGraphicsTextItem("Hello World")
        note.setData(0, "note")
        scene.addItem(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())
        cursor = note.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
        note.setTextCursor(cursor)

        service.apply_color_to_item(note, QColor("#e53935"))

        html = note.toHtml().lower()
        # The colour lands on the selected word only, not the whole-document default.
        self.assertIn("e53935", html)
        self.assertNotEqual(note.defaultTextColor().name().lower(), "#e53935")
        self.assertTrue(note.textCursor().hasSelection())
        self.assertEqual(push_command.call_count, 1)

    def test_note_color_undo_redo_preserves_exact_editing_runtime(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        note = QGraphicsTextItem("Hello World")
        note.setData(0, "note")
        canvas.scene().addItem(note)
        cursor = note.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
        note.setTextCursor(cursor)
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        before_state = note_state_dict_for(canvas, note)
        before_html = note.toHtml()
        before_cursor = (cursor.anchor(), cursor.position(), cursor.hasSelection())
        before_flags = note.textInteractionFlags()

        canvas.services.canvas_color_mutation_service.apply_color_to_item(
            note,
            QColor("#e53935"),
        )

        after_state = note_state_dict_for(canvas, note)
        after_html = note.toHtml()
        after_cursor = note.textCursor()
        self.assertNotEqual(after_state, before_state)
        self.assertEqual(
            (
                after_cursor.anchor(),
                after_cursor.position(),
                after_cursor.hasSelection(),
            ),
            before_cursor,
        )
        self.assertEqual(note.textInteractionFlags(), before_flags)
        self.assertIsInstance(
            canvas.services.history_service.state.history[-1],
            UpdateNoteColorCommand,
        )

        canvas.services.history_service.undo()

        undone_cursor = note.textCursor()
        self.assertEqual(note_state_dict_for(canvas, note), before_state)
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(
            (
                undone_cursor.anchor(),
                undone_cursor.position(),
                undone_cursor.hasSelection(),
            ),
            before_cursor,
        )
        self.assertEqual(note.textInteractionFlags(), before_flags)

        canvas.services.history_service.redo()

        redone_cursor = note.textCursor()
        self.assertEqual(note_state_dict_for(canvas, note), after_state)
        self.assertEqual(note.toHtml(), after_html)
        self.assertEqual(
            (
                redone_cursor.anchor(),
                redone_cursor.position(),
                redone_cursor.hasSelection(),
            ),
            before_cursor,
        )
        self.assertEqual(note.textInteractionFlags(), before_flags)

    def test_committed_note_color_is_not_recorded_again_on_focus_out(self) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        canvas.services.scene_item_controller.attach_scene_item(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())
        before_html = note.toHtml()

        canvas.services.canvas_color_mutation_service.apply_color_to_item(
            note,
            QColor("#cc3344"),
        )

        history = canvas.services.history_service.state.history
        self.assertEqual(len(history), 1)
        self.assertIsInstance(history[0], UpdateNoteColorCommand)
        self.assertEqual(committed_note_html_for(note), note.toHtml())
        after_html = note.toHtml()

        canvas.services.note_controller.handle_note_focus_out(note)

        self.assertEqual(len(history), 1)
        self.assertIsInstance(history[0], UpdateNoteColorCommand)

        canvas.services.history_service.undo()
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(committed_note_html_for(note), before_html)

        canvas.services.history_service.redo()
        self.assertEqual(note.toHtml(), after_html)
        self.assertEqual(committed_note_html_for(note), after_html)

    def test_pending_note_edit_and_color_have_linear_history_and_synced_baselines(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("old")
        canvas.services.scene_item_controller.attach_scene_item(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())
        initial_html = note.toHtml()

        note.setPlainText("old typed")
        pending_html = note.toHtml()
        canvas.services.canvas_color_mutation_service.apply_color_to_item(
            note,
            QColor("#cc3344"),
        )

        history = canvas.services.history_service.state.history
        self.assertEqual(len(history), 2)
        self.assertIsInstance(history[-1], UpdateNoteColorCommand)
        final_html = note.toHtml()
        self.assertIn("#cc3344", final_html.lower())
        self.assertEqual(committed_note_text_for(note), "old typed")
        self.assertEqual(committed_note_html_for(note), final_html)

        canvas.services.note_controller.handle_note_focus_out(note)
        self.assertEqual(len(history), 2)

        canvas.services.history_service.undo()
        self.assertEqual(note.toPlainText(), "old typed")
        self.assertEqual(note.toHtml(), pending_html)
        self.assertEqual(committed_note_html_for(note), pending_html)

        canvas.services.history_service.undo()
        self.assertEqual(note.toPlainText(), "old")
        self.assertEqual(note.toHtml(), initial_html)
        self.assertEqual(committed_note_text_for(note), "old")
        self.assertEqual(committed_note_html_for(note), initial_html)

        canvas.services.history_service.redo()
        self.assertEqual(note.toPlainText(), "old typed")
        self.assertEqual(note.toHtml(), pending_html)
        self.assertEqual(committed_note_html_for(note), pending_html)

        canvas.services.history_service.redo()
        self.assertEqual(note.toPlainText(), "old typed")
        self.assertEqual(note.toHtml(), final_html)
        self.assertEqual(committed_note_text_for(note), "old typed")
        self.assertEqual(committed_note_html_for(note), final_html)

        canvas.services.note_controller.handle_note_focus_out(note)
        self.assertEqual(len(history), 2)

    def test_pending_note_color_second_push_failure_restores_runtime_and_both_stacks(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("old")
        canvas.services.scene_item_controller.attach_scene_item(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())
        note.setPlainText("old typed")

        before_html = note.toHtml()
        before_default_color = note.defaultTextColor()
        before_committed_text = committed_note_text_for(note)
        before_committed_html = committed_note_html_for(note)
        before_cursor = note.textCursor()
        before_cursor_state = (before_cursor.anchor(), before_cursor.position())
        before_flags = note.textInteractionFlags()

        history = canvas.services.history_service
        history_item = object()
        redo_item = object()
        history.state.history.append(history_item)
        history.state.redo_stack.append(redo_item)
        history_object = history.state.history
        redo_object = history.state.redo_stack
        push_count = 0

        def fail_second_push(command) -> None:
            nonlocal push_count
            push_count += 1
            history.state.history.append(command)
            history.state.redo_stack.clear()
            if push_count == 2:
                raise RuntimeError("injected second note push failure")

        with (
            mock.patch.object(history, "push", side_effect=fail_second_push),
            self.assertRaisesRegex(RuntimeError, "second note push failure"),
        ):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                note,
                QColor("#cc3344"),
            )

        restored_cursor = note.textCursor()
        self.assertEqual(push_count, 2)
        self.assertIs(history.state.history, history_object)
        self.assertIs(history.state.redo_stack, redo_object)
        self.assertEqual(history.state.history, [history_item])
        self.assertEqual(history.state.redo_stack, [redo_item])
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(note.defaultTextColor(), before_default_color)
        self.assertEqual(committed_note_text_for(note), before_committed_text)
        self.assertEqual(committed_note_html_for(note), before_committed_html)
        self.assertEqual(
            (restored_cursor.anchor(), restored_cursor.position()),
            before_cursor_state,
        )
        self.assertEqual(note.textInteractionFlags(), before_flags)

    def test_note_color_keyboard_interrupt_restores_exact_runtime(self) -> None:
        class _InterruptingNote(NoteItem):
            interrupt_after_mutation = False

            def setDefaultTextColor(self, color) -> None:
                QGraphicsTextItem.setDefaultTextColor(self, color)
                if self.interrupt_after_mutation:
                    raise KeyboardInterrupt("injected note color interruption")

        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        note = _InterruptingNote(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        canvas.services.scene_item_controller.attach_scene_item(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())
        before_html = note.toHtml()
        before_default_color = note.defaultTextColor()
        before_committed_text = committed_note_text_for(note)
        before_committed_html = committed_note_html_for(note)
        before_cursor = note.textCursor()
        before_cursor_state = (before_cursor.anchor(), before_cursor.position())
        before_flags = note.textInteractionFlags()
        note.interrupt_after_mutation = True

        with self.assertRaisesRegex(KeyboardInterrupt, "note color interruption"):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                note,
                QColor("#cc3344"),
            )

        restored_cursor = note.textCursor()
        self.assertEqual(note.toHtml(), before_html)
        self.assertEqual(note.defaultTextColor(), before_default_color)
        self.assertEqual(committed_note_text_for(note), before_committed_text)
        self.assertEqual(committed_note_html_for(note), before_committed_html)
        self.assertEqual(
            (restored_cursor.anchor(), restored_cursor.position()),
            before_cursor_state,
        )
        self.assertEqual(note.textInteractionFlags(), before_flags)
        self.assertFalse(canvas.services.history_service.can_undo())

    def test_note_history_control_flow_error_keeps_primary_and_notes_rollback_failure(
        self,
    ) -> None:
        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        note = NoteItem(canvas)
        note.setData(0, "note")
        note.setPlainText("memo")
        canvas.services.scene_item_controller.attach_scene_item(note)
        set_committed_note_text_for(note, note.toPlainText())
        set_committed_note_html_for(note, note.toHtml())
        canvas.services.canvas_color_mutation_service.apply_color_to_item(
            note,
            QColor("#cc3344"),
        )
        command = canvas.services.history_service.state.history[-1]
        self.assertIsInstance(command, UpdateNoteColorCommand)
        assert isinstance(command, UpdateNoteColorCommand)

        def interrupt_after_mutation(item) -> None:
            item.setPlainText("partially restored")
            raise KeyboardInterrupt("primary note interruption")

        with (
            mock.patch.object(
                command.before_state,
                "apply",
                side_effect=interrupt_after_mutation,
            ),
            mock.patch.object(
                command.after_state,
                "apply",
                side_effect=SystemExit("secondary note rollback termination"),
            ),
            self.assertRaisesRegex(
                KeyboardInterrupt, "primary note interruption"
            ) as caught,
        ):
            command.undo(canvas)

        self.assertTrue(
            any(
                "SystemExit: secondary note rollback termination" in note_text
                for note_text in getattr(caught.exception, "__notes__", [])
            )
        )

    def test_shape_color_keyboard_interrupt_restores_brush(self) -> None:
        class _InterruptingShape(QGraphicsPathItem):
            interrupt_after_mutation = False

            def setBrush(self, brush) -> None:
                QGraphicsPathItem.setBrush(self, brush)
                if self.interrupt_after_mutation:
                    raise KeyboardInterrupt("injected shape color interruption")

        canvas = CanvasView()
        self.addCleanup(self._dispose_canvas, canvas)
        shape = _InterruptingShape()
        shape.setData(0, "shape")
        canvas.scene().addItem(shape)
        before_brush = shape.brush()
        shape.interrupt_after_mutation = True

        with self.assertRaisesRegex(KeyboardInterrupt, "shape color interruption"):
            canvas.services.canvas_color_mutation_service.apply_color_to_item(
                shape,
                QColor("#2f6ed3"),
            )

        self.assertEqual(shape.brush(), before_brush)
        self.assertFalse(canvas.services.history_service.can_undo())

    def test_apply_color_to_item_rejects_invalid_inputs_and_propagates_live_scene_error(
        self,
    ) -> None:
        scene = QGraphicsScene()
        other_scene = QGraphicsScene()
        color = QColor("#224466")
        push_command = mock.Mock()
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            push_command=push_command,
            services=SimpleNamespace(history_service=_history_service(push_command)),
        )
        _set_atom_graphics(canvas)
        set_bond_items_for(canvas, {})
        service = _color_service_for(canvas)

        invalid_kind_item = QGraphicsTextItem("X")
        invalid_kind_item.setData(0, "mystery")
        invalid_kind_item.setData(1, 1)
        scene.addItem(invalid_kind_item)
        mismatched_item = QGraphicsTextItem("Y")
        mismatched_item.setData(0, "atom")
        mismatched_item.setData(1, 1)
        other_scene.addItem(mismatched_item)
        deleted_item = mock.Mock()
        deleted_item.scene.side_effect = RuntimeError

        service.apply_color_to_item(invalid_kind_item, QColor())
        service.apply_color_to_item(mismatched_item, color)
        with self.assertRaises(RuntimeError):
            service.apply_color_to_item(deleted_item, color)
        service.apply_color_to_item(invalid_kind_item, color)

        push_command.assert_not_called()
        self.assertEqual(invalid_kind_item.defaultTextColor().name(), "#000000")

    def test_apply_ring_fill_color_ignores_non_ring_and_unchanged_state(self) -> None:
        non_ring_item = QGraphicsPathItem()
        non_ring_item.setData(0, "atom")
        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        fill = QColor("#abcdef")
        fill.setAlphaF(0.0)
        ring_item.setBrush(QBrush(fill))
        pushes = []
        canvas = SimpleNamespace(
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        service = _color_service_for(canvas)

        service.apply_ring_fill_color(non_ring_item, QColor("#abcdef"))
        service.apply_ring_fill_color(ring_item, QColor("#abcdef"), alpha=-3.0)

        self.assertEqual(pushes, [])
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 0.0)

    def test_apply_bond_color_ignores_invalid_none_and_unchanged_bonds(self) -> None:
        scene = QGraphicsScene()
        invalid_item = QGraphicsPathItem()
        invalid_item.setData(0, "bond")
        invalid_item.setData(1, "bad-id")
        scene.addItem(invalid_item)
        none_item = QGraphicsPathItem()
        none_item.setData(0, "bond")
        none_item.setData(1, 1)
        scene.addItem(none_item)
        unchanged_item = QGraphicsPathItem()
        unchanged_item.setData(0, "bond")
        unchanged_item.setData(1, 0)
        scene.addItem(unchanged_item)
        bond = Bond(1, 2, 1, color="#445566")
        pushes = []
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[bond, None]),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="same"),
            _bond_state_dict=lambda current: {"color": current.color},
            services=SimpleNamespace(history_service=_history_service(pushes.append)),
        )
        set_bond_items_for(canvas, {0: [], 1: [none_item]})
        service = _color_service_for(canvas)

        service.apply_color_to_item(invalid_item, QColor("#112233"))
        service.apply_color_to_item(none_item, QColor("#112233"))
        service.apply_color_to_item(unchanged_item, QColor("#445566"))

        self.assertEqual(pushes, [])
        self.assertNotEqual(unchanged_item.pen().color().name(), "#445566")

    def test_apply_atom_color_covers_ellipse_dot_missing_atom_and_same_color_paths(
        self,
    ) -> None:
        scene = QGraphicsScene()
        ellipse_item = QGraphicsEllipseItem(0.0, 0.0, 8.0, 8.0)
        ellipse_item.setData(0, "atom")
        ellipse_item.setData(1, 3)
        scene.addItem(ellipse_item)
        label_item = QGraphicsTextItem("N")
        scene.addItem(label_item)
        dot_proxy = mock.Mock()
        pushes = []
        brush = QBrush(QColor("#fedcba"))
        canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={3: Atom("N", 0.0, 0.0, color="#010101")}),
            services=SimpleNamespace(
                history_service=_history_service(pushes.append),
                atom_label_service=SimpleNamespace(
                    implicit_carbon_dot_brush=mock.Mock(return_value=brush)
                ),
            ),
        )
        _set_atom_graphics(canvas, {3: label_item}, {3: dot_proxy})
        service = _color_service_for(canvas)

        service.apply_color_to_item(ellipse_item, QColor("#abcdef"))

        self.assertEqual(ellipse_item.brush().color().name(), "#abcdef")
        self.assertEqual(label_item.defaultTextColor().name(), "#abcdef")
        dot_proxy.setBrush.assert_called_once_with(brush)
        self.assertIsInstance(pushes.pop(), UpdateAtomColorCommand)

        dot_item = AtomDotItem(-1.0, -1.0, 2.0, 2.0)
        dot_item.setData(0, "atom")
        dot_item.setData(1, 99)
        scene.addItem(dot_item)
        same_color_item = QGraphicsEllipseItem(0.0, 0.0, 6.0, 6.0)
        same_color_item.setData(0, "atom")
        same_color_item.setData(1, 3)
        scene.addItem(same_color_item)
        canvas.model.atoms[3].color = "#abcdef"

        service.apply_color_to_item(dot_item, QColor("#123456"))
        service.apply_color_to_item(same_color_item, QColor("#abcdef"))

        self.assertEqual(dot_item.brush().color().name(), "#fedcba")
        self.assertEqual(pushes, [])

    def test_apply_ring_structure_color_covers_invalid_metadata_and_dispatch(
        self,
    ) -> None:
        scene = QGraphicsScene()
        invalid_item = QGraphicsPathItem()
        invalid_item.setData(0, "ring")
        invalid_item.setData(2, "bad")
        scene.addItem(invalid_item)
        empty_item = QGraphicsPathItem()
        empty_item.setData(0, "ring")
        empty_item.setData(2, ["x"])
        scene.addItem(empty_item)
        ring_item = QGraphicsPathItem()
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2, "x"])
        scene.addItem(ring_item)
        atom_item = object()
        fallback_canvas = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}
            ),
            services=SimpleNamespace(
                history_service=_history_service(),
            ),
        )
        graph_service = SimpleNamespace(
            bond_sets_for_atoms=mock.Mock(return_value=({7}, set()))
        )
        _set_atom_graphics(fallback_canvas, {1: atom_item})
        set_bond_items_for(fallback_canvas, {7: []})
        service = _color_service_for(fallback_canvas, graph_service=graph_service)
        service.apply_color_to_item = mock.Mock()

        service._apply_ring_structure_color(invalid_item, QColor("#123456"))
        service._apply_ring_structure_color(empty_item, QColor("#123456"))
        service._apply_ring_structure_color(ring_item, QColor("#123456"))

        graph_service.bond_sets_for_atoms.assert_called_once_with({1, 2})
        service.apply_color_to_item.assert_called_once_with(
            atom_item, QColor("#123456")
        )


if __name__ == "__main__":
    unittest.main()
