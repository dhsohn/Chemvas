<p align="center">
  <img src="docs/images/banner.png" alt="Chemvas — 2D 화학 구조 드로잉 캔버스" width="680">
</p>

<p align="center"><a href="README.md">English</a> · <b>한국어</b></p>

![Chemvas — Base/THF 반응 스킴과 여러 유기촉매 구조를 그린 캔버스](docs/images/demo.png)

Chemvas는 PyQt6 기반의 2D 화학 구조 드로잉 앱입니다. 분자 구조와 반응 스킴을 빠르게 스케치하고,
SMILES 입력(RDKit 선택)을 통해 구조를 불러와 편집할 수 있습니다. 기본 스타일은 ACS 1996 규격을
따르며, 실험 노트나 논문용 그림의 초안을 빠르게 만들기 위한 도구를 목표로 합니다.

## 개요
- 분자 본드/링/라벨, 화살표, bracket annotation을 한 캔버스에서 조합해 그릴 수 있습니다.
- 선택/이동/플립/퍼스펙티브 회전 등 간단한 변형 작업이 가능합니다.
- 선택된 구조에 대해 분자식/분자량을 표시할 수 있으며(RDKit 필요),
  SMILES로 구조를 불러와 클릭 위치에 배치할 수 있습니다.
- 저장/불러오기(.chemvas JSON)를 지원해 작업 상태를 유지합니다.

## 주요 기능
- 본드 도구: 단/이/삼중 결합, 굵은 결합, 웨지/해시 표현, 30도 각도 스냅과 기본 결합 길이 유지
- 링/템플릿: 벤젠 링, 사이클로알케인, 의자/보트 형태 템플릿 배치
- 화살표: 반응/평형/공명/곡선/점선 화살표, 굵기/헤드 스케일 설정
- Brackets: 대괄호/소괄호/중괄호, dagger(`†`), double dagger(`‡`) annotation 객체
- Figure export: 기본은 원본 Chemvas metadata를 담지 않는 plain SVG/PDF/PNG/TIFF 내보내기입니다.
  글리프를 아웃라인 처리해 화면/벡터/래스터 출력이 어긋나지 않으며, zoom과 무관하게 물리 크기
  (결합 길이 또는 84/174mm 컬럼 폭)를 지정할 수 있습니다. Chemvas로 다시 불러올 editable SVG는
  별도 선택이며 SVG metadata에 원본 문서 payload를 포함합니다.
- 2D -> 3D `.xyz` export: 현재 분자 또는 현재 원자/결합 selection을 RDKit 기반 3D 좌표로 변환해 내보내기
- Molecule Info 창: RDKit 기반 3D preview와 분자식/분자량 표시
- 색상/스타일: ACS 팔레트로 결합/원자/링 색 변경, 링 채움 색상, 본드 길이 조절
- 편집/변형: 선택/이동, 수평/수직 플립, 퍼스펙티브 회전, Undo/Redo
- 자동저장 & 복구: 열려 있는 문서를 수 초마다 스냅샷으로 저장해, 비정상 종료 후에도 다음 실행 시 미저장 작업과
  지난 세션을 자동으로 복원합니다. 미저장 탭에는 `●` 표시가 붙고, File 메뉴에는 **Open Recent**(최근 파일)
  목록이 있으며, 이미 열려 있는 파일을 다시 열면 새 창을 만들지 않고 해당 창으로 전환합니다.

## 설치
- Python 3.12+, PyQt6 필요

```bash
pip install chemvas

# 선택: SMILES/분자식/3D 기능 활성화
pip install "chemvas[rdkit]"
```

- 저장소를 클론해 개발용으로 설치하려면(선택 기능은 `".[rdkit]"` 추가):

```bash
python -m pip install -e .
```

> 단일 파일 데스크톱 바이너리 빌드는 아직 로드맵에 있습니다(아래 참고).

## 사용 방법
- 실행(개발 트리): `python app/main.py`
- 실행(설치 후): `chemvas`
- 좌측 툴바에서 도구를 선택하고 캔버스에 클릭/드래그하여 구조를 그립니다.
- 상단의 SMILES 입력란에 문자열을 입력한 뒤 Insert를 누르면 배치 모드가 활성화됩니다.
  마우스를 이동하면 미리보기가 표시되고, 클릭하면 해당 위치에 삽입됩니다. Esc로 취소할 수 있습니다.
- 템플릿 메뉴에서도 동일하게 미리보기/클릭 삽입 방식으로 링 구조를 배치할 수 있습니다.

## 예제
- [`examples/template1.chemvas`](examples/template1.chemvas)를 **File ▸ Open**으로 열어보세요 —
  위 hero 이미지에 보이는 반응 스킴 + 여러 유기촉매 구조가 담겨 있습니다.

## 저장/불러오기
- 상단 툴바의 File 메뉴로 `.chemvas` 파일을 저장/불러옵니다.
- `.chemvas`는 JSON 기반 포맷이며, 분자 모델/주석/화살표/bracket annotation/설정값 등을 포함합니다.
  (형식: `{"type":"chemvas","version":4,"state":{...}}`)
- Figure export의 SVG 기본값은 Chemvas 원본 데이터를 포함하지 않는 plain SVG입니다. Chemvas에서 다시
  편집 가능한 round-trip 파일이 필요할 때만 **Editable Chemvas SVG**를 선택하세요.

## 자동저장 & 복구
- Chemvas는 열려 있는 모든 문서를 수 초마다 사용자별 app-data 폴더에 스냅샷으로 저장합니다(원본 파일 옆에는
  아무것도 쓰지 않습니다).
- 앱이 강제 종료되거나 크래시하면 다음 실행에서 해당 문서들을 복원하며, 미저장 문서는 `●` 표시와 상태바 안내로
  알립니다. 정상 종료 시에는 열려 있던 파일들을 다시 엽니다.
- 스냅샷은 세션이 복원되거나 정상적으로 닫히면 정리됩니다.

## 단축키
- Chemvas는 ChemDraw 호환 단축키의 주요 하위집합을 지원합니다.
- 빈 캔버스(Generic tool hotkeys): Select/Marquee(`Space`), Bond(`X`), Atom(`A`), Text(`T`), Arrow(`E`), Benzene(`J`), Brackets(`Shift+T`), Orbitals(`Shift+G`), Chemical symbols(`Shift+E`), Perspective(`Alt+D`)
- Atom hotkeys(원자 위 hover): 원소/약식 라벨 `c n o s p f h b i l m e r x d` 및 `Shift+f/p/a/b/s/n/e/z/m/l/o/q/h/y`, 전하 `+/-`, 라벨 편집 `Enter`, sprout `0/1/2/3/a/4/5/6/7/8/9/z/v/u` (`9` = gem-dimethyl)
- Bond hotkeys(결합 위 hover): Single(`1`), Double(`2`), Triple(`3`), Bold(`b`/`Shift+B`), Wedge(`w`), Hash(`h`/`Shift+H`), Dashed(`d`/`Shift+D`), 이중결합 위치(`l`/`c`/`r`), Benzene fusion(`a`), Ring fusion(`4/5/6/7/8`), Chair fusion(`9/0`)
- 객체: Flip Horizontal(`Ctrl+Shift+H`), Flip Vertical(`Ctrl+Shift+V`), 선택 회전 `Alt+Up/Down`(15°)·`Alt+Left/Right`(1°), 선택 이동 `Shift+방향키`(10pt)
- 뷰: 실제 크기(`F5`), 창에 맞춤(`F6`), 확대(`F7`), 축소(`F8`)
- 파일/편집: Save/Open/Undo/Redo(플랫폼 기본 단축키), `Ctrl+A`(전체 선택, Select 도구로 전환), `Ctrl+C`(선택 영역 이미지 복사), `Ctrl+X`(선택 잘라내기), `Ctrl+G`/`Ctrl+Shift+G`(선택 그룹/그룹 해제), `Delete/Backspace`(선택 삭제 또는 hover atom/bond 편집/삭제), `Esc`(템플릿/SMILES 삽입 취소)

## 의존성
- PyQt6 필요
- RDKit은 선택 사항이며, 설치된 경우 SMILES/분자식/분자량 계산, 2D -> 3D `.xyz` export, 3D preview에 사용됩니다.

## 2D -> 3D `.xyz` Export / Molecule Info Window
- export 범위는 현재 작업 중인 분자 그래프 또는 현재 원자/결합 selection 기준입니다. 화살표, bracket annotation, 자유 텍스트 등 비분자 객체는 `.xyz`에 포함되지 않습니다.
- RDKit이 없는 환경에서는 이 기능을 사용할 수 없습니다. Chemvas는 기본 실행에 RDKit을 강제하지 않습니다.
- atom에 붙은 `+/-/radical` mark는 formal charge / radical electron으로 변환되어 3D 생성에 반영됩니다.
- wedge/hash 결합은 single bond에서 RDKit stereochemistry 힌트로 변환됩니다.
- 대표적인 축약/alias 라벨 `Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`는 3D 변환 전에 fragment로 확장됩니다.
- 지원되지 않는 라벨, 잘못 연결된 alias, wedge/hash의 잘못된 사용(예: non-single bond) 등은 명시적인 에러 메시지로 안내합니다.
- 상단 툴바의 `Molecule Info` 버튼은 별도 창을 열어 현재 선택된 분자의 3D preview와 분자식/분자량을 표시합니다. 선택된 화학 구조가 없으면 preview는 비어 있으며, 창 안의 `Export 3D XYZ` 버튼으로 선택된 분자를 내보낼 수 있습니다. 마우스 드래그로 회전, 휠로 확대/축소할 수 있습니다.
- `.xyz`는 원자 기호와 3D 좌표만 저장하는 포맷이므로, 결합 차수/입체정보/반응 스킴을 완전하게 round-trip하는 용도에는 적합하지 않습니다.

## 개발 / 기여
- PyQt6가 설치된 환경에서 headless 테스트 실행: `QT_QPA_PLATFORM=offscreen python -m pytest`
- GitHub Actions CI도 동일하게 headless 환경(`QT_QPA_PLATFORM=offscreen`)에서 lint, 타입 체크, 테스트를 실행합니다.
- 개발 환경 설정, 테스트 실행 방법, 그리고 **아키텍처 규약**은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.
  코드베이스가 수많은 작은 `*_ports` / `*_access` / `*_state` / `*_service` 모듈로 나뉜 것은 **의도된 설계**이며,
  그 경계는 테스트로 강제됩니다. 구조를 바꾸기 전에 반드시 CONTRIBUTING을 읽어주세요.
- 전체 설계 개요는 [docs/ARCHITECTURE.ko.md](docs/ARCHITECTURE.ko.md)에 있습니다.

## 로드맵 / 아직 미지원
버그가 아니라 알려진 빈칸입니다 — 기여를 환영합니다:
- **Bond-aware 상호운용:** MOL/SDF **import**, SDF(다중 분자) export. `.mol` export, SMILES export("copy as SMILES"), InChI/InChIKey는 완료됨.
- **벡터 클립보드:** `Ctrl+C`는 현재 PNG만 복사합니다. PDF/SVG 클립보드(Illustrator/Office에 벡터로 붙여넣기)는 예정.
- **배포:** 단일 파일 데스크톱 바이너리 (Chemvas는 이미 PyPI에 게시됨 — `pip install chemvas`)
- **다중 분자 / 반응 스킴 전체 3D export**, 더 풍부한 템플릿 라이브러리

## License
- [MIT License](LICENSE)
