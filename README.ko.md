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
- MOL 상호운용: MDL Molfile(`.mol`, V2000)을 새 문서로 열고, 선택한 구조를 `.mol`로
  내보냅니다. import와 일반 원소 export에는 RDKit이 필요 없지만 축약 라벨 확장에는 선택적
  RDKit이 필요합니다. property record는 `M  CHG` / `M  RAD`만, wedge/hash stereo는
  single bond에서만 지원하고 counts-line chiral flag는 0이어야 합니다. spin multiplicity를
  보존할 수 있을 때까지 singlet `M  RAD` code 1은 거부합니다.
- 2D -> 3D `.xyz` export: 현재 분자 또는 현재 원자/결합 selection을 RDKit 기반 3D 좌표로 변환해 내보내기
- Molecule Info 창: RDKit 기반 3D preview와 분자식/분자량 표시, 현재 selection의 canonical
  SMILES / InChI / InChIKey 원클릭 복사
- 색상/스타일: ACS 팔레트로 결합/원자/링 색 변경, 링 채움 색상, 본드 길이 조절
- 편집/변형: 선택/이동, 지우개 도구(클릭 또는 드래그로 삭제), 수평/수직 플립, 퍼스펙티브 회전, Undo/Redo
- 데스크톱 메뉴: 표준 File / Edit / View 메뉴와 시트 크기/방향을 바꾸는 **Canvas Size** 다이얼로그
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
- Qt를 시작하지 않는 CLI 도움말/버전 확인: `chemvas --help`, `chemvas --version`
- 상단 툴바에서 도구를 선택하고 캔버스에 클릭/드래그하여 구조를 그립니다.
- 상단의 SMILES 입력란에 문자열을 입력한 뒤 Insert를 누르면 배치 모드가 활성화됩니다.
  마우스를 이동하면 미리보기가 표시되고, 클릭하면 해당 위치에 삽입됩니다. Esc로 취소할 수 있습니다.
- 템플릿 메뉴에서도 동일하게 미리보기/클릭 삽입 방식으로 링 구조를 배치할 수 있습니다.

## 예제
- [`examples/template1.chemvas`](examples/template1.chemvas)를 **File ▸ Open**으로 열어보세요 —
  위 hero 이미지에 보이는 반응 스킴 + 여러 유기촉매 구조가 담겨 있습니다.

## 저장/불러오기
- 메뉴바의 **File** 메뉴에서 `.chemvas` 파일을 저장/불러옵니다.
- `.chemvas`는 JSON 기반 포맷이며, 분자 모델/주석/화살표/bracket annotation/설정값 등을 포함합니다.
  (형식: `{"type":"chemvas","version":5,"state":{...}}`)
- v5는 선택적인 `calculation_plan`에 재사용 가능한 계산 상태, elementary-step 양끝의 역할,
  명시적 원자 대응을 함께 저장합니다. 기존 v1-v4 문서도 계속 불러옵니다.
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
- 파일/편집: Save/Open/Undo/Redo(플랫폼 기본 단축키), `Ctrl+A`(전체 선택, Select 도구로 전환), `Ctrl+C`(선택 복사 — PNG와 SVG/PDF 벡터 클립보드 동시 제공), `Ctrl+X`(선택 잘라내기), `Ctrl+V`(복사한 선택 붙여넣기), `Ctrl+G`/`Ctrl+Shift+G`(선택 그룹/그룹 해제), `Delete/Backspace`(선택 삭제 또는 hover atom/bond 편집/삭제), `Esc`(템플릿/SMILES 삽입 취소)

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
- 메뉴바의 **View ▸ Molecule Info**는 별도 창을 열어 현재 선택된 분자의 3D preview와 분자식/분자량을 표시합니다. 선택된 화학 구조가 없으면 preview는 비어 있으며, 창 안의 `Export 3D XYZ` 버튼으로 선택된 분자를 내보낼 수 있습니다. 마우스 드래그로 회전, 휠로 확대/축소할 수 있습니다.
- `.xyz`는 원자 기호와 3D 좌표만 저장하는 포맷이므로, 결합 차수/입체정보/반응 스킴을 완전하게 round-trip하는 용도에는 적합하지 않습니다.

## Agent가 안전하게 문서 수정하기

### 창 없는 문서 렌더링

Agent는 데스크톱 창을 열거나 RDKit을 불러오지 않고 GUI와 같은 figure-export 경로로
전체 그림을 렌더링할 수 있습니다.

```bash
chemvas render-document scheme.chemvas --output scheme.svg
chemvas render-document scheme.chemvas --output scheme.png --dpi 600
chemvas render-document scheme.chemvas --output scheme-transparent.png \
  --background transparent
```

출력 suffix가 SVG/PNG를 결정합니다. 기본 배경은 흰색이며 PNG DPI는 150, 300, 600, 1200 중
하나이고 SVG는 DPI를 무시합니다. 명령은 보이지 않는 offscreen Qt canvas만 만들고 session
recovery를 시작하지 않으며 원본을 바꾸지 않습니다. 기존 파일·디렉터리·symlink는 거부하고 새
출력만 원자적으로 공개합니다.

표준 출력의 결정론적 JSON report에는 원본과 출력의 정확한 SHA-256, 문서 버전, 출력 byte 수,
물리 point 크기와 PNG pixel 크기가 들어갑니다. 같은 Chemvas/Qt/font 환경에서 반복한 렌더는
byte가 동일하지만 Qt나 font가 바뀌면 path geometry 또는 encoding이 달라질 수 있으므로
cross-platform byte 동일성을 가정하지 말고 report의 hash를 사용해야 합니다. 렌더는 source
8 MiB, graphics record 20,000개, output 64 MiB, 한 변 14,400 point, PNG 한 변 10,000 pixel
또는 총 2,500만 pixel 한도에서 fail closed합니다.

### Graph Patch v1

Agent는 Qt를 띄우거나 `.chemvas` 전체를 다시 쓰지 않고도 안정적인 atom ID를 모두 검사한 뒤
범위가 제한된 Graph Patch를 제안할 수 있습니다.

```bash
chemvas inspect-document scheme.chemvas > inspection.json
chemvas apply-patch scheme.chemvas patch.json --dry-run
chemvas apply-patch scheme.chemvas patch.json --output revised.chemvas
```

`inspect-document`는 원본 파일 bytes의 정확한 SHA-256, 문서 버전, `next_atom_id`, 전체
atom/bond 목록, 유효 charge/radical annotation, 연결 성분, 의존 scene state 개수를 보고합니다.
Agent는 그 hash를 Graph Patch v1 전제조건에 그대로 넣습니다.

```json
{
  "format": "chemvas-graph-patch",
  "version": 1,
  "source_sha256": "<소문자 16진수 64자>",
  "operations": [
    {"op": "add_atom", "atom_id": 12, "element": "O",
     "x": 216.0, "y": 72.0, "color": "#000000", "explicit_label": true},
    {"op": "add_bond", "a": 4, "b": 12, "order": 1,
     "style": "single", "color": "#000000"},
    {"op": "update_bond", "a": 4, "b": 12,
     "changes": {"order": 2, "style": "double"}}
  ]
}
```

지원 연산은 `add_atom`, `update_atom`(원소/색/명시 라벨), `move_atom`, `add_bond`,
`update_bond`, `remove_bond`입니다. 모든 연산을 원본과 분리된 복사본에서 순서대로 실행하고
문서 및 Calculation Plan 전체 검증을 통과한 뒤에만 공개합니다. `move_atom`은 연관된 ring fill,
부착 mark, perspective 좌표도 함께 이동합니다. Dry-run은 실제 적용과 동일한 검증 및 후보 파일
hash 계산을 수행하지만 아무것도 쓰지 않습니다. 실제 적용도 입력 문서 버전을 유지하고 source를
바꾸지 않으며 기존 파일이나 symlink를 절대 덮어쓰지 않습니다.

Graph Patch v1은 의도적으로 atom 삭제, charge/radical annotation, arrow, group, Calculation Plan
편집을 지원하지 않습니다. 화학·반응 메커니즘도 추론하지 않으므로 이런 의미론은 GUI 또는 별도로
검토한 plan 갱신 경로를 사용해야 합니다.

## Headless 계산 번들

설치된 Chemvas는 Qt GUI를 띄우지 않고도 agent에게 구조를 전달할 수 있습니다. 먼저 연결 성분을
검사한 다음, 사용할 성분 하나를 명시해 패키징합니다.

```bash
chemvas inspect scheme.chemvas
chemvas pack scheme.chemvas \
  --component 0 --species-id reactant-a \
  --charge 0 --multiplicity 1 \
  --output reactant-a.bundle
```

`inspect`는 RDKit 없이도 동작하며 JSON을 출력합니다. `pack`은 선택 사항인 RDKit이 필요하고,
기존 경로를 덮어쓰지 않는 Calculation Bundle v1 디렉터리를 새로 만듭니다. 번들은
`source.chemvas`, `structure.mol`, `geometry.xyz`, `atom_map.json`, `manifest.json`으로
구성됩니다. manifest에는 manifest 자신을 제외한 payload 파일의 SHA-256, 선택한 Chemvas 원자 ID, 선언한 전하/다중도,
모델의 formal charge/radical, RDKit 버전과 원자 수가 기록됩니다. atom map은 alias 확장 원자와
implicit hydrogen까지 설명하므로 계산 좌표 인덱스를 원래 그림까지 추적할 수 있습니다.

선언 전하가 구조에 붙은 charge mark의 합과 다르면 번들 생성을 거부합니다. 다중도는 항상
명시적으로 입력하며 electron-count parity만 검사하고 2D 구조로부터 spin state를 추론하지
않았다고 기록합니다. Chemvas는 반응물/생성물 역할 또는 반응 메커니즘을 임의로 추측하지 않습니다.

species/run마다 고유한 출력 디렉터리를 사용하세요. `pack`은 기존 target을 거부하지만 같은 경로를
동시에 차지하려는 여러 orchestrator를 조정하지는 않습니다.

### 계산 상태와 elementary step

한 캔버스에 reactant, product, catalyst, spectator를 그린 뒤
**Calculation ▸ Edit States and Steps...**를 엽니다. 각 endpoint에서 연결 성분마다 다음 포함 방식을
지정합니다.

- `included`: XYZ 좌표, 전자 수, 전하·다중도 검증에 실제로 포함
- `context_only`: catalyst, solvent, additive 같은 조건으로 기록하지만 계산 좌표에서는 제외

`reactant`, `product`, `catalyst`, `spectator` 역할은 구조의 전역 속성이 아니라 step endpoint의
속성입니다. 따라서 한 상태를 S01의 product이자 S02의 reactant로 재사용할 수 있습니다. 원자 대응
표에는 included reactant 원자만 나오며, 각 행에서 같은 원소의 product 원자를 안정적인 Chemvas
원자 ID로 고릅니다. 양 endpoint가 정확히 같은 ID를 공유하는 촉매 같은 원자는 한 번만 초기값으로
제안할 뿐, 원소나 위치로 대응을 추론하지 않으며 사용자가 지정한 **Unmapped**를 다시 덮어쓰지
않습니다. 같은 product 원자를 중복 지정하면 저장을 거부합니다. 대응이 덜 된 표도 draft로 저장할
수 있지만, 양 endpoint의 모든 included 원자에 완전한 1:1 source mapping이 생길 때까지 상태 표시와
`pack-step`은 잠깁니다. 이 준비 표시는 source mapping gate만 뜻하며 RDKit geometry 생성과 후속
화학적 검토는 별도 요구사항입니다. 대응 행을 선택하거나 product 메뉴의 후보를 훑으면 캔버스의
reactant에는 파란 실선 **R**, product에는 주황 점선 **P**가 표시됩니다. 이 표시는 임시 overlay라
dialog를 닫으면 사라지며 그림, 기존 canvas selection, undo history를 바꾸지 않습니다.

Agent는 Qt 없이도 같은 계약을 붙이고 검사할 수 있습니다.

```bash
chemvas attach-plan scheme.chemvas plan.json --output mechanism.chemvas
chemvas inspect-plan mechanism.chemvas
chemvas pack-step mechanism.chemvas --step S01 --output calculations/S01
```

Calculation Plan v1에서 state는 계산 성분과 전하·다중도를, step endpoint는 역할을 소유합니다.

```json
{
  "format": "chemvas-calculation-plan",
  "version": 1,
  "states": [
    {"id": "R01", "charge": 0, "multiplicity": 1,
     "members": [
       {"component_atom_ids": [0, 1], "inclusion": "included"},
       {"component_atom_ids": [9], "inclusion": "context_only"}]},
    {"id": "P01", "charge": 0, "multiplicity": 1,
     "members": [{"component_atom_ids": [2, 3], "inclusion": "included"}]}
  ],
  "steps": [{
    "id": "S01",
    "reactant": {"state_id": "R01", "roles": [
      {"component_atom_ids": [0, 1], "role": "reactant"},
      {"component_atom_ids": [9], "role": "spectator"}]},
    "product": {"state_id": "P01", "roles": [
      {"component_atom_ids": [2, 3], "role": "product"}]},
    "atom_correspondence": [
      {"reactant_atom_id": 0, "product_atom_id": 2},
      {"reactant_atom_id": 1, "product_atom_id": 3}]
  }]
}
```

각 `component_atom_ids`는 정렬된 완전한 연결 성분 하나와 정확히 같아야 합니다. `pack-step`은
`reactant.bundle/`, `product.bundle/`, `atom_correspondence.json`, `bond_changes.json`,
`step_manifest.json`을 만듭니다. RDKit이 만든 원자까지 완전한 대응을 요구하므로 endpoint 사이
implicit hydrogen 수가 달라지는 전달 수소는 명시적으로 그려야 합니다. `inspect-plan`은 각 step에
결정론적인 `path_precheck`를 보고합니다. source mapping이 완전하고, 양 endpoint의 전하·다중도가
같고, endpoint마다 included 연결 성분이 정확히 하나라면 `pack-step`은
`path_endpoints/reactant.xyz`, `product.xyz`, `manifest.json`도 만듭니다. product XYZ는 reactant의
원자 identity 순서로 재작성되며, path manifest는 그 순서와 결합 변화에 참여한 반응중심 원자를
공통 0-based index로 기록합니다. 따라서 downstream 도구가 원소 순서나 좌표로 대응을 다시
추론할 필요가 없습니다.

source mapping이 불완전하면 기존 gate에서 여전히 `pack-step` 전체를 중단합니다. 이 gate와 생성
원자 bijection을 통과한 뒤 다성분 또는 전자상태 조건만 맞지 않으면 generic step bundle은 유지하고,
`path_readiness.blocking_reasons`에 `path_endpoints/`를 만들지 않은 이유를 기록합니다. 특히 Chemvas는
다성분 catalyst/substrate precomplex를 임의로 만들지 않습니다. 모든 생성 좌표는 초기 추정이며,
path endpoint pair에는 rigid alignment나 양자화학 최적화가 수행되지 않습니다. 후속 최적화와
연구자 검토가 필요합니다.

## 개발 / 기여
- 테스트는 headless로 실행하되, 전체 suite는 Qt 전역 상태 격리를 위해 `test_*.py` 파일마다 별도 pytest 프로세스를 사용합니다. 정확한 CI 미러 명령은 [Running the checks](CONTRIBUTING.md#running-the-checks)를 따르세요.
- GitHub Actions도 테스트 단계에서 같은 file-isolated headless 방식을 사용합니다.
- 개발 환경 설정, 테스트 실행 방법, 그리고 **아키텍처 규약**은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.
  전환기 UI 코드는 실제 책임을 분리하는 기존 `*_ports` / `*_access` / `*_state` / `*_service` 경계를 유지하지만,
  신규 기능이 이 배치를 기본으로 복제하지는 않습니다. 활성 경계는 테스트로 강제되므로 구조를 바꾸기 전에 반드시 CONTRIBUTING을 읽어주세요.
- 전체 설계 개요는 [docs/ARCHITECTURE.ko.md](docs/ARCHITECTURE.ko.md)에 있습니다.

## 로드맵 / 아직 미지원
버그가 아니라 알려진 빈칸입니다 — 기여를 환영합니다:
- **SDF(다중 분자) 상호운용:** import와 export. 단일 분자 `.mol` import/export, SMILES export("copy as SMILES"), InChI/InChIKey는 완료됨.
- **배포:** 단일 파일 데스크톱 바이너리 (Chemvas는 이미 PyPI에 게시됨 — `pip install chemvas`)
- **다중 분자 / 반응 스킴 전체 3D export**, 더 풍부한 템플릿 라이브러리
- **당분간 의도적 비범위:** 인쇄(PDF export로 대체), 환경설정 영속화(모든 문서는 ACS 1996 기본값에서 시작), 외부 클립보드 내용 붙여넣기, 드래그앤드롭으로 파일 열기

## License
- [MIT License](LICENSE)
