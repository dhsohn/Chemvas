# 데모와 브랜딩 미디어

[English](README.md)

README, 가이드 문서 및 소셜 프리뷰에 사용되는 미디어 자산 목록입니다.

| 자산 | 출처 및 용도 |
| --- | --- |
| `examples/first-scheme.png` | 300 DPI, 174 mm PNG 출력본 (README 완성 예시) |
| `examples/first-scheme.svg` | 윤곽선 폰트가 적용된 174 mm 규격 표준 SVG |
| `demo.gif` | 기능별 캡션이 포함된 Qt UI 워크스루 애니메이션 |
| `demo.png` | 완성된 캔버스 작업 공간 스크린샷 |
| `walkthrough-drawing.gif` | 드로잉 레퍼런스: 결합 그리기, 단축키, 전하 및 축합 고리 |
| `walkthrough-arrows.gif` | 화살표 레퍼런스: 반응, 평형, 곡선 화살표 및 반응 경로 프로파일 |
| `walkthrough-editing.gif` | 편집 레퍼런스: 이동, 회전, 뒤집기, 정렬 및 균등 분배 |
| `walkthrough-chemistry.gif` | 화학 기능: molfile 불러오기, Molecule Info 패널, 3D XYZ 내보내기 |
| `walkthrough-images.gif` | 이미지 객체: PNG 이미지 삽입, 크기 조정 및 속성 변경 |
| `walkthrough-arrange.gif` | 레이아웃: 분자-캡션 그룹화 및 반응식 자동 정렬 |
| `cli-*.png` | CLI 명령 및 배치 기능 시각화 예시 이미지 |
| `examples/publication-*.png` | 예제 갤러리에 사용되는 고해상도 출판용 그림 |
| `banner.png` | Chemvas 로고 배너 (1360×270) |
| `social-preview.png` | 저장소 공유용 소셜 미리보기 카드 (1280×640) |

## 워크스루 애니메이션 재생성

메인 데모 워크스루 캡처:

```bash
python -m pip install -e ".[dev,rdkit]"
QT_QPA_PLATFORM=offscreen python scripts/capture_first_scheme.py --output-dir /tmp/chemvas-demo-capture
```

생성된 파일 복사:

```bash
cp /tmp/chemvas-demo-capture/first-scheme.chemvas examples/first-scheme.chemvas
cp /tmp/chemvas-demo-capture/first-scheme.svg examples/first-scheme.svg
cp /tmp/chemvas-demo-capture/first-scheme.png examples/first-scheme.png
cp /tmp/chemvas-demo-capture/demo.gif docs/images/demo.gif
cp /tmp/chemvas-demo-capture/demo.png docs/images/demo.png
```

문서 검사 및 헤드리스 렌더링 확인:

```bash
chemvas inspect-document examples/first-scheme.chemvas
chemvas check-layout examples/first-scheme.chemvas
chemvas render-document examples/first-scheme.chemvas --output /tmp/first-scheme-check.svg
```

## 기능별 워크스루 재생성

개별 기능별 애니메이션 생성 (`--topic drawing|arrows|editing|chemistry|images|arrange`):

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_walkthroughs.py --output-dir /tmp/chemvas-walkthroughs
```

## CLI 및 출판용 그림 재생성

CLI 다이어그램 및 출판용 그림 생성:

```bash
QT_QPA_PLATFORM=offscreen python scripts/render_doc_figures.py --output-dir /tmp/chemvas-doc-figures
```

생성된 이미지 복사:

```bash
cp /tmp/chemvas-doc-figures/figures/cli-*.png docs/images/
cp /tmp/chemvas-doc-figures/figures/publication-*.png examples/
```

## 브랜딩 이미지 재생성

배너 및 소셜 프리뷰 이미지 재생성:

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_branding_images.py
```
