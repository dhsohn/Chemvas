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

Chemvas는 연구자와 자동화 스크립트가 함께 편집할 수 있는 **오픈소스 화학 구조 드로잉 애플리케이션**입니다. 데스크톱 캔버스에서 직관적으로 그리고, 전용 CLI를 통해 헤드리스로 편집하거나 검사하며, 작업 결과물을 언제든 다시 열어 자유롭게 편집할 수 있습니다.

## 주요 기능

- **직관적인 캔버스 드로잉**: 화학 구조 스케치, SMILES 즉시 삽입, 반응 화살표 및 조건 라벨링, 정렬 기능을 제공하며 자동 저장과 세션 복구를 지원합니다.
- **헤드리스 자동화 및 CLI**: GUI 창을 띄우지 않고도 원자 ID 검사, 반응식 배치 검증, 프로그래밍 방식의 패치 적용, 논문 규격 렌더링이 가능합니다.
- **논문 출판용 고품질 출력**: 논문 컬럼 규격(예: 82 mm, 174 mm)에 맞춰 벡터(SVG, PDF) 및 래스터(PNG, TIFF) 그림을 정확한 물리 크기로 내보낼 수 있습니다.
- **신뢰할 수 있는 문서 형식**: 저장된 `.chemvas` 파일은 사람이 읽고 수정할 수 있는 표준 JSON 형식(version 8, schema 1)입니다. 자세한 내용은 [문서 호환성 정책](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.ko.md)을 참고하세요.

## 설치

**Python 3.12+**가 필요합니다.

SMILES 삽입, 분자 물성 조회, 3D XYZ 출력, 구조 기반 추천, `pack-step` 등 화학 정보학 기능을 사용하려면 RDKit 백엔드를 함께 설치하세요.

```bash
pip install "chemvas[rdkit]"
chemvas
```

기본 그리기와 문서 편집, 그림 출력만 사용할 경우 RDKit 없이 설치할 수 있습니다:

`pip install chemvas`

Windows 로컬 빌드 및 패키징은 [패키징 안내](https://github.com/dhsohn/Chemvas/blob/main/packaging/windows/README.ko.md)를 참고하세요.

## 빠른 시작: 첫 반응식 그리기

![Chemvas 따라 그리기: 구조 삽입, 화살표 라벨 작성, 반응식 정렬, SVG 출력](https://raw.githubusercontent.com/dhsohn/Chemvas/main/docs/images/demo.gif)

1. 툴바 아래 SMILES 입력란에 `OCc1ccccc1`을 입력하고 **Insert**를 누른 뒤 캔버스를 클릭합니다. 산소 원자 위에 마우스를 올리고 **Enter**를 눌러 라벨을 `OH`로 변경합니다.
2. 오른쪽에 `O=Cc1ccccc1`도 같은 방식으로 삽입합니다. **Arrow** 도구로 두 구조 사이를 드래그하고, 화살표를 더블클릭해 반응 조건을 입력합니다.
3. **Edit ▸ Select All**로 전체를 선택하고 **Edit ▸ Align ▸ Middle**로 가운데 정렬합니다.
4. `.chemvas`로 저장하고, **File ▸ Export Figure…**에서 **Plain SVG**, **Fit 2-column (174 mm)**를 선택해 출력합니다.

자세한 튜토리얼과 예제 파일은 [단계별 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/FIRST_SCHEME.ko.md)를 참고하세요.

## 스크립트 및 CLI

터미널에서 직접 문서를 검사하고 렌더링할 수 있습니다:

```bash
chemvas inspect-document first-scheme.chemvas
chemvas check-layout first-scheme.chemvas
chemvas render-document first-scheme.chemvas --output first-scheme.pdf --width-mm 174
```

다양한 CLI 활용법은 [에이전트 CLI 안내](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md), [반응 도식 배치](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.ko.md), [논문 그림 작성 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md)를 참고하세요.

## 문서 및 가이드

- [그리기 도구 및 단축키](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md) · [화학 입출력](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md#화학-입출력) · [이미지 객체](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.ko.md)
- [계산 전달 (RDKit)](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md#계산-상태와-기본-단계): 반응 단계별 성분을 임베딩하여 `machine.json`으로 내보냅니다.
- [예제 모음](https://github.com/dhsohn/Chemvas/tree/main/examples): 샘플 `.chemvas` 문서 (version 8, schema 1).
- [기여 안내](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.ko.md) · [아키텍처](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) · [변경 이력](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [릴리스](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.ko.md) · [라이선스 (MIT)](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

문의 및 버그 제보: [GitHub Issues](https://github.com/dhsohn/Chemvas/issues).
