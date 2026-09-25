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

Chemvas는 직관적인 반응식 작성과 출판용 그림 제작을 위한 **오픈소스 화학 구조 드로잉 애플리케이션**입니다. 데스크톱 캔버스에서 화학 구조를 스케치하고, SMILES를 삽입하고, 반응식을 정렬하여 논문 규격에 맞는 고품질 그림으로 내보낼 수 있습니다.

## 주요 기능

- **직관적인 캔버스 드로잉**: 화학 구조 스케치, SMILES 즉시 삽입, 반응 화살표 및 조건 라벨링, 정렬 기능을 제공하며 자동 저장과 세션 복구를 지원합니다.
- **논문 출판용 고품질 출력**: 논문 컬럼 규격(예: 82 mm, 174 mm)에 맞춰 벡터(SVG, PDF) 및 래스터(PNG, TIFF) 그림을 정확한 물리 크기로 내보낼 수 있습니다.
- **화학 정보학 및 3D 미리보기**: 분자 물성 확인, 대화형 3D 구조 회전, XYZ 좌표 내보내기 기능을 선택적 RDKit 백엔드를 통해 제공합니다.
- **신뢰할 수 있는 문서 형식**: 저장된 `.chemvas` 파일은 사람이 읽고 수정할 수 있는 표준 JSON 형식(version 8, schema 1)입니다. 자세한 내용은 [문서 호환성 정책](https://github.com/dhsohn/Chemvas/blob/main/docs/DOCUMENT_COMPATIBILITY.ko.md)을 참고하세요.

## 설치

**Python 3.12+**가 필요합니다.

SMILES 삽입, 분자 물성 조회, 3D XYZ 출력 등 화학 정보학 기능을 사용하려면 RDKit 백엔드를 함께 설치하세요:

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

## 문서 및 가이드

- [그리기 도구 및 단축키](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md) · [화학 입출력](https://github.com/dhsohn/Chemvas/blob/main/docs/REFERENCE.ko.md#화학-입출력) · [이미지 객체](https://github.com/dhsohn/Chemvas/blob/main/docs/IMAGE_OBJECTS.ko.md)
- [계산 전달 (RDKit)](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md#계산-상태와-기본-단계): 반응 단계별 성분을 임베딩하여 `machine.json`으로 내보냅니다.
- [헤드리스 & 에이전트 CLI](https://github.com/dhsohn/Chemvas/blob/main/docs/AGENT_CLI.ko.md) · [반응 도식 배치](https://github.com/dhsohn/Chemvas/blob/main/docs/SCHEME_LAYOUT.ko.md) · [논문 그림 작성 예제](https://github.com/dhsohn/Chemvas/blob/main/docs/PUBLICATION_SCHEMES.ko.md)
- [예제 모음](https://github.com/dhsohn/Chemvas/tree/main/examples): 샘플 `.chemvas` 문서 (version 8, schema 1).
- [기여 안내](https://github.com/dhsohn/Chemvas/blob/main/CONTRIBUTING.ko.md) · [아키텍처](https://github.com/dhsohn/Chemvas/blob/main/docs/ARCHITECTURE.ko.md) · [변경 이력](https://github.com/dhsohn/Chemvas/blob/main/CHANGELOG.md) · [릴리스](https://github.com/dhsohn/Chemvas/blob/main/RELEASING.ko.md) · [라이선스 (MIT)](https://github.com/dhsohn/Chemvas/blob/main/LICENSE)

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
- `machine.json` 출력은 공통 [machine-contracts](https://github.com/dhsohn/machine-contracts)
  validator로 검증합니다. validator가 없으면 조용히 통과하지 않고 실패합니다.
- 문서 형식, 실행 취소와 롤백, 그림 출력처럼 영향이 큰 변경은 별도 에이전트가 독립적으로
  적대적 리뷰를 합니다.
