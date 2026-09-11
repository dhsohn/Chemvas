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
데스크톱에서 그리고, 논문 단 너비 그대로 SVG·PDF·PNG·TIFF로 출력하고,
같은 문서를 스크립트로도 다룰 수 있습니다.

## 설치

**Python 3.12+**가 필요합니다. SMILES 삽입, Molecule Info(분자식·식별자),
3D XYZ 출력, 약어 라벨을 포함한 MOL 출력, **Suggest by structure**와
`generate-precomplex` / `select-precomplex` / `pack-step`에는 선택적 RDKit
백엔드가 필요합니다.

```bash
pip install "chemvas[rdkit]"
chemvas
```

`pip install chemvas`는 RDKit을 뺀 설치입니다. 그리기, `.chemvas` 저장·열기,
그림 출력(편집 가능한 SVG를 포함한 SVG/PDF/PNG/TIFF), 일반 MOL 가져오기·내보내기는
그대로 사용할 수 있습니다.
Windows 로컬 빌드는 [패키징 안내](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.ko.md)를 보세요.

## 첫 반응식 만들기

![Chemvas 따라 그리기: 구조 삽입, 화살표 라벨 작성, 반응식 정렬, SVG 출력](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

1. **Ring** 도구를 고르고 SMILES 입력란에 `OCc1ccccc1`을 넣은 뒤 **Insert**를
   누르고 캔버스를 클릭하세요. 산소 위에 포인터를 두고 **Enter**를 눌러 `OH`로
   바꾸세요.
2. 오른쪽에 `O=Cc1ccccc1`도 삽입하세요. **Arrow** 도구로 두 구조 사이를
   드래그하고, 화살표를 더블클릭해 라벨을 적으세요.
3. **Edit ▸ Select All** 뒤 **Edit ▸ Align ▸ Middle**.
4. `.chemvas`로 저장하고 **File ▸ Export Figure…**에서 **Plain SVG**,
   **Fit 2-column (174 mm)**를 고르세요.

라벨 입력값과 예제 파일은 [단계별 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.ko.md)에
있습니다. 이 그림은 연습용 도식이며 실험 결과가 아닙니다.

## 스크립트

내려받은 `first-scheme.chemvas`가 있는 폴더에서:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme.pdf --width-mm 174
```

출력은 새 파일을 만들며 원본은 건드리지 않습니다. 문서 구성·Graph Patch·
반응식 배치와 그 한계는
[문서 CLI 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md) ·
[반응 도식 배치](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.ko.md) ·
[논문 그림 작성 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md)를 보세요.

## 문서

- [그리기 도구·단축키](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md) ·
  [화학 입출력](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md#화학-입출력) ·
  [이미지 객체](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.ko.md) ·
  [현재 제한·로드맵](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md#로드맵--아직-지원하지-않는-것)
- [계산 전달 (RDKit)](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md#계산-상태와-기본-단계): 반응 단계와 검토한 반응 전 복합체를 단계별 `machine.json`으로 내보냅니다.
- 문서는 편집 가능한 `.chemvas` JSON 파일(version 7)입니다.
  [다른 예제](https://github.com/dhsohn/Chemvas/tree/main/examples)
- [기여 안내](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.ko.md) ·
  [아키텍처](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) ·
  [변경 이력](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) ·
  [릴리스](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.ko.md) ·
  [MIT License](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

불편한 점이 있었다면 [이슈로 알려주세요](https://github.com/dhsohn/Chemvas/issues).
