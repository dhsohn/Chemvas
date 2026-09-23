# 예제

[English](README.md)

샘플 반응식, 시작 예제 파일, 재현 가능한 출판용 레시피입니다.

## 출판 그림 갤러리

모든 샘플 PNG 그림은 600 DPI로 출력되었습니다.

### 분자 쌍
베이스라인이 정렬된 캡션과 첨자 식별자를 포함한 두 아니솔 구조입니다. [PNG 다운로드](publication-pair.png).

![Two anisole drawings with aligned captions](publication-pair.png)

### 독립적인 분자 파트
단일 캡션을 공유하며 독립적으로 정렬된 두 분자 파트입니다. [PNG 다운로드](publication-independent-parts.png).

![Independently aligned molecular parts with a shared caption](publication-independent-parts.png)

### 두 행 비교
일관된 열 너비와 라벨 화살표를 갖춘 두 줄 반응식입니다. [PNG 다운로드](publication-comparison.png).

![Two symbolic input-output rows with aligned columns](publication-comparison.png)

이 그림들을 직접 생성하거나 수정하려면 [출판 그림 레시피](../docs/PUBLICATION_SCHEMES.ko.md)를 참고하세요.

## 시작하기

[first-scheme.chemvas](first-scheme.chemvas)를 **File ▸ Open**으로 열어 바로 편집해 볼 수 있습니다.
[따라 그리기](../docs/FIRST_SCHEME.ko.md) · [English](../docs/FIRST_SCHEME.md) · [SVG](first-scheme.svg) · [PNG](first-scheme.png).

- 기본 그리기, 편집 및 내보내기는 별도 의존성 없이 지원됩니다.
- SMILES 삽입 단계를 재현하려면 선택적 RDKit(`pip install "chemvas[rdkit]"`)이 필요합니다.
