# 데모와 브랜딩 미디어

[English](README.md)

README, 가이드 문서 및 소셜 프리뷰에 사용되는 미디어 자산 목록입니다.

GIF 6개와 `demo.png`는 2026-10-25에 Chemvas 0.27.1, PyQt/Qt 6.11.0,
macOS arm64의 Qt offscreen 백엔드로 다시 캡처했습니다. 합성 그림과 스크립트 입력으로
현재 앱의 실제 위젯을 조작하고, 캡처한 창 위에 설명을 붙였습니다. 모든 OS에서
최근 파일과 복구 데이터를 임시 프로필로 격리합니다. 이 영상은 사용 안내이며
네이티브 설치 프로그램 검증 결과는 아닙니다.

| 자산 | 출처 및 용도 |
| --- | --- |
| `examples/first-scheme.png` | 300 DPI, 174 mm PNG 출력본 (README 완성 예시) |
| `examples/first-scheme.svg` | 윤곽선 폰트가 적용된 174 mm 규격 표준 SVG |
| `demo.gif` | 기능별 캡션이 포함된 Qt UI 워크스루 애니메이션 |
| `demo.png` | 완성된 캔버스 작업 공간 스크린샷 |
| `walkthrough-drawing.gif` | 드로잉 레퍼런스: 결합 그리기, 단축키, 전하 및 축합 고리 |
| `walkthrough-arrows.gif` | 화살표 레퍼런스: 반응, 평형, 곡선 화살표 및 반응 경로 프로파일 |
| `walkthrough-editing.gif` | 편집 레퍼런스: 이동, 회전, 뒤집기, 정렬 및 균등 분배 |
| `walkthrough-chemistry.gif` | 현재 MOL 가져오기와 선택한 명시적 원자의 V2000 내보내기 |
| `walkthrough-images.gif` | 이미지 객체: PNG 이미지 삽입, 크기 조정 및 속성 변경 |
| `cli-*.png` | CLI 명령 및 배치 기능 시각화 예시 이미지 |
| `examples/publication-*.png` | 예제 갤러리에 사용되는 고해상도 출판용 그림 |
| `banner.png` | Chemvas 로고 배너 (1360×270) |
| `social-preview.png` | 저장소 공유용 소셜 미리보기 카드 (1280×640) |

## 워크스루 애니메이션 재생성

메인 데모 워크스루 캡처:

```bash
python -m pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen PYTHONPATH=app python scripts/capture_first_scheme.py --output-dir /tmp/chemvas-demo-capture
```

실행할 때마다 새 빈 출력 디렉터리를 사용합니다. 파일을 교체하기 전에 화살표 라벨의
서식, 빠진 결합선이 없는지, 출력 미리보기 화면을 확인합니다. 메인 데모는 Ring·Bond
도구로 구조를 그리고, `MnO2`의 `2`를 선택해 **Subscript x₂**를 적용합니다.
편집용 CDXML을 저장한 뒤 제출용 그림을 내보냅니다.
두 벤젠고리는 반듯하게 유지하고, 곁사슬은 같은 30° 지그재그 방향으로 그려
히드록실 라벨이 가로로 읽히게 합니다.

생성된 파일 복사:

```bash
cp /tmp/chemvas-demo-capture/first-scheme.cdxml examples/first-scheme.cdxml
cp /tmp/chemvas-demo-capture/first-scheme.svg examples/first-scheme.svg
cp /tmp/chemvas-demo-capture/first-scheme.png examples/first-scheme.png
cp /tmp/chemvas-demo-capture/demo.gif docs/images/demo.gif
cp /tmp/chemvas-demo-capture/demo.png docs/images/demo.png
```

문서 검사 및 헤드리스 렌더링 확인:

```bash
chemvas inspect-document examples/first-scheme.cdxml
chemvas check-layout examples/first-scheme.cdxml
chemvas render-document examples/first-scheme.cdxml --output /tmp/first-scheme-check.svg
```

## 기능별 워크스루 재생성

개별 기능별 애니메이션 생성 (`--topic drawing|arrows|editing|chemistry|images`):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=app python scripts/capture_walkthroughs.py --output-dir /tmp/chemvas-walkthroughs
cp /tmp/chemvas-walkthroughs/walkthrough-*.gif docs/images/
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
