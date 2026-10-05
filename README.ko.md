<p align="center">
  <img src="https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/banner.png" alt="Chemvas — 직접 그리고, 간편하게 자동화하고, 정확하게 내보내세요." width="680">
</p>

<p align="center">
  <a href="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml"><img src="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/chemvas/"><img src="https://img.shields.io/pypi/v/chemvas" alt="PyPI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/dhsohn/Chemvas/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center"><a href="https://github.com/dhsohn/Chemvas/blob/main/README.md">English</a> · <b>한국어</b></p>

Chemvas는 **다시 만들 수 있는 반응식 그림**을 위한 오픈소스 드로잉 도구입니다. 모든 그림은 편집 가능한 `.chemvas` 파일(JSON, version 9)과 명령 한 줄에서 나오므로, 내용을 고친 뒤에도 논문 단 너비에 맞춰 다시 렌더링할 수 있습니다. 스크립트나 AI 에이전트는 파일을 통째로 다시 쓰는 대신 검사를 거치는 패치로 같은 파일을 편집할 수 있습니다.

## Chemvas로 하는 일

**재현 가능한 논문용 반응식**

- `render-document`는 창을 띄우지 않고 SVG, PDF, PNG, [CDXML](https://github.com/dhsohn/Chemvas/blob/main/docs/CDXML_EXPORT.ko.md)을 84 mm나 174 mm 같은 단 너비에 맞춰 내보냅니다.
- `check-layout`은 내보내기 전에 흔한 라벨 충돌과 용지 밖으로 나간 요소를 알려 줍니다. 모든 객체 쌍을 검사하지는 않습니다.
- [논문 그림 작성 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md)는 결합 길이와 글자 크기를 고정한 스크립트로 완성 그림을 만들어, 한 원고의 모든 반응식이 같은 축척을 갖게 합니다.

**검증 가능한 에이전트 편집**

- `inspect-document`는 모든 원자를 고정 ID로, 모든 결합을 두 원자 ID로 나열하고, 파일의 SHA-256을 알려 줍니다.
- `apply-patch`는 그래프 연산을 담은 JSON 패치를 받습니다. 다른 파일 바이트를 기준으로 쓴 패치는 거부하고, `--dry-run`으로 아무것도 쓰지 않고 패치를 검사할 수 있으며, 문서 전체를 검증한 뒤 새 파일에만 씁니다. 입력 파일은 절대 바꾸지 않습니다.
- 패치 검사는 문서 구조만 다루고 화학은 다루지 않습니다. 원소 기호와 원자가는 검증하지 않으므로, 사용하기 전에 렌더링된 그림을 확인하세요.

**손으로 그리기**

- 데스크톱 앱에서 구조, 반응 화살표와 라벨을 그리고, 정렬 도구와 자동 저장, 세션 복구를 쓸 수 있습니다. 앱에서 저장한 그림은 위의 모든 명령에 그대로 쓸 수 있고, 반대도 마찬가지입니다.

## 현재 한계

Chemvas는 파일 교환 면에서 ChemDraw를 대신하지 못합니다. Chemvas가 정확히 표현할 수 없는 입력은 잘못 그리는 대신 오류로 거부합니다.

- **열 수 있는 파일:** `.chemvas`, **Editable Chemvas SVG**를 켜고 Chemvas에서 내보낸 SVG(다른 SVG 파일은 열 수 없음), Chemvas가 쓰는 범위(결합 차수 1–3, 쐐기·해시 결합, 전하, 라디칼) 안의 2D MOL V2000 파일.
- **거부하는 입력:** CDX/CDXML, SDF, RXN 파일. 3D 좌표, 동위원소, 방향족 결합 유형 4, V3000을 쓴 MOL 파일.

## 설치

**Python 3.12 이상**이 필요합니다.

```bash
pip install chemvas
chemvas
```

그리기, 그림 출력, 스크립트 빠른 시작은 이 설치로 동작합니다. 선택적 화학 정보학 extra는 없습니다.

Windows 로컬 빌드 및 패키징은 [패키징 안내](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.ko.md)를 참고하세요.

## 빠른 시작: 스크립트나 에이전트에서

```bash
chemvas compose-document scheme.json --output scheme.chemvas
chemvas inspect-document scheme.chemvas > inspection.json
chemvas apply-patch scheme.chemvas patch.json --dry-run
chemvas apply-patch scheme.chemvas patch.json --output revised.chemvas
chemvas check-layout revised.chemvas
chemvas render-document revised.chemvas --output scheme.svg --width-mm 174
```

`scheme.json`에는 원자, 결합, 화살표, 노트를 적습니다. `patch.json`에는 `inspection.json`의 `source_sha256`과 적용할 연산을 적습니다. 각 명령은 새 파일에 쓰고 기존 파일은 덮어쓰지 않으며, `check-layout`은 경고를 찾으면 종료 코드 1을 반환합니다. 형식과 그림이 있는 예제는 [에이전트 CLI 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md)에 있습니다.

## 빠른 시작: 데스크톱 앱에서

![Chemvas 따라 그리기: 구조 삽입, 화살표 라벨 작성, 반응식 정렬, SVG 출력](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

1. **Ring** 도구(`J`)로 왼쪽 캔버스에 벤젠을 놓습니다. **Bond**(`X`)로 고리 원자에서 결합을 하나 끌어 새 탄소를 만든 뒤, 그 탄소에서 말단 원자까지 두 번째 결합을 끌어 냅니다. 말단 원자 위에서 `o`를 누른 뒤 **Enter**로 라벨을 `OH`로 바꿉니다.
2. 오른쪽에도 벤젠을 놓습니다. 고리 원자에서 결합을 하나 끌어 새 탄소를 만든 뒤, 그 탄소에서 말단 원자까지 두 번째 결합을 끌어 냅니다. 두 번째 결합 위에서 `2`를 눌러 그 결합만 이중결합으로 바꾸고, 말단 원자 위에서 `o`를 누릅니다. **Arrow** 도구로 두 구조 사이를 드래그하고, 화살표를 더블클릭해 반응 조건을 입력합니다.
3. **Edit ▸ Select All**로 전체를 선택하고 **Edit ▸ Align ▸ Middle**로 가운데 정렬합니다.
4. `.chemvas`로 저장하고, **File ▸ Export Figure…** 메뉴에서 **Plain SVG**와 **Fit 2-column (174 mm)** 옵션을 선택해 출력합니다.

자세한 튜토리얼과 예제 파일은 [단계별 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.ko.md)를 참고하세요.

## 문서 및 가이드

- [브라우저 어댑터](https://github.com/dhsohn/Chemvas/blob/main/docs/WEB_ADAPTER.ko.md): 소스 체크아웃에서 실행할 수 있는 실험적 웹 편집기(`chemvas --ui web`). 배포용 wheel 및 sdist 패키지에는 포함되지 않는다. 웹 소스는 향후 Leaf 연동을 위한 실험적 코드이며, 독립적인 웹 제품으로 출시되지 않는다.

- [헤드리스 & 에이전트 CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md) · [논문 그림 작성 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md) · [반응 도식 배치](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.ko.md)
- [그리기 도구 및 단축키](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md) · [MOL 입출력](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md#화학-입출력) · [이미지 객체](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.ko.md) · [문서 호환성 정책](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.ko.md)
- [예제 모음](https://github.com/dhsohn/Chemvas/tree/main/examples): 샘플 `.chemvas` 문서와 논문 그림을 만드는 스크립트.
- [기여 안내](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.ko.md) · [아키텍처](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) · [보안 정책](https://github.com/dhsohn/Chemvas/blob/main/SECURITY.ko.md) · [변경 이력](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [릴리스](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.ko.md) · [라이선스 (MIT)](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

문의 및 버그 제보: [GitHub Issues](https://github.com/dhsohn/Chemvas/issues).

## 만든 방식

저는 프로그래머가 아니라 화학자입니다. 이 저장소의 코드는 AI 코딩 에이전트가 작성합니다.
저는 Chemvas가 무엇을 해야 하는지 정하고, 구조에 관한 결정을
[설계 결정 기록(ADR)](https://github.com/dhsohn/Chemvas/tree/main/docs/adr)으로 남기고,
저장된 그림은 문서로 정한 [호환성 정책](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.ko.md)으로
보호하며, 변경이 병합되기 전에 통과해야 할 검사를 정합니다.

코드를 한 줄씩 리뷰하지 않기 때문에, 변경은 에이전트의 "동작한다"는 보고가 아니라 증거로
받아들입니다.

- `make check`가 lint, 포맷, 타입 검사를 실행한 뒤, Qt 상태가 다음 파일로 새지 않도록 테스트
  파일마다 별도 프로세스로 실행합니다. CI도 같은 방식으로 파일별로 실행합니다.
- Chemvas는 `machine.json`을 쓰지 않습니다. 계산 핸드오프와 프로젝트 로컬 관측
  스냅샷은 화학 백엔드와 함께 제거되었습니다
  ([ADR 0035](https://github.com/dhsohn/Chemvas/blob/main/docs/adr/0035-retire-rdkit-chemistry-provider.md)).
  다른 프로젝트가 provider를 채택하는지는 이 저장소 밖의 결정입니다.
- 문서 형식, 실행 취소와 롤백, 그림 출력처럼 영향이 큰 변경은 별도 에이전트가 독립적으로
  적대적 리뷰를 합니다.
