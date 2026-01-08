# LiteDraw

LiteDraw는 PyQt6 기반의 2D 화학 구조 드로잉 앱입니다. 분자 구조와 반응 스킴을 빠르게 스케치하고,
SMILES 입력(RDKit 선택)을 통해 구조를 불러와 편집할 수 있습니다. 기본 스타일은 ACS 1996 규격을
따르며, 실험 노트나 논문용 그림의 초안을 빠르게 만들기 위한 도구를 목표로 합니다.

## 개요
- 분자 본드/링/라벨, 화살표, 오비탈을 한 캔버스에서 조합해 그릴 수 있습니다.
- 선택/이동/플립/퍼스펙티브 회전 등 간단한 변형 작업이 가능합니다.
- 선택된 구조에 대해 분자식/분자량을 표시할 수 있으며(RDKit 필요),
  SMILES로 구조를 불러와 클릭 위치에 배치할 수 있습니다.
- 저장/불러오기(.ldraw JSON)를 지원해 작업 상태를 유지합니다.

## 주요 기능
- 본드 도구: 단/이/삼중 결합, 굵은 결합, 웨지/해시 표현, 30도 각도 스냅과 기본 결합 길이 유지
- 링/템플릿: 벤젠 링, 사이클로알케인, 의자/보트 형태 템플릿 배치
- 화살표: 반응/평형/공명/곡선/점선 화살표, 굵기/헤드 스케일 설정
- 오비탈: s, p, sp, sp2, sp3, d, MO bonding/antibonding, 위상 표시 토글
- 색상/스타일: ACS 팔레트로 결합/원자/링 색 변경, 링 채움 색상, 본드 길이 조절
- 편집/변형: 선택/이동, 수평/수직 플립, 퍼스펙티브 회전, Undo/Redo

## 사용 방법
- 실행: `python app/main.py`
- 좌측 툴바에서 도구를 선택하고 캔버스에 클릭/드래그하여 구조를 그립니다.
- 상단의 SMILES 입력란에 문자열을 입력한 뒤 Render를 누르면 배치 모드가 활성화됩니다.
  마우스를 이동하면 미리보기가 표시되고, 클릭하면 해당 위치에 삽입됩니다. Esc로 취소할 수 있습니다.
- 템플릿 메뉴에서도 동일하게 미리보기/클릭 삽입 방식으로 링 구조를 배치할 수 있습니다.

## 저장/불러오기
- 상단 툴바의 Save/Load 버튼으로 `.ldraw` 파일을 저장/불러옵니다.
- `.ldraw`는 JSON 기반 포맷이며, 분자 모델/주석/화살표/오비탈/설정값 등을 포함합니다.
  (형식: `{"type":"litedraw","version":1,"state":{...}}`)

## 단축키
- 도구: Select(V), Bond(B), Atom(T), Ring(R), Arrow(A), Orbital(O)
- 파일: Save(플랫폼 기본 단축키), Open(플랫폼 기본 단축키)
- 편집: Undo/Redo(플랫폼 기본 단축키), Delete/Backspace(선택 항목 삭제)
- 작업: Esc(템플릿/SMILES 삽입 모드 취소)

## 의존성
- PyQt6 필요
- RDKit은 선택 사항이며, SMILES/분자식/분자량 계산 기능에만 사용됩니다.

## Architecture
- CanvasView 분리 및 커맨드 기반 undo 진행 상황은 `docs/architecture.md`에서 확인할 수 있습니다.

## Current Issues
- Atom label cutouts are inconsistent for single bonds: when replacing a joint atom label, only one of the connected single bonds is trimmed while others still overlap the label.
- Benzene ring double bonds: trimming is excessive when a ring atom label is introduced, and inner double-bond segments do not reliably match the intended shorter inner-line style.
- Undo after multiple consecutive atom label changes reverts all label edits at once instead of only the most recent change.
- Importing a SMILES structure clears all existing drawings on the canvas.
- SMILES insertion always appears at a fixed location; it should insert at the clicked position, with a transparent preview on hover. The same hover preview issue applies to rings, templates, and bond placement.
- Hover highlight style: prefer a soft gray circular hover indicator around atoms/bonds instead of changing to a blue line highlight.
- Color and ring fill icons should be redesigned to be more intuitive for users.
- Add save/load functionality for the current canvas.
- Curved double arrow rendering: arrowhead placement looks incorrect.
- Left toolbar separator (dotted line) is mispositioned and should be removed.
- Add a shortcut to edit the hovered atom label via Shift + letter key combination.
- Orbital drawing does not align to the molecular geometry; it appears as a fixed shape simply overlaid on bonds.
- Orbital and template icons should be redesigned to be more intuitive.
- Arrow/orbital/template dropdowns show only text labels; they should preview the expected structure shape.
- When Wedge/Hash is selected, clicking an existing bond still cycles single/double/triple instead of switching to wedge/hash.
- Add copy-to-clipboard as image for selected molecules (to paste into external files).
- Bond length control should move to the top toolbar.
- Add export/conversion from current 2D structure to 3D `.xyz`.
