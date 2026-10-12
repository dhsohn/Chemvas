"""Temporary read-only glyph evidence; removed before the correction PR."""

import faulthandler
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if sys.platform == "darwin":
    from tests.macos_test_support import disable_window_restore

    disable_window_restore()

from PyQt6.QtCore import QT_VERSION_STR, QPointF, qVersion
from PyQt6.QtGui import QFontInfo, QPainterPath, QRawFont, QTextLayout
from PyQt6.QtWidgets import QApplication

faulthandler.enable()


def emit(kind, **data):
    print("WINDOWS_GATE_EVIDENCE " + json.dumps({"kind": kind, **data}), flush=True)


def rect(value):
    return [value.x(), value.y(), value.width(), value.height()]


def point(value):
    return [value.x(), value.y()]


def raw_font(raw):
    if not raw.isValid():
        return {"valid": False}
    return {
        "valid": raw.isValid(),
        "family": raw.familyName(),
        "pixel_size": raw.pixelSize(),
        "ascent": raw.ascent(),
        "descent": raw.descent(),
        "weight": int(raw.weight()),
        "style": raw.style().name,
    }


def document_runs(item):
    item.boundingRect()
    blocks = []
    block = item.document().begin()
    while block.isValid():
        layout = block.layout()
        runs = []
        for run in layout.glyphRuns(0, block.length() - 1):
            raw = run.rawFont()
            runs.append(
                {
                    "font": raw_font(raw),
                    "indices": list(run.glyphIndexes()),
                    "positions": [point(v) for v in run.positions()],
                    "outlines": [
                        rect(raw.pathForGlyph(g).boundingRect())
                        for g in run.glyphIndexes()
                    ]
                    if raw.isValid()
                    else None,
                    "outline_empty": [
                        raw.pathForGlyph(g).isEmpty() for g in run.glyphIndexes()
                    ]
                    if raw.isValid()
                    else None,
                }
            )
        blocks.append(
            {
                "text": block.text(),
                "layout_position": point(layout.position()),
                "lines": [
                    {"y": layout.lineAt(i).y(), "ascent": layout.lineAt(i).ascent()}
                    for i in range(layout.lineCount())
                ],
                "runs": runs,
            }
        )
        block = block.next()
    return blocks


def environment():
    app = QApplication.instance()
    emit(
        "environment",
        platform=app.platformName(),
        requested=os.environ.get("QT_QPA_PLATFORM"),
        python=sys.version,
        qt=QT_VERSION_STR,
        qt_runtime=qVersion(),
        dpi=app.primaryScreen().logicalDotsPerInch(),
        default_font=app.font().toString(),
    )


def atom():
    import tests.test_atom_label_service as test

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    environment()
    original = test._painted_atom_y

    def measured(item, normal_text):
        result = original(item, normal_text)
        emit("original_measurement", text=item.toPlainText(), measured_y=result)
        outline = QPainterPath()
        outline.addText(QPointF(), item.font(), normal_text)
        layout = item._layout
        emit(
            "atom",
            text=item.toPlainText(),
            normal_text=normal_text,
            font=item.font().toString(),
            actual_family=QFontInfo(item.font()).family(),
            raw=raw_font(QRawFont.fromFont(item.font())),
            position=point(item.pos()),
            typographic=item._typographic,
            center=point(item.label_position_center()),
            glyph_bounds=rect(item.glyph_path().boundingRect()),
            normal_bounds=rect(outline.boundingRect()),
            measured_y=result,
            document=document_runs(item),
            typography=None
            if layout is None
            else [
                {"role": r.role, "text": r.text, "baseline": r.baseline, "x": r.x}
                for r in layout.runs
            ],
        )
        return result

    names = [
        "test_carbon_dot_helpers_position_label_and_restore_item_interaction",
        "test_cf3_with_a_left_bond_anchors_on_the_leading_carbon",
        "test_multi_part_label_with_a_vertical_bond_anchors_on_attachment",
    ]
    suite = unittest.TestSuite(test.AtomLabelServiceTest(n) for n in names)
    with patch.object(test, "_painted_atom_y", measured):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    emit(
        "original_assertions",
        passed=result.wasSuccessful(),
        count=result.testsRun,
        failures=[{"test": str(t), "traceback": tb} for t, tb in result.failures],
        errors=[{"test": str(t), "traceback": tb} for t, tb in result.errors],
    )
    # Product font cases supplement, rather than replace, the original assertions.
    for text, neighbor in [("NH", (-20, 0)), ("CF3", (-20, 0)), ("CF3", (0, -20))]:
        canvas = test._FakeCanvas()
        canvas.renderer.atom_font = test.Renderer().atom_font
        canvas.model = test.MoleculeModel(
            atoms={1: test.Atom("C", *neighbor), 2: test.Atom("C", 0, 0)},
            bonds=[test.Bond(1, 2, 1, style="single")],
        )
        test._atom_label_service(canvas).add_or_update_atom_label(2, text, record=False)
        emit("product_font_case", text=text, neighbor=neighbor)
        measured(canvas.atom_items[2], "NH" if text == "NH" else "CF")


def cdxml():
    import xml.etree.ElementTree as ET

    from tests.test_cdxml_export import (
        _resolved_export,
        _simple_state,
        offscreen_document_scene,
        preflight_cdxml,
        serialize_cdxml,
        test_refuse_fallback_glyph_note,
    )

    from chemvas.bootstrap.document_cli_shared import offscreen_application

    with offscreen_application(command="windows-gate-diagnostic"):
        environment()
        try:
            test_refuse_fallback_glyph_note()
        except BaseException as exc:
            emit(
                "original_cdxml_assertion",
                passed=False,
                type=type(exc).__name__,
                reason=str(exc),
            )
        else:
            emit("original_cdxml_assertion", passed=True)
        state = _simple_state(notes=[{"text": "\U0001f600", "x": 0.0, "y": 30.0}])
        with offscreen_document_scene(
            state, command="windows-gate-diagnostic"
        ) as context:
            note = context.state.note_items()[0]
            font = note.document().defaultFont()
            primary_family = QFontInfo(font).family()
            layout = QTextLayout("\U0001f600", font)
            layout.beginLayout()
            line = layout.createLine()
            if line.isValid():
                line.setLineWidth(1e6)
            layout.endLayout()
            premise_runs = [
                {"font": raw_font(run.rawFont()), "indices": list(run.glyphIndexes())}
                for run in layout.glyphRuns()
            ]
            emit(
                "original_cdxml_premise",
                primary_family=primary_family,
                runs=premise_runs,
                has_fallback=any(
                    r["font"]["family"] and r["font"]["family"] != primary_family
                    for r in premise_runs
                ),
                has_glyph_zero=any(0 in r["indices"] for r in premise_runs),
            )
            emit(
                "note",
                requested_font=note.document().defaultFont().toString(),
                document=document_runs(note),
            )
            items, plan = _resolved_export(context)
            try:
                preflight_cdxml(context, items, plan)
                xml = serialize_cdxml(context, items, plan)
            except Exception as exc:
                emit("cdxml_refusal", type=type(exc).__name__, reason=str(exc))
            else:
                root = ET.fromstring(xml)
                emit(
                    "cdxml_success",
                    xml=xml.decode(),
                    scale=plan.out_w_pt / plan.source_w,
                    fonts=[dict(f.attrib) for f in root.findall("./fonttable/font")],
                    segments=[
                        {"text": s.text, **s.attrib} for s in root.findall("./page/t/s")
                    ],
                )


if __name__ == "__main__":
    {"atom": atom, "cdxml": cdxml}[sys.argv[1]]()
