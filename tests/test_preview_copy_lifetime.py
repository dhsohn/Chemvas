from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from tests.subprocess_support import source_subprocess_env

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT = r"""
import sys
if sys.platform != 'win32':
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
from PyQt6 import sip
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton, QWidget
from chemvas.ui.preview3d.preview_3d import Preview3D

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
owner = QWidget()
owner.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
owner.resize(700, 400)
preview = Preview3D()
preview.setParent(owner)
preview.resize(680, 380)
values = {'smiles': 'C', 'inchi': 'InChI=1S/CH4/h1H4', 'inchikey': 'VNWKTOKETHGBQD-UHFFFAOYSA-N'}
labels = {'smiles': 'SMILES', 'inchi': 'InChI', 'inchikey': 'InChIKey'}
preview.set_info('CH4', '16.04', values['smiles'], values['inchi'], values['inchikey'])
survivor = QWidget()
survivor.show()
owner.show()
app.processEvents()
# Every copy button is built by the same helper, so one process clicks all of
# them and each timer wait covers the three buttons at once.
buttons = {name: preview.findChild(QToolButton, 'preview_copy_' + name + '_button') for name in labels}

def click_all():
    for name, button in buttons.items():
        assert button is not None and button.isVisible(), name
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert button.text() == 'Copied', name
        assert app.clipboard().text() == values[name], name

click_all()
if sys.argv[1] == 'close':
    QTimer.singleShot(50, owner.close)
    QTest.qWait(1400)
    assert all(sip.isdeleted(button) for button in buttons.values()) and sip.isdeleted(preview)
    assert survivor.isVisible()
else:
    QTest.qWait(700)
    click_all()
    QTest.qWait(700)
    assert all(button.text() == 'Copied' for button in buttons.values()), 'A previous click must not reset the latest feedback'
    QTest.qWait(650)
    assert all(button.text() == labels[name] for name, button in buttons.items())
    owner.close()
    app.processEvents()
print('PASS: copy timer teardown and surviving window' if sys.argv[1] == 'close' else 'PASS: restarted copy feedback')
"""


@pytest.mark.parametrize("mode", ["close", "repeat"])
def test_copy_feedback_follows_button_lifetime(tmp_path: Path, mode: str):
    environment = source_subprocess_env()
    environment["QT_QPA_PLATFORM"] = environment.get("QT_QPA_PLATFORM", "offscreen")
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        environment[key] = str(tmp_path / key.lower())
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, mode],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
