# 데모와 브랜딩 미디어

[English](README.md)

소개는 [first-scheme.chemvas](../../examples/first-scheme.chemvas)에서 실제로 출력한
그림으로 시작하고, 데스크톱 작업 흐름의 짧은 워크스루가 뒤따릅니다. 이 예제는
도식적 그리기 연습이며 실험 결과가 아닙니다.

| 자산 | 출처와 용도 |
| --- | --- |
| `examples/first-scheme.png` | 300 DPI, 174 mm PNG 출력. README의 완성 결과. |
| `examples/first-scheme.svg` | 174 mm 프리셋의 일반 SVG. 원자/화살표 라벨은 윤곽선이며 원본 문서는 내장하지 않음. |
| `demo.gif` | 실제 Qt UI/캔버스 프레임에 장(章) 자막과 편집한 멈춤을 더한 것. |
| `demo.png` | 앱에서 완성한 그림의 정지 화면. |
| `walkthrough-drawing.gif` | 레퍼런스 워크스루: 드래그로 결합, 결합 차수·원소 단축키, 전하, 융합된 벤젠 고리. |
| `walkthrough-arrows.gif` | 레퍼런스 워크스루: 반응·평형·곡선 화살표, 화살표 라벨 대화상자, 스냅 연결선이 있는 Line 도구 반응 프로파일. |
| `walkthrough-editing.gif` | 레퍼런스 워크스루: 이동, 노브 회전, 뒤집기, 정렬, 분배. |
| `walkthrough-chemistry.gif` | 레퍼런스 워크스루: molfile 열기, Molecule Info, MOL과 3D XYZ 내보내기(RDKit). |
| `walkthrough-images.gif` | 이미지 객체 워크스루: 합성 PNG 삽입, 이동, Image Properties에서 크기 조절과 밝게 하기. |
| `walkthrough-arrange.gif` | 반응식 배치 워크스루: 구조와 캡션 그룹화, Edit ▸ Arrange Scheme…, 정렬된 한 행. |
| `cli-*.png` | CLI 안내와 반응식 배치 그림: 문서화된 예제 명령을 작은 합성 입력에 실행하고 `render-document`로 렌더링한 것(compose, insert-template, apply-patch 전/후, layout-document arrange, align-y, wrap 전/후). |
| `publication-*.png` | `examples/publication_scheme.py`(`pair`, `independent-parts`)와 `examples/publication_comparison.py`(`comparison`)의 최종 PNG. |
| `banner.png` | 기존 Chemvas 마크와 새 태그라인을 1360×270으로 렌더링. |
| `social-preview.png` | 실제 예제 SVG를 담은 1280×640 공유 카드. |

## 워크스루 재생성

선택적 RDKit 백엔드가 있는 저장소 개발 환경을 씁니다.

```bash
python -m pip install -e ".[dev,rdkit]"
QT_QPA_PLATFORM=offscreen python scripts/capture_first_scheme.py --output-dir /tmp/chemvas-demo-capture
```

빈 출력 디렉터리를 고르세요. 스크립트는 비어 있지 않은 디렉터리를 거부하고 임시
앱 데이터/설정/캐시 프로필을 씁니다. 기존 사용자 문서를 열거나 세션 복구를
시작하지 않습니다. Ring 도구를 고르고 옵션 바의 SMILES 컨트롤로 두 구조를 삽입한
뒤 각 선택을 회전하고, 실제 원자 라벨·화살표 라벨 대화상자를 열고, 반응식을
정렬하고, 문서를 저장하고, 데스크톱 그림 출력 서비스로 출력합니다. 출력 옵션
대화상자는 실제 것이고, 사용자의 파일 선택기를 녹화하지 않도록 출력 경로는
스크립트가 제공합니다. 생성된 SVG의 끝 공백은 저장소 위생을 위해 제거되며, 그림의
요소, 속성, 글리프 경로는 바뀌지 않습니다.

워크스루는 원자 라벨 동작을 직접 호출합니다. 이는 합성 전역 포인터 이동을 거부할
수 있는 Wayland에서도 동작합니다. 튜토리얼은 사용자의 hover-and-Enter 단축키를
설명합니다. 커밋된 캡처는 offscreen으로 만들었고, Wayland 실행도 캡처 환경에서
완료되어 동일한 편집 가능 문서를 만들었습니다. Windows나 macOS 인수 주장은
아닙니다.

자막과 커서 강조는 캡처한 UI 프레임 주변/위에 더한 것입니다. 멈춤은 읽기 쉽게
편집했으므로 GIF는 속도 측정이 아닙니다. Qt, 글꼴, 디스플레이 배율, RDKit 버전이
출력을 바꿀 수 있습니다. 커밋된 파일은 검토한 캡처이지 기계 간 바이트 재현
보장이 아닙니다.

출력을 검토한 뒤 다섯 파일을 각 목적지로 복사합니다.

```bash
cp /tmp/chemvas-demo-capture/first-scheme.chemvas examples/first-scheme.chemvas
cp /tmp/chemvas-demo-capture/first-scheme.svg examples/first-scheme.svg
cp /tmp/chemvas-demo-capture/first-scheme.png examples/first-scheme.png
cp /tmp/chemvas-demo-capture/demo.gif docs/images/demo.gif
cp /tmp/chemvas-demo-capture/demo.png docs/images/demo.png
```

새 출력 경로를 써서 저장된 그림과 명령줄 렌더링을 확인합니다.

```bash
chemvas inspect-document examples/first-scheme.chemvas
chemvas check-layout examples/first-scheme.chemvas
chemvas render-document examples/first-scheme.chemvas --output /tmp/first-scheme-check.svg
```

명령줄 렌더링은 프리셋 결합 길이 크기를 씁니다. 예제 SVG와 PNG는 데스크톱 출력의
174 mm 설정을 씁니다.

예제 SVG는 윤곽선 처리된 화살표 라벨을 담아 캔버스의 글리프 모양과 위·아래 첨자
위치를 보존합니다. 공유 카드는 이 SVG를 직접 렌더링하며 출력을 고치지 않습니다.
SVG는 출력기가 명목상 174 mm 프리셋을 반올림한 뒤 너비 173.919 mm를 기록합니다.

## 레퍼런스 워크스루 재생성

네 개의 `walkthrough-*.gif`는 첫 반응식과 같은 하네스
([walkthrough_capture.py](../../scripts/walkthrough_capture.py))에서 GIF마다 주제
하나씩 나옵니다.

```bash
QT_QPA_PLATFORM=offscreen python scripts/capture_walkthroughs.py --output-dir /tmp/chemvas-walkthroughs
```

`--topic drawing|arrows|editing|chemistry|images|arrange`는 그중 하나만 다시
만듭니다. images 주제는 **File ▸ Insert Image…**가 파일 선택기 뒤에 호출하는 것과
같은 함수로 합성 스펙트럼을 삽입하고, arrange 주제는 카메라 밖에서 그룹화된 구조
두 개를 만든 뒤 실제 Arrange Scheme 대화상자를 조작합니다. editing, chemistry,
arrange 주제는 SMILES로 구조를 놓으므로 선택적 RDKit 백엔드가 필요합니다.
chemistry 주제는 추가로 출력 디렉터리에 아스피린 molfile을 쓰고, **File ▸ Open**과
같은 방식으로 열고, 메뉴 동작이 호출하는 것과 같은 서비스로 Molecule Info 창과
MOL·XYZ 내보내기를 조작하며, 출력 경로는 파일 선택기 대신 스크립트가 제공합니다.
검토한 GIF를 `docs/images/`로 복사하세요.

## CLI와 출판 그림 재생성

```bash
QT_QPA_PLATFORM=offscreen python scripts/render_doc_figures.py --output-dir /tmp/chemvas-doc-figures
```

스크립트는 문서화된 예제 입력을 `work/`에 쓰고, 안내서에 보이는 그대로 공개
명령을 실행하고, 결과를 `render-document`로 300 dpi에 렌더링하고, 두 출판 예제를
실행한 뒤 그림을 `figures/`에 남깁니다. 검토한 뒤 `figures/*.png`를
`docs/images/`로 복사하세요. RDKit은 필요 없으며, 한 환경에서 반복 실행하면
바이트 동일한 PNG가 나옵니다.

## 브랜딩 재생성

예제 SVG를 갱신한 뒤:

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_branding_images.py
```

[브랜딩 스크립트](../../scripts/generate_branding_images.py)는 기존 마크를 재사용하고
예제 SVG를 읽습니다. 화학을 다시 그리지 않습니다.

`social-preview.png`는 **GitHub ▸ Settings ▸ General ▸ Social preview**에서 따로
올려야 합니다. 커밋해도 저장소에 설정된 공유 이미지는 바뀌지 않습니다. 앱
아이콘은 `app/chemvas/assets/icon/`에 그대로 있습니다.

패키지 요약은 [pyproject.toml](../../pyproject.toml)에 있습니다. GitHub About 설명은
별도 설정이며, 대응하는 문구는 다음과 같습니다.

> An open-source desktop canvas for chemical structures and reaction schemes,
> with publication-ready export and scriptable document workflows.

README와 문서 링크는 게시 후 PyPI에서도 동작하도록 `main` URL을 씁니다. 새 미디어와
튜토리얼 URL은 이 파일들이 GitHub의 `main`에 도달하면 쓸 수 있게 됩니다. PyPI의
긴 설명은 다음 패키지 릴리스와 함께 갱신됩니다.
