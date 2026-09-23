# 재현 가능한 논문 출판 그림 작성

[English](PUBLICATION_SCHEMES.md)

일관된 물리적 크기, 깔끔한 조판, 편집 가능한 원본 `.chemvas` 파일을 보존하면서 논문용 화학 반응식 그림을 프로그래밍 방식으로 생성하는 방법입니다.

저장소 루트에서 예제 스크립트를 실행합니다:

```bash
python examples/publication_scheme.py --output-dir /absolute/existing-parent/new-figures
```

이 스크립트는 표준화된 배율(결합당 5 mm)로 두 개의 예제 그림을 생성합니다:

![pair.png: two anisole drawings with subscript identifiers and a superscript footnote mark, captions arranged below](../examples/publication-pair.png)

![independent-parts.png: one caption describing two independently aligned molecular parts](../examples/publication-independent-parts.png)

지정한 출력 디렉터리에는 편집 가능한 `.chemvas` 문서 원본과 고해상도 출력 파일(SVG, 600 DPI PNG), 레이아웃 진단 보고서, 종합 `manifest.json`이 함께 생성됩니다.

## 출판 그림 작성을 위한 모범 사례

1. **표준 템플릿 사용**: `insert-template` 명령을 활용하여 일관된 결합 각도와 방향족 고리 구조를 생성합니다.
2. **논문 전체의 일관된 배율**: 하나의 논문에 들어가는 모든 그림에 공통 배율(`mm_per_unit`)을 적용하여 결합 길이, 글꼴 크기, 선 두께의 일관성을 유지합니다.
3. **구조적 정렬**: 구조와 캡션을 그룹으로 묶고 `layout-document`로 정렬합니다. `mode: "align-y"`를 사용하면 분자들의 세로 중심을 기준선에 맞출 수 있습니다.
4. **정밀한 조판**: 화학식의 아래첨자와 전이 상태 기호(`‡`) 등은 `vertical_align: "sub"` / `"super"` 속성의 `runs` 배열을 사용하여 정확하게 표현합니다.
5. **출력 전 레이아웃 검사**: 최종 그림을 내보내기 전에 `check-layout`을 실행하여 텍스트 겹침이나 용지 경계 초과가 없는지 미리 확인합니다.

## 작용기 약어 및 라벨 방향

- **가역적 약어 배치**: `OMe`와 같은 작용기 약어는 결합 방향에 따라 글자 배치가 자동으로 조정됩니다:
  - 왼쪽에서 결합할 때: `OMe`로 표시.
  - 오른쪽에서 결합할 때: 결합 원자인 산소(O)가 결합 선에 직접 맞닿도록 `MeO`로 자동 전환.
- **물리적 배율 일관성**: 헤드리스 렌더링은 고정 96 DPI를 기준으로 텍스트와 선 두께를 계산하여 실행 환경에 관계없이 일관된 크기를 보장합니다.

## 다중 반응 비교 도식

여러 반응 경로를 열 단위로 나란히 비교하는 그림을 생성하려면:

```bash
python examples/publication_comparison.py --output-dir /absolute/existing-parent/new-comparison
```

![comparison.png: two complete rows, each with an input, a labelled arrow and an output, sharing column widths](../examples/publication-comparison.png)

### 비교 도식 배치 원칙

- **독립 블록 구성**: 각 반응물과 생성물을 관련 라벨 및 캡션과 함께 독립된 블록으로 그룹화합니다.
- **공통 열 그룹**: `column_group: "comparison"`을 지정하면 서로 다른 행에 속한 단계들도 동일한 열 너비를 공유하도록 정렬됩니다.
- **구조별 캡션 정렬**: `caption_alignment: "structure"`를 사용하면 각 블록의 중심 아래에 캡션이 정확히 배치됩니다.

구체적인 CLI 옵션 및 JSON 스키마는 [에이전트 CLI 안내](AGENT_CLI.ko.md) 및 [반응 도식 배치](SCHEME_LAYOUT.ko.md)를 참고하세요.
