"""Bold native graphics use ChemDraw's BoldWidth for their strokes."""

import base64
import io

from PIL import Image

from chemvas.features.cdxml_document import parse_cdxml_document


def rectangle_stroke_pixels(kind: str) -> int:
    raw = (
        '<CDXML LineWidth="0.6" BoldWidth="2"><page id="1" BoundingBox="0 0 300 200">'
        f'<graphic id="2" GraphicType="Rectangle" RectangleType="{kind}" '
        'BoundingBox="100 100 20 20"/></page></CDXML>'
    ).encode()
    image = parse_cdxml_document(raw).state["images"][0]
    raster = Image.open(io.BytesIO(base64.b64decode(image["data_base64"])))
    row = raster.height // 2
    alpha = [raster.getpixel((x, row))[3] for x in range(raster.width // 2)]
    return sum(1 for a in alpha if a)


def test_bold_rectangle_strokes_at_bold_width():
    # The raster is four pixels per point.
    assert rectangle_stroke_pixels("Plain") == round(0.6 * 4)
    assert rectangle_stroke_pixels("Bold") == round(2 * 4)
    assert rectangle_stroke_pixels("RoundEdge Bold") == round(2 * 4)
