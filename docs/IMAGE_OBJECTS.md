# Embedded PNG/JPEG images

[한국어](IMAGE_OBJECTS.ko.md)

Chemvas can combine complete PNG/JPEG rasters with native structures, notes,
arrows, and graphs in one `.chemvas` document. Image positions and display sizes
are editable canvas properties. Inserting, saving, reopening, copying a selection,
and undoing/redoing an edit retain the original encoded image bytes. Images are
embedded, so the original files are not needed to reopen the document.

## GUI

![Embedded images walkthrough: insert a PNG, drag it with Select, resize and lighten it in Image Properties](images/walkthrough-images.gif)

Choose **File → Insert Image…** and select a `.png`, `.jpg`, or `.jpeg` file.
Use the Select tool to move the resulting image. Select one image and choose
**Edit → Image Properties…** to set X, Y, width, height, aspect locking, and opacity.
Coordinates and sizes use canvas units, not source pixels. The whole raster is
displayed, including transparent margins; changing its size does not crop it.
Initial insertion fits the visible part of the sheet, or the sheet itself when
it is offscreen. Later manual moves can put pixels outside the exported sheet.

You can also copy an image in another application and paste it into the canvas.
When the clipboard supplies PNG/JPEG file bytes, those bytes are retained. When
it supplies only a decoded image, Chemvas embeds a lossless PNG of those clipboard
pixels; the original file's JPEG encoding or metadata is not available on that path.
Copying and pasting Chemvas selections retains the embedded bytes and native
objects. Image insertion and property edits participate in undo/redo.
Images have a fixed layer above shapes and ring fills, below native labels and
arrows. Their order relative to other images follows insertion order. Resizing
uses the properties dialog; there are no image corner handles. Group rotation
and flipping reposition image rectangles while keeping their pixels upright,
like text labels; pixel rotation, mirroring, cropping and filters are not supported.
Automatic **Arrange Scheme** does not support image-containing groups; use manual
Select, alignment, and Image Properties for image panels.

For original NMR/SEM figures, file insertion is the direct way to preserve the
source file bytes. Verify that the selected source includes the complete NMR axes,
concentration labels, and SEM scale bar; Chemvas does not infer or reconstruct
missing source content.

## CLI composition

Add an `images` array to composition v1. Every entry requires `source`, `x`, and
`y`. Sources may be absolute paths or paths relative to the composition JSON's
directory, independent of the command's working directory. Only regular PNG/JPEG
files are read. No URL fetch is performed.

```json
{
  "format": "chemvas-document-composition",
  "version": 1,
  "atoms": [],
  "bonds": [],
  "notes": [
    {"text": "Original ¹H NMR", "x": -350, "y": -265},
    {"text": "Original SEM", "x": -350, "y": 15}
  ],
  "images": [
    {"source": "originals/proton-nmr.png", "x": -350, "y": -240, "width": 700},
    {"source": "originals/sem.jpg", "x": -350, "y": 40, "width": 250,
     "opacity": 1.0, "lock_aspect": true}
  ]
}
```

```bash
chemvas compose-document figure.json --output figure.chemvas
chemvas check-layout figure.chemvas --sheet-only
chemvas render-document figure.chemvas --output figure.svg
chemvas render-document figure.chemvas --output figure.pdf
chemvas render-document figure.chemvas --output figure.png
```

Omit `height` when supplying `width`, or vice versa, to calculate the missing
dimension from the original pixel ratio. Omit both to use the source pixel
dimensions as canvas units. Supplying both keeps those exact dimensions, including
intentional stretching. `lock_aspect` (default `true`) governs later GUI resizing;
`opacity` defaults to `1.0` and accepts values from 0 to 1. Images should be placed
inside the document's sheet. Canvas origin is the sheet center; default landscape
A4 spans X −421…421 and Y −297.5…297.5. This example fits a 3:1 NMR source and
a 4:3 SEM source; adjust panel positions/sizes for other ratios and run the
sheet-only check before export. Composition writes a new output atomically
and refuses to overwrite an existing path. Its JSON report includes `image_count`
and `output_sha256`.

The Qt-free Python composition API accepts an explicit
`image_source_reader: Callable[[str], bytes]` keyword argument. File access and
relative-path resolution belong to the CLI bootstrap, not the composition feature.

## Native schema and limits

Document v7 may contain an optional `state.images` array. Empty image collections
are omitted by normal composition and canvas serialization, so documents without
images retain their previous shape. Image-bearing documents require an
image-capable Chemvas installation; older v7 readers reject the unknown `images`
field rather than silently losing it.

Each native image contains exactly these fields:

```json
{
  "kind": "image",
  "mime_type": "image/png",
  "data_base64": "<canonical base64 of the complete original file>",
  "pixel_width": 2400,
  "pixel_height": 1200,
  "x": 30,
  "y": 40,
  "width": 650,
  "height": 325,
  "opacity": 1.0,
  "lock_aspect": true
}
```

The MIME type is `image/png` or `image/jpeg` and must match the decoded content.
Pixel dimensions must match the source raster. Display width and height must be
positive finite numbers. `lock_aspect` must be a boolean. Native groups can refer
to an image as `["images", index]`; a clipboard selection carries images with the
same fields in `scene_items` and refers to them as `["scene_items", index]`.

Limits are 16 MiB of source bytes and 25 million pixels per image; 64 MiB of
combined source bytes, 100 million combined pixels, and 256 image objects per
document/selection. Native document and selection envelopes allow 96 MiB including
base64 and other document data. The composition JSON itself remains limited to
1 MiB because it contains file paths rather than embedded image bytes. Files are
checked with a full bounded decode; malformed, truncated, unsupported, animated,
and multi-frame images are rejected. PNG data after the first IEND chunk,
including a trailing newline or a second IEND, is rejected with an explicit
trailing-data message. Re-export a clean PNG; Chemvas does not trim or rewrite
source bytes on import. Pixel dimensions describe stored pixels;
EXIF orientation is not applied to or rewritten into the original source.

## Export behavior

SVG and PDF exports carry raster images, not pixel-to-vector fragments. An
editable SVG additionally carries native document metadata, which preserves the
original encoded bytes for Chemvas roundtrip. SVG's visible raster stream may be
re-encoded as PNG by Qt; PNG figure export rasterizes the whole composition at the
selected output size/DPI. Resizing on the canvas or choosing a low-resolution
figure export can therefore reduce the readability of original image text even
though the embedded native source is intact. PDF image rendering uses lossless
image rendering. PNG transparency and per-object opacity remain part of rendering.
The original 16-bit PNG file and its SVG raster can retain that precision;
PDF and whole-figure PNG export are 8-bit display outputs. Use the native
embedded source when the original pixel precision is needed.

The rendered raster omits source-image text metadata such as PNG text chunks
and JPEG comments, including in plain SVG and vector clipboard output. The
native document and Editable Chemvas SVG still preserve the exact encoded
source bytes, including that metadata; share plain figure exports when the
original image metadata should not travel with the editable document.

Images with zero effective object opacity do not contribute to whole-canvas or
selection figure export bounds; a figure containing only those images has nothing
to export. Positive-opacity images retain their full rectangle, including
transparent pixel margins. Native image state and the original selection frame
used by bitmap clipboard copy are unchanged.

Image text is raster content: `--min-font-pt` measures native text, not NMR labels
or SEM scale bars inside an image. There is no OCR or scientific annotation
validation. The editable SVG input envelope is bounded at 256 MiB (native payload
96 MiB); the 64 MiB headless render output limit also applies, so a large noisy image
re-encoded into SVG may exceed it. Keep `.chemvas` as the editable source and
visually inspect exported axes, labels, scale bars, and image edges at the intended
publication size.
