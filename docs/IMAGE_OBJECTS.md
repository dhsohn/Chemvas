# Embedded PNG/JPEG images

[한국어](IMAGE_OBJECTS.ko.md)

Chemvas allows embedding PNG and JPEG images directly into `.chemvas` documents alongside native chemical structures, text notes, and arrows. Embedded images are fully stored inside the document, so the original image files are not required to reopen or share the drawing.

## GUI Operations

![Embedded images walkthrough: insert a PNG, drag it with Select, resize and lighten it in Image Properties](images/walkthrough-images.gif)

- **Insert Image**: Choose **File ▸ Insert Image…** and select a `.png`, `.jpg`, or `.jpeg` file.
- **Move & Select**: Use the **Select** tool (`Space`) to drag and position images across the canvas.
- **Image Properties**: Select an image and choose **Edit ▸ Image Properties…** to adjust:
  - Position (X, Y) and dimensions (width, height in canvas units).
  - Aspect ratio locking (`lock_aspect`).
  - Layer opacity (from 0.0 to 1.0).
- **Clipboard Paste**: Copy any image from your operating system or web browser and press `Ctrl+V` to paste it directly onto the canvas.
- **Layer Stacking**: Use **Edit ▸ Bring to Front** and **Edit ▸ Send to Back** to adjust image layering relative to other annotations and shapes.

## CLI Composition

Embed images programmatically by including an `images` array in a Composition JSON manifest:

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

Compile and render headless figures:

```bash
chemvas compose-document figure.json --output figure.chemvas
chemvas check-layout figure.chemvas --sheet-only
chemvas render-document figure.chemvas --output figure.svg
chemvas render-document figure.chemvas --output figure.pdf
chemvas render-document figure.chemvas --output figure.png
```

- `source`: Relative path (from the JSON file's directory) or absolute path.
- `width` / `height`: If only one dimension is specified, Chemvas computes the other automatically using the source aspect ratio.
- `lock_aspect`: Preserves aspect ratio during subsequent GUI resizing.
- `opacity`: Opacity between `0.0` (fully transparent) and `1.0` (fully opaque).

## Document Schema & Constraints

In `.chemvas` documents, each image is stored as an object within the `state.images` array:

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

### Constraints & Limits

- **File Formats**: Standard PNG and JPEG files only.
- **Resource Limits**:
  - Maximum 16 MiB and 25 megapixels per individual image.
  - Maximum 64 MiB and 100 megapixels combined image payload per document (up to 256 images).
- **Integrity**: Original source image bytes are preserved bit-for-bit inside the Base64 payload.

## Figure Export

- **Vector Exports (SVG & PDF)**: Embedded images are included as high-fidelity rasters within the exported vector streams.
- **Editable Chemvas SVG**: Preserves the complete `.chemvas` metadata payload, allowing full round-trip reopening in Chemvas.
- **Raster Exports (PNG & TIFF)**: Images are rasterized at the chosen target DPI with full alpha transparency support.
