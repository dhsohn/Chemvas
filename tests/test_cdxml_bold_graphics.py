"""Bold native graphics use ChemDraw's BoldWidth for their strokes."""

import base64
import io

from PIL import Image

from chemvas.features.cdxml_document import parse_cdxml_document


def rectangle_stroke_points(kind: str, line_width: str = "0.6") -> float:
    raw = (
        f'<CDXML LineWidth="{line_width}" BoldWidth="2"><page id="1" BoundingBox="0 0 300 200">'
        f'<graphic id="2" GraphicType="Rectangle" RectangleType="{kind}" '
        'BoundingBox="100 100 20 20"/></page></CDXML>'
    ).encode()
    image = parse_cdxml_document(raw).state["images"][0]
    raster = Image.open(io.BytesIO(base64.b64decode(image["data_base64"])))
    row = raster.height // 2
    alpha = [raster.getpixel((x, row))[3] for x in range(raster.width // 2)]
    # Convert stroke pixels to points with the projection's placed width.
    return sum(1 for a in alpha if a) * image["width"] / raster.width


def test_bold_rectangle_strokes_at_bold_width():
    assert abs(rectangle_stroke_points("Plain") - 0.6) < 0.01
    assert abs(rectangle_stroke_points("Bold") - 2) < 0.01
    assert abs(rectangle_stroke_points("RoundEdge Bold") - 2) < 0.01


def test_raster_stroke_keeps_its_native_width():
    # A fixed 4 px/pt raster rounded these to 0.5, 0.25 and 0.25 pt.
    for width in ("0.6", "0.3", "0.15", "0.45"):
        assert abs(rectangle_stroke_points("Plain", width) - float(width)) < 0.005
