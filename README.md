# Chemvas

Chemvas는 PyQt6 기반의 2D 화학 구조 드로잉 앱입니다. 분자 구조와 반응 스킴을 빠르게 스케치하고,
SMILES 입력(RDKit 선택)을 통해 구조를 불러와 편집할 수 있습니다. 기본 스타일은 ACS 1996 규격을
따르며, 실험 노트나 논문용 그림의 초안을 빠르게 만들기 위한 도구를 목표로 합니다.

## 개요
- 분자 본드/링/라벨, 화살표, TS bracket을 한 캔버스에서 조합해 그릴 수 있습니다.
- 선택/이동/플립/퍼스펙티브 회전 등 간단한 변형 작업이 가능합니다.
- 선택된 구조에 대해 분자식/분자량을 표시할 수 있으며(RDKit 필요),
  SMILES로 구조를 불러와 클릭 위치에 배치할 수 있습니다.
- 저장/불러오기(.chemvas JSON)를 지원해 작업 상태를 유지합니다.

## 주요 기능
- 본드 도구: 단/이/삼중 결합, 굵은 결합, 웨지/해시 표현, 30도 각도 스냅과 기본 결합 길이 유지
- 링/템플릿: 벤젠 링, 사이클로알케인, 의자/보트 형태 템플릿 배치
- 화살표: 반응/평형/공명/곡선/점선 화살표, 굵기/헤드 스케일 설정
- TS bracket: 전이상태 표기를 위한 paired bracket + double dagger(`‡`) 객체
- 2D -> 3D `.xyz` export: 현재 분자 또는 현재 원자/결합 selection을 RDKit 기반 3D 좌표로 변환해 내보내기
- 우측 고정 패널: RDKit 기반 3D preview
- 색상/스타일: ACS 팔레트로 결합/원자/링 색 변경, 링 채움 색상, 본드 길이 조절
- 편집/변형: 선택/이동, 수평/수직 플립, 퍼스펙티브 회전, Undo/Redo

## 사용 방법
- 실행: `python app/main.py`
- 좌측 툴바에서 도구를 선택하고 캔버스에 클릭/드래그하여 구조를 그립니다.
- 상단의 SMILES 입력란에 문자열을 입력한 뒤 Render를 누르면 배치 모드가 활성화됩니다.
  마우스를 이동하면 미리보기가 표시되고, 클릭하면 해당 위치에 삽입됩니다. Esc로 취소할 수 있습니다.
- 템플릿 메뉴에서도 동일하게 미리보기/클릭 삽입 방식으로 링 구조를 배치할 수 있습니다.

## 저장/불러오기
- 상단 툴바의 File 메뉴로 `.chemvas` 파일을 저장/불러옵니다.
- `.chemvas`는 JSON 기반 포맷이며, 분자 모델/주석/화살표/TS bracket/설정값 등을 포함합니다.
  (형식: `{"type":"chemvas","version":1,"state":{...}}`)

## 단축키
- Chemvas는 ChemDraw 호환 단축키의 주요 하위집합을 지원합니다.
- 빈 캔버스(Generic tool hotkeys): Select/Marquee(`Space`), Bond(`X`), Atom/Text(`T`), Arrow(`E`), Benzene(`J`), TS Bracket(`Shift+G`), Perspective(`Alt+D`)
- Atom hotkeys(원자 위 hover): 원소/약식 라벨 `c n o s p f h b i l m e r x d` 및 `Shift+f/p/a/b/s/n/e/z/m/l/o/q/h/y`, 전하 `+/-`, 라벨 편집 `Enter`, sprout `0/1/2/3/a/4/5/6/7/8/z/v/u`
- Bond hotkeys(결합 위 hover): Single(`1`), Double(`2`), Triple(`3`), Bold(`b`/`Shift+B`), Wedge(`w`), Hash(`h`/`Shift+H`), Benzene fusion(`a`), Ring fusion(`4/5/6/7/8`), Chair fusion(`9/0`)
- 객체: Flip Horizontal(`Ctrl+Shift+H`), Flip Vertical(`Ctrl+Shift+V`)
- 파일/편집: Save/Open/Undo/Redo(플랫폼 기본 단축키), `Ctrl+C`(선택 영역 이미지 복사), `Delete/Backspace`(선택 삭제 또는 hover atom/bond 편집/삭제), `Esc`(템플릿/SMILES 삽입 취소)

## 의존성
- PyQt6 필요
- RDKit은 선택 사항이며, 설치된 경우 SMILES/분자식/분자량 계산, 2D -> 3D `.xyz` export, 3D preview에 사용됩니다.

## 2D -> 3D `.xyz` Export / Right Panel
- export 범위는 현재 작업 중인 분자 그래프 또는 현재 원자/결합 selection 기준입니다. 화살표, TS bracket, 자유 텍스트 등 비분자 객체는 `.xyz`에 포함되지 않습니다.
- RDKit이 없는 환경에서는 이 기능을 사용할 수 없습니다. Chemvas는 기본 실행에 RDKit을 강제하지 않습니다.
- atom에 붙은 `+/-/radical` mark는 formal charge / radical electron으로 변환되어 3D 생성에 반영됩니다.
- wedge/hash 결합은 single bond에서 RDKit stereochemistry 힌트로 변환됩니다.
- 대표적인 축약/alias 라벨 `Me`, `Et`, `OH`, `Ph`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `i-Pr`는 3D 변환 전에 fragment로 확장됩니다.
- 지원되지 않는 라벨, 잘못 연결된 alias, wedge/hash의 잘못된 사용(예: non-single bond) 등은 명시적인 에러 메시지로 안내합니다.
- 우측 패널은 상단 툴바의 `3D Preview Panel` 버튼으로 열고 닫을 수 있으며, `3D Preview`에서 현재 구조를 실시간으로 확인할 수 있습니다. 마우스 드래그로 회전, 휠로 확대/축소할 수 있습니다.
- `.xyz`는 원자 기호와 3D 좌표만 저장하는 포맷이므로, 결합 차수/입체정보/반응 스킴을 완전하게 round-trip하는 용도에는 적합하지 않습니다.

## GUI Smoke Test
- PyQt6가 설치된 환경에서 headless shortcut smoke test 실행:
  `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests`
- 현재 smoke test는 generic tool hotkey, atom hotkey, bond hotkey의 실제 key sequence 입력을 `PyQt6.QtTest.QTest`로 검증합니다.
- GitHub Actions CI도 동일하게 headless 환경(`QT_QPA_PLATFORM=offscreen`)에서 lint, 타입 체크, 테스트를 실행합니다.

## License
- [MIT License](LICENSE)

## Architecture
- CanvasView 분리 및 커맨드 기반 undo 진행 상황은 `docs/architecture.md`에서 확인할 수 있습니다.

## Current Issues
- Template icons should be redesigned to be more intuitive.
- 2D -> 3D 변환은 단일 화학 그래프 중심입니다. 다중 분자 동시 export, 반응 스킴 전체 export, `.sdf/.mol` 같은 bond-aware 3D 포맷 지원은 후속 작업이 필요합니다.
