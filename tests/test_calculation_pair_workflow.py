from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication

from chemvas.ui.dialogs.calculation_handoff_check import CalculationHandoffCheck
from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog
from tests.calculation_plan_support import _document_state, _plan

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def dialog() -> Iterator[CalculationStepDialog]:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    state = _document_state()
    state["calculation_plan"] = _plan()
    before = deepcopy(state)
    dialog = CalculationStepDialog(state)
    dialog.step_selector.setCurrentIndex(1)
    dialog.show()
    app.processEvents()
    yield dialog
    dialog.reject()
    assert state == before


def test_mapping_and_bond_changes(dialog: CalculationStepDialog) -> None:
    assert dialog._changed_bonds == [(0, 1), (2, 3)]
    dialog._clear_active_mappings()
    dialog._next_unmapped()
    assert dialog._selected_reactant == 0
    dialog._pick_product(2)
    assert dialog._mapping_by_reactant[0] == 2
    assert dialog._selected_reactant is None
    dialog._pick_reactant(1)
    dialog._pick_product(2)
    assert dialog._mapping_by_reactant.get(1) is None
    assert "same element" in dialog.suggestion_status.text()
    dialog._pick_product(3)
    assert dialog._mapping_by_reactant[1] == 3


@pytest.mark.parametrize(
    "edit", ["charge", "multiplicity", "id", "mapping", "inclusion", "role"]
)
def test_every_pair_edit_invalidates_review(
    dialog: CalculationStepDialog, edit: str
) -> None:
    artifact = {
        "handoff": {"status": "ready"},
        "payload": {"data": {"endpoint_geometry": {"sides": {}}}},
    }
    dialog._check_finished(artifact, b"source", "")
    dialog.review_checkbox.setChecked(True)
    assert dialog.export_button.isEnabled()
    if edit == "charge":
        dialog.reactant_widgets.charge.setValue(1)
    elif edit == "multiplicity":
        dialog.product_widgets.multiplicity.setValue(3)
    elif edit == "id":
        dialog.step_id.setText("different")
    elif edit == "mapping":
        dialog._mapping_combos[0].setCurrentIndex(0)
    elif edit == "inclusion":
        dialog._inclusion_combos[("reactant", 0)].setCurrentIndex(0)
    else:
        combo = dialog._role_combos[("reactant", 0)]
        combo.setCurrentIndex(combo.findData("catalyst"))
    assert dialog._checked_artifact is None
    assert not dialog.review_checkbox.isChecked()
    assert not dialog.export_button.isEnabled()


def test_worker_cancel_cleans_snapshot_and_reports_no_result(
    dialog: CalculationStepDialog, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = CalculationHandoffCheck(dialog)
    start = checker.process.start
    monkeypatch.setattr(
        checker.process,
        "start",
        lambda *_: start(sys.executable, ["-c", "import time; time.sleep(60)"]),
    )
    spy = QSignalSpy(checker.finished)
    state = _document_state()
    state["calculation_plan"] = _plan()
    checker.start(state, "S01")
    assert checker.process.waitForStarted(5000), checker.process.errorString()
    checker.cancel()
    assert len(spy) or spy.wait(5000)
    assert spy[0][0] is None
    assert "cancelled" in spy[0][2]
    assert checker._directory is None


def test_worker_start_failure_allows_retry(
    dialog: CalculationStepDialog, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = CalculationHandoffCheck(dialog)
    monkeypatch.setattr(sys, "executable", "/chemvas-missing-interpreter")
    spy = QSignalSpy(checker.finished)
    state = _document_state()
    state["calculation_plan"] = _plan()
    checker.start(state, "S01")
    assert len(spy) or spy.wait(5000)
    assert spy[0][0] is None
    assert spy[0][2]
    assert checker._directory is None


@pytest.mark.parametrize(
    "frozen, platform, suffix, prefix",
    [
        (False, "darwin", "python", ["-m", "chemvas"]),
        (True, "darwin", "python", []),
        (True, "win32", "chemvas-cli.exe", []),
    ],
)
def test_worker_uses_packaged_console_companion(
    monkeypatch: pytest.MonkeyPatch,
    frozen: bool,
    platform: str,
    suffix: str,
    prefix: list[str],
) -> None:
    from chemvas.ui.dialogs.calculation_handoff_check import _worker_command

    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "executable", "/bundle/python")
    executable, arguments = _worker_command()
    assert Path(executable) == Path("/bundle") / suffix
    assert arguments == prefix


def test_synchronous_process_launch_failure_stops_timeout(monkeypatch, qt_application):
    from PyQt6.QtCore import QProcess

    from chemvas.ui.dialogs.calculation_handoff_check import CalculationHandoffCheck
    from tests.test_calculation_step_rdkit import _balanced_state

    checker = CalculationHandoffCheck()
    results = []
    checker.finished.connect(lambda *result: results.append(result))
    monkeypatch.setattr(
        checker.process,
        "start",
        lambda *_args: checker._process_error(QProcess.ProcessError.FailedToStart),
    )
    checker.start(_balanced_state(), "S01")
    assert len(results) == 1
    assert results[0][2]
    assert not checker.timer.isActive()
    assert checker._directory is None
