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

Chemvas는 **분자 구조와 반응식을 그리고, 논문에 넣을 그림으로 내보내는 오픈소스 데스크톱 앱**입니다. 캔버스에서 직접 그리거나 스크립트로 여러 그림을 같은 축척에 맞출 수 있습니다. 편집 원본은 `.cdxml`로 저장하고, 제출할 그림은 SVG·PDF·PNG로 내보냅니다.

![Chemvas에서 구조를 그리고, 화살표에 조건을 적고, 반응식을 정렬하는 과정](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

## 그리기부터 논문 그림까지

- **구조와 반응식 그리기.** 고리, 결합, 반응 화살표와 라벨을 캔버스에 배치하고 정렬합니다. 자동 저장과 세션 복구로 작업을 이어갈 수 있습니다.
- **원본을 고쳐 다시 출력하기.** 지원되는 단일 페이지 CDXML을 열어 편집하고 저장합니다. 그림은 84 mm·174 mm 같은 논문 단 너비에 맞춰 내보낼 수 있습니다.
- **여러 그림의 축척 맞추기.** [논문 그림 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md)는 결합 길이와 글자 크기를 고정해 원고 전체에 쓸 그림을 만듭니다.
- **스크립트로 반복 작업 줄이기.** 문서 생성·검사·패치·출력을 명령줄에서 실행합니다. `check-layout`은 일부 라벨 충돌과 용지 밖 요소를 찾아 줍니다. 검사 범위와 패치 형식은 [CLI 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md)에 있습니다.

## 설치

macOS, Windows, Linux에서 **Python 3.12 이상**으로 실행합니다.

```bash
pip install chemvas
chemvas
```

Windows 실행 파일을 직접 만들려면 [패키징 안내](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.ko.md)를 따르세요.

## 첫 반응식 그리기

1. **Ring** 도구(`J`)로 왼쪽 캔버스에 벤젠을 놓습니다. **Bond**(`X`)로 고리 원자에서 결합을 하나 끌어 새 탄소를 만든 뒤, 그 탄소에서 말단 원자까지 두 번째 결합을 끌어 냅니다. 말단 원자 위에서 `o`를 누른 뒤 **Enter**로 라벨을 `OH`로 바꿉니다.
2. 오른쪽에도 벤젠을 놓습니다. 고리 원자에서 결합을 하나 끌어 새 탄소를 만든 뒤, 그 탄소에서 말단 원자까지 두 번째 결합을 끌어 냅니다. 두 번째 결합 위에서 `2`를 눌러 그 결합만 이중결합으로 바꾸고, 말단 원자 위에서 `o`를 누릅니다. **Arrow** 도구로 두 구조 사이를 드래그하고, 화살표를 더블클릭해 반응 조건을 입력합니다.
3. **Edit ▸ Select All**로 전체를 선택하고 **Edit ▸ Align ▸ Middle**로 가운데 정렬합니다.
4. `.cdxml`로 저장하고, **File ▸ Export Figure…** 메뉴에서 **Plain SVG**와 **Fit 2-column (174 mm)** 옵션을 선택해 출력합니다.

[첫 반응식 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.ko.md)에는 각 단계와 완성된 예제 파일이 있습니다.

## 스크립트로 편집하고 출력하기

```bash
chemvas compose-document scheme.json --output scheme.cdxml
chemvas inspect-document scheme.cdxml > inspection.json
chemvas apply-patch scheme.cdxml patch.json --dry-run
chemvas apply-patch scheme.cdxml patch.json --output revised.cdxml
chemvas check-layout revised.cdxml
chemvas render-document revised.cdxml --output scheme.svg --width-mm 174
```

`scheme.json`에 원자·결합·화살표·노트를 적고, `patch.json`에 적용할 연산과 `inspection.json`의 `source_sha256`을 담습니다. 패치는 검사한 파일과 바이트가 일치할 때 적용되며, 결과는 새 파일에 저장됩니다. 출력 명령은 기존 파일 덮어쓰기를 거부합니다. `check-layout`이 경고를 찾으면 종료 코드 1을 반환합니다.

패치 검사는 문서 구조를 다룹니다. 원소 기호·원자가와 최종 그림의 화학적 의미는 사용자가 확인합니다. 입력 형식과 실행 예제는 [CLI 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md)를 참고하세요.

## 파일 형식

- **편집 원본:** 지원되는 단일 페이지 `.cdxml`. 외부 파일은 Chemvas 스타일로 표시하며, 중첩 축약 구조·반응 참조·벡터 객체는 원본 XML로 보존합니다. 보존할 수 없는 수정은 저장 전에 거부합니다.
- **구조 가져오기:** 결합 차수 1–3, 쐐기·해시 결합, 전하·라디칼을 포함한 지원 범위의 2D MOL V2000.
- **그림 출력:** SVG·PDF·PNG. SVG는 출력용이며 다시 열어 편집하는 형식은 아닙니다. [CDXML 내보내기](https://github.com/dhsohn/Chemvas/blob/main/docs/CDXML_EXPORT.ko.md)도 지원합니다.
- **미지원 입력:** 바이너리 CDX, 여러 페이지 CDXML, SDF, RXN, 3D 좌표·동위원소·방향족 결합 유형 4·V3000을 쓴 MOL.

자세한 보존 범위는 [문서 호환성](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.ko.md)과 [CDXML 지원 범위](https://github.com/dhsohn/Chemvas/blob/main/docs/adr/0058-desktop-cdxml-documents.md)에 정리되어 있습니다.

## 더 알아보기

- [그리기 도구와 단축키](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md) · [이미지 객체](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.ko.md)
- [논문 그림 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md) · [반응식 배치](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.ko.md) · [예제 파일](https://github.com/dhsohn/Chemvas/tree/main/examples)
- [구조 설계](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) · [기여 안내](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.ko.md) · [보안](https://github.com/dhsohn/Chemvas/blob/main/SECURITY.ko.md) · [변경 이력](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [릴리스](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.ko.md) · [MIT 라이선스](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)
- [브라우저 어댑터](https://github.com/dhsohn/Chemvas/blob/main/docs/WEB_ADAPTER.ko.md): 소스 체크아웃의 `chemvas --ui web`에서 실행하는 실험 기능입니다. 배포 패키지에는 포함되지 않습니다.

사용 중 불편한 점이나 제안은 [GitHub Issues](https://github.com/dhsohn/Chemvas/issues)에 남겨 주세요.

## 만든 방식

저는 화학 연구에서 쓸 도구를 만들고 있습니다. 필요한 기능과 저장 형식, 검증 기준은 제가 정하고, 코드는 AI 코딩 에이전트를 활용해 작성합니다.

설계 결정은 [ADR](https://github.com/dhsohn/Chemvas/tree/main/docs/adr)에, 저장한 그림을 유지하는 규칙은 [문서 호환성 정책](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.ko.md)에 기록합니다. `make check`는 로컬에서 린트·포맷·타입 검사와 파일별 테스트를 실행합니다. GitHub CI는 품질 검사, 패키지 스모크 검사, 비밀정보 검사를 실행합니다.
