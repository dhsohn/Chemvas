# PNG/JPEG 이미지 내장

[English](IMAGE_OBJECTS.md)

Chemvas는 화학 구조, 텍스트 노트, 화살표와 함께 PNG 및 JPEG 래스터 이미지를 `.chemvas` 문서 안에 직접 내장하여 다룰 수 있습니다. 이미지는 문서 파일 내에 완전히 포함되어 저장되므로 원본 이미지 파일이 없어도 문서를 열고 편집할 수 있습니다.

## 데스크톱 GUI 작업

![Embedded images walkthrough: insert a PNG, drag it with Select, resize and lighten it in Image Properties](images/walkthrough-images.gif)

- **이미지 삽입**: **File ▸ Insert Image…**를 선택하고 `.png`, `.jpg`, `.jpeg` 파일을 선택합니다.
- **이동 및 선택**: **Select** 도구(`Space`)를 사용하여 캔버스 위에서 이미지를 원하는 위치로 드래그합니다.
- **이미지 속성 편집**: 이미지를 선택하고 **Edit ▸ Image Properties…**를 열어 다음 항목을 설정합니다:
  - 위치(X, Y) 및 크기(너비, 높이 - 캔버스 단위).
  - 가로세로 비율 고정 (`lock_aspect`).
  - 레이어 불투명도 (`opacity`, 0.0~1.0).
- **클립보드 붙여넣기**: 다른 응용 프로그램이나 웹 브라우저에서 복사한 이미지를 캔버스에서 `Ctrl+V`로 즉시 붙여넣을 수 있습니다.
- **레이어 순서 조정**: **Edit ▸ Bring to Front**(맨 앞으로) 및 **Edit ▸ Send to Back**(맨 뒤로)을 통해 이미지와 분자 구조, 화살표 간의 앞뒤 층위를 조절합니다.

## CLI 문서 구성 (Composition)

Composition JSON 매니페스트에 `images` 배열을 추가하여 이미지를 프로그래밍 방식으로 배치할 수 있습니다:

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

헤드리스로 문서를 생성하고 렌더링합니다:

```bash
chemvas compose-document figure.json --output figure.chemvas
chemvas check-layout figure.chemvas --sheet-only
chemvas render-document figure.chemvas --output figure.svg
chemvas render-document figure.chemvas --output figure.pdf
chemvas render-document figure.chemvas --output figure.png
```

- `source`: 구성 JSON 파일 기준의 상대 경로 또는 절대 경로.
- `width` / `height`: 둘 중 하나만 지정하면 원본 이미지의 비율에 맞춰 나머지 값이 자동으로 계산됩니다.
- `lock_aspect`: 이후 GUI 편집 시 가로세로 비율 유지 여부.
- `opacity`: `0.0`(완전 투명)에서 `1.0`(완전 불투명) 사이의 값.

## 문서 스키마 및 제약 조건

`.chemvas` 파일 내에서 각 이미지는 `state.images` 배열 아래에 객체로 저장됩니다:

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

### 자원 제한 및 형식 기준

- **지원 형식**: 표준 PNG 및 JPEG 파일.
- **용량 제한**:
  - 개별 이미지당 최대 16 MiB 및 2,500만 픽셀.
  - 문서당 총 이미지 합계 최대 64 MiB, 1억 픽셀, 256개 객체.
- **무결성**: Base64 페이로드 내에 원본 이미지 바이트가 손실 없이 그대로 보존됩니다.

## 그림 출력

- **벡터 출력 (SVG, PDF)**: 내장된 이미지는 고해상도 래스터 형태로 벡터 스트림 내에 포함되어 출력됩니다.
- **편집 가능한 SVG (Editable Chemvas SVG)**: `.chemvas` 메타데이터가 함께 내장되어, 내보낸 SVG 파일을 Chemvas에서 다시 열어 언제든 계속 편집할 수 있습니다.
- **래스터 출력 (PNG, TIFF)**: 지정된 DPI에 맞춰 렌더링되며, 알파 투명 배경을 온전히 지원합니다.
