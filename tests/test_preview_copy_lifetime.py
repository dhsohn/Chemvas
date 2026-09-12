from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

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
from chemvas.ui.preview_3d import Preview3D

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
owner = QWidget()
owner.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
owner.resize(700, 400)
preview = Preview3D()
preview.setParent(owner)
preview.resize(680, 380)
preview.set_info('CH4', '16.04', 'C', 'InChI=1S/CH4/h1H4', 'VNWKTOKETHGBQD-UHFFFAOYSA-N')
survivor = QWidget()
survivor.show()
owner.show()
app.processEvents()
name = sys.argv[1]
button = preview.findChild(QToolButton, 'preview_copy_' + name + '_button')
assert button is not None and button.isVisible()
QTest.mouseClick(button, Qt.MouseButton.LeftButton)
assert button.text() == 'Copied'
assert app.clipboard().text()
if sys.argv[2] == 'close':
    QTimer.singleShot(50, owner.close)
    QTest.qWait(1400)
    assert sip.isdeleted(button) and sip.isdeleted(preview)
    assert survivor.isVisible()
else:
    QTest.qWait(700)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QTest.qWait(700)
    assert button.text() == 'Copied', 'A previous click must not reset the latest feedback'
    QTest.qWait(650)
    assert button.text() == {'smiles': 'SMILES', 'inchi': 'InChI', 'inchikey': 'InChIKey'}[name]
    owner.close()
    app.processEvents()
print('PASS: copy timer teardown and surviving window' if sys.argv[2] == 'close' else 'PASS: restarted copy feedback')
"""


@pytest.mark.parametrize("name", ["smiles", "inchi", "inchikey"])
@pytest.mark.parametrize("mode", ["close", "repeat"])
def test_copy_feedback_follows_button_lifetime(tmp_path: Path, name: str, mode: str):
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = environment.get("QT_QPA_PLATFORM", "offscreen")
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        environment[key] = str(tmp_path / key.lower())
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, name, mode],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
