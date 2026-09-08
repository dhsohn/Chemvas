<p align="center">
  <img src="https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/banner.png" alt="Chemvas — 직접 그리고, 안전하게 자동화하고, 정확하게 내보내세요." width="680">
</p>

<p align="center">
  <a href="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml"><img src="https://github.com/dhsohn/Chemvas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/chemvas/"><img src="https://img.shields.io/pypi/v/chemvas" alt="PyPI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://github.com/dhsohn/Chemvas/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center"><a href="https://github.com/dhsohn/Chemvas/blob/main/README.md">English</a> · <b>한국어</b></p>

Chemvas는 **화학 구조와 반응식을 그리는 오픈소스 데스크톱 캔버스**입니다.
논문용 그림 출력과 스크립트를 통한 문서 작업을 지원합니다.

![Chemvas에서 직접 출력한 벤질 알코올 산화 반응식](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.png)

[편집 가능한 그림 받기](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.chemvas) ·
[SVG 받기](https://raw.githubusercontent.com/dhsohn/Chemvas/main/examples/first-scheme.svg) ·
[따라 그리기](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.ko.md)

## 직접 그리고, 안전하게 자동화하고, 정확하게 내보내세요.

- **직접 그리기.** 구조를 스케치하거나 SMILES로 삽입하고, 반응 화살표에 조건을
  적고, 분자를 정렬하세요. 편집 가능한 문서에 자동저장·크래시 복구를 지원합니다.
  SMILES 삽입에는 선택적 RDKit 백엔드가 필요합니다.
- **안전하게 자동화하기.** 스크립트로 문서를 구성·검사·출력하세요.
  구조 편집은 원본 파일의 해시를 확인하고 변경안을 검증한 뒤 새 문서로 저장합니다.
- **정확하게 출력하기.** SVG·PDF·PNG·TIFF 출력과 명시적인 물리 크기 프리셋을
  지원합니다. 84 mm·174 mm 논문 단 너비도 선택할 수 있습니다.
  출력한 그림과 함께 편집 가능한 원본 문서를 보관하세요.

## 설치하고 그리기

**Python 3.12+**가 필요합니다. 따라 그리기에 필요한 SMILES 기능을 함께 설치하세요.

```bash
pip install "chemvas[rdkit]"
chemvas
```

RDKit 없이 직접 그리기와 그림 출력만 사용하려면 `pip install chemvas`로 설치하세요.
두 방식 모두 PyQt6가 함께 설치됩니다. 데스크톱 설치 파일은 아직 제공하지 않으며,
현재 배포 방식은 Python 패키지입니다.

## 첫 반응식 만들기

![Chemvas 따라 그리기: 구조 삽입, 화살표 라벨 작성, 반응식 정렬, SVG 출력](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

실제 앱 조작을 짧게 편집한 데모입니다. 그림은 사용법을 보여주는 도식이며
실험 결과를 나타내지 않습니다.

1. SMILES 입력란에 `OCc1ccccc1`을 입력하고 **Insert**를 누른 뒤 캔버스를 클릭하세요.
   산소 위에 포인터를 놓고 **Enter**를 눌러 라벨을 `OH`로 바꾸세요.
2. 오른쪽에 `O=Cc1ccccc1`도 삽입하세요. **Arrow** 도구로 두 구조 사이를
   드래그하고, 화살표를 더블클릭해 라벨을 작성하세요.
3. 반응식을 선택하고 **Edit ▸ Align ▸ Middle**로 정렬하세요.
4. 그림을 `.chemvas`로 저장하세요. **File ▸ Export Figure…**에서 **Plain SVG**와
   **Fit 2-column (174 mm)**를 선택해 출력하세요.

[단계별 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.ko.md)에
라벨 입력값, 예제 파일, 명령줄 출력 방법이 있습니다.
완성된 그림을 열고 출력하는 데에는 RDKit이 필요하지 않습니다.

## 스크립트로 문서 다루기

`first-scheme.chemvas`를 내려받은 폴더에서 다음 명령을 실행해 보세요.

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme-rendered.svg
```

출력 명령은 새 파일을 만들며 원본 그림은 그대로 둡니다.
이 명령은 기본 결합 길이를 기준으로 크기를 정합니다. 위의 다운로드용 SVG는
데스크톱에서 174 mm 단 너비를 선택해 출력했습니다.
현재 레이아웃 검사는 노트·원자 라벨 글자, 도형 경계, 화살표와 구조의 교차를 다루며,
화학 반응식에서 가능한 모든 겹침을 검사하지는 않습니다.

문서 구성·구조 패치·출력 보장과 제한은
[문서 CLI 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md)를 참고하세요.

## 다른 작업과 문서

- **화학 입출력:** SMILES 삽입, MOL 교환, 분자 정보, 3D XYZ 출력.
  일부 기능은 RDKit이 필요합니다.
  [상세 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#chemistry-io)
- **계산 전달 (RDKit):** 반응 단계와 검토한 반응 전 복합체를 단계별 `machine.json`으로 내보냅니다. [상세 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.md#calculation-states-and-elementary-steps)
- **문서:** 편집 가능한 `.chemvas` JSON 파일(version 7).
  [그리기 도구·단축키](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md) ·
  [다른 예제](https://github.com/dhsohn/Chemvas/tree/main/examples) ·
  [현재 제한·로드맵](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.md#roadmap--not-yet-supported)

## 참여하기

예제를 사용해 보고 [불편했던 점을 알려주세요](https://github.com/dhsohn/Chemvas/issues).
문제를 재현하는 작은 그림, 설치 경험, 문서 개선도 좋은 기여입니다.
Chemvas가 유용했다면 스타로 다른 사용자에게 알려주세요.

개발에 참여하려면
[CONTRIBUTING](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.md)을 읽어보세요.
`make check`는 lint·포맷·타입 검사, 파일별로 격리된 테스트,
문서의 계산 전달 형식 검사를 실행합니다.

[아키텍처](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) ·
[변경 이력](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) ·
[릴리스](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.md) ·
[MIT License](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)
