# 반응 구조 및 캡션 배치

[English](SCHEME_LAYOUT.md)

`layout-document`는 반응식 내 구조와 캡션 노트를 깔끔한 행 단위로 정렬합니다. 각 분자 아래에 캡션을 자동으로 가운데 맞춤하고, 캡션 기준선을 정렬하며, 여러 행으로 구성된 반응 도식에서도 일관된 열 너비를 유지합니다.

## 데스크톱 GUI에서 배치하기

![Arrange Scheme walkthrough: group each structure with its caption, open the dialog, choose captions and the arrow, click Arrange](images/walkthrough-arrange.gif)

1. **구조와 캡션 그룹화**: 각 분자 구조와 이에 딸린 캡션 노트를 함께 선택한 뒤 **Edit ▸ Group** (`Ctrl+G`)으로 묶습니다.
2. **배치 대화상자 실행**: **Edit ▸ Arrange Scheme…**를 엽니다. 각 그룹이 하나의 독립된 블록으로 인식됩니다.
3. **캡션 및 연결 화살표 지정**:
   - 노트를 **Structure caption** 또는 상대 위치를 유지하는 **Attached note**로 지정합니다.
   - 블록 사이를 연결할 화살표를 선택합니다.
4. **간격 및 줄바꿈 설정**: 간격과 선택적 **Wrap width**를 설정한 뒤 **Arrange**를 클릭합니다. 작업 내용은 언제든 `Ctrl+Z`로 실행 취소할 수 있습니다.

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
