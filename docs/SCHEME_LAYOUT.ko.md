# 반응 구조 및 캡션 배치

[English](SCHEME_LAYOUT.md)

`layout-document`는 반응식 내 구조와 캡션 노트를 깔끔한 행 단위로 정렬합니다. 각 분자 아래에 캡션을 자동으로 가운데 맞춤하고, 캡션 기준선을 정렬하며, 여러 행으로 구성된 반응 도식에서도 일관된 열 너비를 유지합니다.

## CLI를 통한 스크립트 배치

CLI를 사용해 배치 작업을 자동화할 수 있습니다:

```bash
chemvas inspect-document scheme.chemvas
chemvas layout-document scheme.chemvas --layout layout.json --output arranged.chemvas
chemvas check-layout arranged.chemvas
chemvas render-document arranged.chemvas --output arranged.svg --width-mm 174 --max-height-mm 120
```

### 배치 요청 스펙 (Arrange 모드)

일반적인 배치 요청은 블록들을 행으로 정렬하고 하단에 캡션을 배치합니다:

```json
{
  "format": "chemvas-scheme-layout",
  "version": 1,
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "gap": 12,
  "row_gap": 24,
  "caption_gap": 8,
  "line_gap": 4,
  "rows": [{
    "blocks": [
      {"atoms": [0, 1, 2], "captions": [0, 1], "anchor_atom": 0},
      {"atoms": [3, 4, 5], "captions": [2, 3], "anchor_atom": 3,
       "items": [["ts_brackets", 0]]}
    ],
    "arrows": [0]
  }]
}
```

![Before layout: the second structure sits higher, its captions further down and the bracket loosely around it](images/cli-layout-arrange-before.png)

![After layout: both blocks share a row, captions are centred below each structure at common baselines, the bracket moved with its block](images/cli-layout-arrange-after.png)

- **`blocks`**: 분자 단위 배열. `atoms`는 원자 ID 목록, `captions`는 위에서 아래 순서의 노트 인덱스, `anchor_atom`은 정렬 기준점으로 삼을 특정 원자입니다.
- **`column_group`**: 여러 행에 걸쳐 동일한 식별자를 지정하면 열 너비를 일치시킵니다.
- **`caption_alignment`**: `"row"`는 행 전체의 기준선에 캡션을 정렬하고, `"structure"`는 각 분자 바로 아래에 캡션을 배치합니다.

## `1 + 2 → 3`의 반응물별 캡션

각 분자와 해당 캡션을 별도 블록으로 유지합니다. 보이는 텍스트가 `+`인 노트를
만들고 구조 블록 밖에 둡니다. 첫 반응물 뒤에는 `+` 노트, 두 번째 반응물
뒤에는 화살표를 연결 요소로 지정합니다.

CLI 요청에서는 `rows` 안에 다음 행을 넣습니다(인덱스는 모두 0부터 시작).

```json
{
  "blocks": [
    {"atoms": [0, 1, 2], "captions": [0]},
    {"atoms": [3, 4, 5], "captions": [1]},
    {"atoms": [6, 7, 8], "captions": [2]}
  ],
  "connectors": [["notes", 3], ["arrows", 0]]
}
```

노트 3은 기존 `+`이고, 노트 0–2는 각 분자의 캡션입니다. 배치기는 `+`의 표시
중심을 분자 축에 맞추고 각 캡션은 해당 블록 아래에 둡니다.

각 블록 사이마다 연결 요소를 하나씩 지정하거나, 갤러리 배치라면 모두 생략합니다.
한 행에서 `connectors`와 기존 화살표 전용 `arrows`를 함께 사용할 수 없습니다.
각 연결 요소는 서로 다른 기존 화살표 또는 `+` 노트여야 하며 캡션이나 블록 항목과
중복될 수 없습니다. `arrow_color`는 화살표만 변경합니다. 명시적 `connectors`는
arrange 모드에서 사용하며, `align-y`는 연결 요소를 이동하지 않습니다.

줄바꿈에서는 `+`로 이어진 블록들을 같은 줄에 유지합니다. 이 단위 전체가 들어가지
않으면 줄바꿈 폭을 늘려야 합니다. `+`가 다음 줄 맨 앞에 홀로 배치되지는 않습니다.
기존 객체를 이동하므로 문서 형식은 바뀌지 않습니다. 새 출력 문서를 저장하며,
다시 열기와 내보내기에서도 캡션·`+`·화살표의 배치를 유지합니다.


## 분자 구조만 세로 정렬 (`align-y`)

캡션과 가로 배치는 이미 완성되어 있고 분자의 세로 중심만 맞추고 싶을 때는 `"mode": "align-y"`를 사용합니다:

```json
{
  "format": "chemvas-scheme-layout",
  "version": 1,
  "mode": "align-y",
  "source_sha256": "<64 lowercase hexadecimal characters>",
  "rows": [{
    "reference_blocks": [0],
    "blocks": [
      {"atoms": [0, 1, 2], "captions": [0]},
      {"atoms": [3, 4, 5, 6], "captions": [1],
       "parts": [[3, 4, 5], [6]]}
    ]
  }]
}
```

![Before align-y: the product chain and the Cl⁻ sit well above the reactant](images/cli-layout-align-y-before.png)

![After align-y: both parts moved down to the reactant's molecular midline, captions untouched](images/cli-layout-align-y-after.png)

- **`reference_blocks`**: 세로 정렬의 기준선이 될 기준 블록 인덱스입니다.
- **`parts`**: 하나의 블록 안에서 독립적으로 세로 이동할 조각(예: 이온이나 별도 시약)을 지정합니다.

## 긴 반응 경로의 자동 줄바꿈

여러 단계의 긴 반응식을 여러 줄로 줄바꿈하려면 `"max_row_width"`를 지정합니다:

![Before wrapping: four states and three arrows in one long row](images/cli-layout-wrap-before.png)

![After wrapping with max_row_width 320: two lines, the continuation arrow at the start of the second line](images/cli-layout-wrap-after.png)

- 블록 내부 구조가 쪼개지지 않고 온전하게 다음 줄로 넘어갑니다.
- 줄바꿈 위치에 걸친 연결 화살표는 다음 줄 맨 앞으로 이동하여 반응이 계속 이어짐을 직관적으로 보여줍니다.

## 레이아웃 검증 및 출력 가드

최종 그림을 내보내기 전, 최소 글꼴 크기와 최대 높이 조건을 지정하여 가독성을 보장할 수 있습니다:

```bash
chemvas render-document arranged.chemvas --output arranged.svg --width-mm 174 --min-font-pt 6
```

- `--min-font-pt`: 그림 축소로 인해 텍스트(첨자 포함)가 지정한 pt 미만으로 작아지면 출력을 중단합니다.
- `--max-height-mm`: 논문 규격을 초과하는 높이의 그림 출력을 방지합니다.
