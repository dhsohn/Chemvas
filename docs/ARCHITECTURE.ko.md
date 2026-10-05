# 아키텍처

브라우저 어댑터는 [사용 안내](WEB_ADAPTER.ko.md)와
[ADR 0029](adr/0029-browser-adapter.md)를 따른다. Python 세션은
기존 문서·기능 API와 CanvasHistoryService를 재사용한다. 브라우저는 승인된
상태를 표시하고 UI 정의·그림은 기존 소유자에서 읽는다. SVG 표시와 이벤트 연결은
각각 응집된 연결 코드로 유지한다.
아래 Qt 구조는 기존 기본 데스크톱 편집기에 해당한다.

[English](ARCHITECTURE.md)

## 패키지별 책임

Chemvas는 책임을 기준으로 코드를 묶습니다. 아래 그림은 주요 패키지 관계를 보여 주며, 반드시 거쳐야 하는 호출 순서가 아닙니다. 현재 경계 규칙은 [ADR 0005](adr/0005-responsibility-based-editor-boundaries.md)에 기록되어 있습니다.

```mermaid
flowchart TB
    bootstrap["bootstrap<br/>CLI 디스패치 · 조립 루트 · adapters (Qt 렌더러, 파일 열기 이벤트, macOS 식별)"]
    editor["편집기 계층 (Qt)<br/>ui.canvas · ui.scene · ui.window · ui.tools · ui.selection · ui.molecule · ui.insert · ui.history · ui.export · ui.dialogs · ui.session · ui.annotations · ui.transactions · shell"]
    policy["정책 계층 (Qt 없음)<br/>features/* · core"]
    domain["domain (Qt 없음)<br/>문서 모델 · 화학 값 타입 · Calculation Plan · 트랜잭션"]
    bootstrap --> editor
    editor --> policy
    policy --> domain
```

화살표는 아래 방향으로만 향합니다. 이 계층은 선언이 아니라 import 그래프 실측입니다.
`core`와 `features`는 `domain`만 import하고, 편집기 계층은 `features`·`core`·`domain`을
import하며, `bootstrap`만 adapters를 알고 편집기를 조립합니다. `ui.annotations`와
`ui.transactions`는 편집기 아래 계층이 아니라 편집기의 하위 패키지입니다.

### 계층별 역할과 책임

| 계층 | 역할 및 책임 | Qt 의존성 없음 |
| --- | --- | :---: |
| `bootstrap` | CLI 디스패치, 앱 시작, 창·캔버스 서비스 조립, Qt·OS adapters | 부분적 |
| `shell` | 메인 윈도우 셸, 창 레지스트리, 테마, 스타일시트 및 툴바 UI | 아니요 |
| `ui.canvas` | `CanvasView`, 런타임 상태와 서비스, 캔버스 범위 컨트롤러 | 아니요 |
| `ui.scene` | 장면 항목 작업: 클립보드, 삭제, 변환, 그룹, 기하, 레코드 | 아니요 |
| `ui.window` | 메인 윈도우 서비스, 메뉴, 컨텍스트 바, 패널, 최근 문서 | 아니요 |
| `ui.tools` | 그리기 도구, 도구 디스패치, 핸들, 스냅, 호버 피드백 | 아니요 |
| `ui.selection` | 선택 상태, 외곽선, 조회, 회전, 선택 도구 | 아니요 |
| `ui.molecule` | 원자·결합 그래픽, 라벨, 구조 생성 | 아니요 |
| `ui.insert` | 템플릿 삽입 미리보기와 커밋 | 아니요 |
| `ui.history` | Undo/Redo 명령 페이로드와 재생 연산 | 아니요 |
| `ui.export`, `ui.dialogs`, `ui.session` | 그림 내보내기·레이아웃 검사, 편집기 대화상자, 자동 저장·복구 | 아니요 |
| `ui.annotations` | 편집기와 헤드리스 장면이 공유하는 주석 표시·렌더링·레코드 연결·상태 변환 | 아니요 |
| `ui.transactions` | 정확한 롤백을 위한 문서·장면 savepoint | 아니요 |
| `features` | 기능 정책과 Qt 없는 구현 | 예 |
| `core` | Qt-free 엔진 계층: 히스토리 명령, molfile·SVG 왕복, 문서 I/O | **예** |
| `domain` | 핵심 분자 그래프, 문서 스키마, 화학 값 타입, Calculation Plan, 트랜잭션 | **예** |

## 핵심 컴포넌트

- **CanvasView** (`app/chemvas/ui/canvas/canvas_view.py`): 사용자 입력 처리, 도구 디스패치, 좌표계 변환을 담당합니다. 선택 변경은 `SelectionController`가 소유합니다. 저수준 드로잉 처리는 직접 소유하지 않고 컨트롤러 및 렌더러와 협력합니다.
- **MoleculeModel** (`app/chemvas/domain/document/model.py`): 고유 정수 ID를 가진 원자 및 결합 데이터 구조이며 Qt 의존성이 없습니다.
- **Renderer** (`app/chemvas/adapters/qt/renderer.py`): `acs1996_style` 드로잉 정책을 적용하는 Qt 렌더링 구현체입니다.
- **HistoryCommand** (`app/chemvas/core/history.py`): 델타 기반 Undo/Redo 엔진입니다. 복합 작업은 `CompositeCommand`로 묶여 원자적으로 실행 취소/다시 실행됩니다.
- **장면 렌더링** (`scene_render_context.py`, `scene_rendering.py`): `SceneRenderContext`를 통해 뷰에 독립적인 분자 그래픽 및 주석 렌더링을 제공합니다 ([ADR 0004](adr/0004-view-independent-scene-rendering.md)).
- **도메인 문서** (`app/chemvas/domain/document`): 문서 직렬화, 스키마 검증 및 Calculation Plan v2 구조를 관리합니다.

## UI 아키텍처 및 경계 원칙

- **기능 소유권**: 상호작용 흐름은 컨트롤러 중심으로 구성하고 구체적인 협력 객체를 직접 주입받아 호출합니다. 캔버스가 소유하는 협력 객체는 한 가지 표기만 갖습니다. 런타임은 `canvas.services.<이름>`(평탄한 `CanvasRuntimeServices`), 상태는 `canvas.runtime_state.<이름>`, 캔버스 셋업이 만드는 객체는 `canvas.model`, `canvas.renderer`, `canvas.render_context`, `canvas.bond_renderer`입니다. 이 표기로 단순 위임만 하던 모듈은 제거했습니다 ([ADR 0012](adr/0012-flat-editor-runtime-and-ui-packages.md)).
- **서비스 의존성**: 그래프 조회는 현재 모델 조회 함수·렌더러·그래프 캐시를 받습니다. 결합 편집과 고리 채움은 기존 `SceneRenderContext`를, 단축키는 모델 조회 함수·호버 상태·구체적인 편집 서비스를 받습니다. 이 서비스들에 뷰 전체를 전달하지 않아도 문서 교체 후 현재 모델을 읽습니다. 뷰 수명과 입력을 조정하는 컨트롤러는 타입이 명시된 `CanvasView`를 유지합니다. 런타임 조립과 이력 어댑터에는 구체 타입을 적용하고, 메모·마크 편집과 이력 기록에는 이력 서비스를 필수로 주입합니다. 그래프·단축키 서비스는 strict 타입 검사를 받습니다. 서로 다른 장면 객체의 복원과 명령 조합에는 동적인 부분이 남습니다. 편집·Undo/Redo 측정은 [성능 기준 문서](performance/README.md)에 정리합니다.
- **상태 소유권**: `CanvasRuntimeState`가 캔버스 런타임 상태의 단일 소유자이며 `SceneRenderState`를 확장합니다. 상태 복사본을 두지 않고 소유자의 공개 인터페이스를 통해 작업하며, 히스토리·캐시 무효화·수명 주기 처리는 해당 소유자가 전담합니다.
- **동적 의존성 및 수명**: 윈도우 액션은 호출 시점에 활성 문서를 조회합니다. 공통 렌더 컨텍스트는 모델 및 장면 교체 시 최신 인스턴스를 추적하며, 수명 주기 계약을 준수합니다.
- **문서 모델과 장면 분리**: 분자 그래프와 `AnnotationCollection`은 Qt와 독립적으로 문서 데이터를 소유합니다. 주석 8종 모두 이 컬렉션에서 존재 여부·순서·저장 값을 읽으며, 그래픽 아이템은 런타임 ID로 연결된 표시 객체입니다 ([ADR 0010](adr/0010-document-owned-notes-and-marks.md)).
- **의존성 경계**: `domain`, `core`, `features`는 Qt-free를 유지합니다. 데스크톱 Qt 구현은 `ui`, 프레임워크 어댑터는 `adapters`, 애플리케이션 조립은 `bootstrap`에 둡니다. 기능 모듈은 어댑터, 편집기 위젯, 애플리케이션 진입점에 의존하지 않습니다. 패키지 간 비순환 import를 보장합니다.
- **복구 및 렌더링 계약**: 트랜잭션 및 복구 작업은 `CanvasHistoryOperations`, 공통 문서 트랜잭션, `SceneRenderContext` 계약을 준수합니다.
- **화학 백엔드 없음**: 그리기, MOL 입출력, 그림 내보내기는 화학 라이브러리를 호출하지 않습니다 ([ADR 0035](adr/0035-retire-rdkit-chemistry-provider.md)).

검토와 테스트 기준은 [기여 가이드](../CONTRIBUTING.ko.md#아키텍처-규칙)를 따릅니다.

### 편집과 복구 트랜잭션

문서 편집은 하나의 savepoint 안에서 데이터를 바꾸고 히스토리 명령을 기록합니다.
붙여넣기와 선택 삭제는 `document_transaction`을 사용하며, 구조 생성의 추가 항목
기록은 `StructureBuildCommitter`가 담당합니다. 두 경로의 실패·취소 복원은
`DocumentSavepoint.rollback`으로 통일합니다. 복원 실패는 원래 편집 오류에 첨부하고,
취소 중 복원이 실패하면 부분 문서를 정상 결과로 처리하지 않고 오류를 발생시킵니다.

단순 히스토리 명령의 캡처·해제·실패 복구는 `history_command_transaction`이 담당합니다.
헤드리스 실행을 지원하는 명령은 필요한 역연산을 직접 지정합니다. 정확한 복원이
실패했을 때는 복원 결과가 명시적으로 허용해야만 역연산을 실행합니다. 복합 명령과
별도 가변 페이로드를 가진 명령은 기존 보상 순서를 유지합니다. 삭제 협력 객체는
필수 의존성으로 직접 주입하고, 교체 가능한 모델은 호출 시 캔버스에서 읽습니다.

정확한 히스토리 트랜잭션은 스냅샷을 캡처 전에 확인한 복원·해제 함수와 결합합니다.
이후 포트의 함수가 교체되어도 해당 스냅샷은 원래 함수로 복원·해제하며, 호출자는
결합된 트랜잭션만 전달합니다. 캡처와 복원은 하나의 선택적 기능이고, 자원을 소유하지
않는 헤드리스 스냅샷은 해제 함수를 생략할 수 있습니다. 역연산 허용 여부를 판단하기
전에는 복원 결과를 계속 런타임에서 검증합니다.

메모 텍스트·문서 텍스트 스타일·주석 설정은 각각 구체 타입의 이력 명령과 복원
메서드를 사용합니다. 메모 텍스트 명령에는 문서 ID가 필수이며, 문자열 target으로
페이로드의 해석 방법을 선택하지 않습니다.

세션 복구 메뉴와 직접 복구 호출은 `restore_previous`의 동일한 인계 경로를 사용합니다.
이미 열린 사본이 있으면 재시도는 사본을 다시 여는 대신 현재 세션에 저장한 뒤 원본
복구 자료를 정리합니다. 정리 실패는 재시도 대상으로 남으며 자동 저장 성공을 막지 않습니다.

### 선택과 문서 생성

선택 삭제는 결합 하나와 혼합 선택 모두 같은 `DeleteSelectionPlan`을 사용합니다.
계획은 변경 전에 살아 있는 결합, 고립 원자, 연결된 마크와 살아남는 마크 소유자를
결정합니다. 컨트롤러는 계획을 적용한 뒤 고리·그룹 정리와 히스토리 기록을 문서
트랜잭션 안에서 조정합니다. 지우개 드래그는 반복 포인터 입력을 위한 기존 인덱스
기반 세션 경로를 유지합니다.

`SelectionController`가 장면 선택 쓰기, ID 기반 복원, 전체 선택과 노트 선택을
소유합니다. 조회와 선택 스타일 모듈은 선택 상태를 읽기만 합니다. 클립보드·이미지·
원자 라벨 경로도 컨트롤러를 호출하며, 문서·히스토리 롤백 소유자는 정확한 선택 플래그
복원을 유지합니다. Qt는 러버밴드 입력을 소유합니다. 구조 선택과 ID 기반 복원은 중간
신호를 묶고 그룹을 확장한 뒤 완성된 윤곽을 한 번 게시합니다. 노트의 명시적 선택 목록과
Qt 선택 플래그라는 기존 이원 상태는 유지하며, 구조 선택은 노트를 Qt 플래그만으로
선택하지 않고 이 목록을 통해 선택합니다.

`domain.document.build_normalized_document_payload`가 문서 상태를 검증하고 JSON
숫자를 정규화합니다. 데스크톱 생성과 CLI 조합·배치·템플릿 삽입·패치가 이를 공유합니다.
그래프 패치는 연산 요약과 함께, 문서 상태로는 검증한 이 페이로드
(`DocumentPatchResult.payload`)만 돌려주며, CLI는 이를 다시 조립하지 않고 인코딩합니다.
CLI 인코딩과 바이트 제한은 `bootstrap.document_cli_shared`가 소유하며, 데스크톱과
CLI의 기존 바이트 형식과 오류 메시지는 유지합니다.

### 문서 내용 이동

`CanvasMoveController`가 원자와 주석의 이동 및 이에 따르는 표식·결합·고리 채움·핸들·
히트 테스트 무효화를 담당합니다. 도구 조립 시 해당 캔버스의 컨트롤러를 `ToolContext`에
주입하며, `MoveTool`, 선택 영역 드래그, `SceneTransformController`가 직접 호출합니다.
일회용 레이아웃 캔버스와 `CanvasHistoryOperations`도 자기 캔버스의 같은 컨트롤러를
사용합니다. 컨트롤러는 캔버스를 보관하고 실행 시 현재 모델을 조회하므로, 문서를 새로
불러온 뒤 이전 모델을 편집 명령에 붙잡아 두지 않습니다.

제스처 트랜잭션, 변환 트랜잭션, 이력 재생은 기존의 캡처·커밋·롤백 책임을 유지합니다.
이동 컨트롤러가 독자적으로 이력을 발행하지 않습니다. 회전 드래그와 화살표 끝점
드래그는 매 프레임을 누른 시점에 캡처한 상태에서 계산하므로, 시작 각도로 돌아온 회전이나
원래 위치로 돌아온 화살표 끝점은 문서를 정확히 복원하고 이력을 남기지 않습니다. 다른
핸들은 포인터를 현재 레코드에 적용합니다.

### 문서가 소유하는 주석 컬렉션

`domain/document/annotation_collection.py`의 `AnnotationCollection[Record]`가
도형·화살표·TS 괄호·이미지·오비탈·고리 채움·노트·표식 ID의 순서와 원본 값을 소유합니다. 공통 렌더 상태는 이 문서와 그래픽 조회 사전을 함께 보관합니다.
저장은 문서를 직접 읽으므로 그래픽 아이템을 장면에서 떼거나 파괴해도 주석이
삭제되지 않습니다. 그룹 참조와 레이아웃 진단은 표시 객체가 없는 자리까지 포함한
문서 순서를 사용합니다.

명시적 생성·삭제와 이력 재생은 문서 목록과 그래픽 조회 사전을 함께 갱신하며,
Undo는 원래 순서를 복구합니다. 삭제된 주석의 임시 기록은 표시 객체가 사용하는 동안
유지됩니다. 이력은 ID와 복사한 값을 보관하므로 기록과 표시 객체가 해제돼도 다시
만들 수 있습니다. 아이템 해제는 문서에 남아 있는 주석을 지우지 않습니다. 기존
문서·장면 복구 장치는 작업 중의 롤백을 위해 목록·값·표시 객체를 함께 캡처합니다. 저장 형식과 GUI·헤드리스 공통 렌더러는 그대로 유지합니다.
상태 읽기는 실제 아이템이나 문서 레코드를 사용하며, 임의의 Qt role-9 사전을 별도
원본으로 사용하지 않습니다. 테스트도 같은 레코드와 표시 객체를 생성합니다.

이미지 레코드는 원본 인코딩 데이터·위치·크기·불투명도·종횡비 잠금을, 오비탈 레코드는
종류·중심·배율·회전을 보관합니다. 편집은 레코드를 갱신한 뒤 표시 객체를 다시 그립니다.
Qt 변환이나 데이터 역할만 바꾸는 것은 문서 편집이 아닙니다. 이미지 삽입과 붙여넣기의
용량 제한도 표시 객체의 생존 여부와 관계없이 문서의 모든 활성 이미지를 셉니다.

고리 채움 레코드는 원자 ID의 순서·색·정밀 불투명도를 보관하며, 좌표는 현재 분자
그래프에서 계산합니다. 저장과 복사는 다각형의 존재 여부에 관계없이 문서를 읽습니다.
고리를 끊는 삭제는 채움도 제거하며 Undo는 원래 문서 순서를 복구합니다. 표시 객체가
사라진 고리를 편집할 때는 같은 기록 ID로 다시 그립니다. 교체된 이전 객체가 나중에
해제돼도 Undo 데이터를 지우지 못하도록 기록 정리 책임도 이전합니다. Qt 브러시나
데이터 역할은 고리 상태의 원본이 아닙니다.
고리는 원자를 통해 그룹에 포함되며, 저장 그룹 형식에 별도 고리 아이템 인덱스를
추가하지 않습니다.

노트 기록은 평문·정제한 HTML·위치·회전을 소유합니다. Qt 편집기는 커서·포커스·텍스트
Undo를 담당하고 입력과 서식 변경 결과를 기록에 반영합니다. 표식 기록은 종류·텍스트·
소속 원자·오프셋·중심·색상을 소유하며 Qt 메타데이터는 이 기록에서 읽습니다. 저장,
원자에 붙은 표식 복사, 전하·라디칼 계산은 표시 객체가 없어도 기록을 읽습니다.
복구 중 위치·글꼴·텍스트를 차례로 되돌릴 때 생기는 중간 신호가 결과를 바꾸지 않도록
네이티브 상태 복원 후 캡처한 문서 기록을 복원합니다.
([ADR 0010](adr/0010-document-owned-notes-and-marks.md))

### 공통 주석 렌더링

`ui.annotations`는 Qt 주석 경계를 한 패키지로 묶습니다.

| 모듈 | 책임 |
| --- | --- |
| `items` | 노트·이미지·오비탈·고리 채움 Qt 아이템 구현 |
| `materialize` | 렌더 컨텍스트와 저장 상태로 주석 생성 |
| `graphics`, `arrows` | 주석 그리기와 화살표 렌더링 |
| `records` | 도형·TS 괄호 레코드와 표시 객체 연결 |
| `marks` | 표식의 네이티브 그래픽과 문서 값 연결 |
| `state` | Qt 경계에서 주석 상태 읽기·적용 |
| `projections` | 문서 ID 조회와 이력 재생 중 사라진 표시 객체 복원 |
| `text` | 공통 노트 글꼴·서식 적용 |

```mermaid
flowchart LR
    editor["SceneItemController"] --> create["annotations.materialize"]
    headless["헤드리스 장면 컨텍스트"] --> create
    create --> values["AnnotationCollection<br/>문서가 소유하는 8종"]
    create --> view["Qt 주석 아이템"]
    values --> save["문서 저장"]
    editor --> lifecycle["부착 / 제거 / 이력 연동"]
```

편집기는 노트 포커스 처리와 생성된 아이템의 부착을 담당합니다. 생성·서식·기하 처리는
헤드리스 장면과 같은 구현을 사용합니다. 종류별 복원 전달 함수 7쌍과 별도의 상태
재노출 모듈을 제거했습니다. 이 패키지는 편집 제스처나 이력 스택을 소유하지 않습니다.

### 문서 ID를 사용하는 그룹과 히스토리

`domain.document.groups`의 `SceneGroup`은 원자 ID와 주석 ID를 보관합니다. 저장과
복사는 표시 객체의 생존 여부와 관계없이 문서 순서로 ID를 해석합니다. 저장 파일의
그룹 형식은 그대로입니다.

주석·고리 기하·그룹·표식 소속·텍스트와 서식 변경 명령은 ID와 값을 보관합니다.
`CanvasHistoryOperations`가 재생 시 표시 객체를 찾고, `annotations.projections`는
살아 있는 객체를 재사용하거나 같은 ID로 다시 만듭니다. 약한 참조 캐시는 아이템의
수명을 늘리지 않습니다. 교체 시 기록 정리 책임을 이전하고, 재생 실패 시 캐시도
롤백합니다. Undo는 문서 순서·선택·깊이·분자 그림과의 쌓임 순서를 복원합니다.
서식 명령은 복사한 Qt 값 타입을 사용하지만 위젯·그래픽 아이템·캔버스를 붙잡는
콜백은 보관하지 않습니다.

`history_canvas_access`와 `history_recording_access` 전달 모듈을 제거했습니다.
소비자는 `DocumentSavepoint`, 히스토리 어댑터, 이력 기록 서비스의 실제 소유자에게
직접 요청합니다. ([ADR 0011](adr/0011-document-identities-for-groups-and-history.md))

```mermaid
flowchart LR
    groups["SceneGroup<br/>원자 ID · 주석 ID"] --> document["문서 컬렉션"]
    history["히스토리 명령<br/>ID · 값 · 순서"] --> replay["CanvasHistoryOperations"]
    replay --> resolve["annotations.projections"]
    resolve --> document
    resolve --> qt["Qt 표시 객체<br/>재사용 / 재생성"]
```

### 남은 설계 개선

주석 8종의 값과 순서, 그룹 멤버십, 장기간 보관하는 히스토리 데이터가 문서 ID와
값을 사용합니다. 이는 완료한 소유권 경계이며 전체 설계의 완료율은 아닙니다.
이력 재생은 사라진 주석 표시 객체를 복원하지만, 외부에서 손상된 장면 전체를
자동 복구하는 기능은 아닙니다. 이번 범위 밖의 편집기 접근·포트·서비스 전달 모듈은
일부 남아 있습니다. 제스처 상태와 작업 중의 롤백 스냅샷은 정확한 복원을 위해
다루는 Qt 객체를 일시적으로 보관합니다.

## 트랜잭션 및 복구 라이프사이클

- **원자적 트랜잭션**: `DocumentSavepoint`가 문서 전체 상태를 캡처하여 검증하고, 실패 시 안전하게 롤백합니다 ([ADR 0002](adr/0002-single-rollback-kernel.md)).
- **히스토리 관리**: `CanvasHistoryService`가 Undo/Redo 명령과 롤백용 스택 스냅샷을 관리합니다. 명령은 문서 ID와 값을, 작업 중의 롤백 스냅샷은 정확한 네이티브 상태를 보관합니다.
- **비활성 히스토리**: 히스토리를 비활성화하는 것은 문서 교체(`CanvasDocumentSessionService.apply_state`)뿐이며, 그동안 편집기는 실행되지 않습니다. 비활성 상태에서 `CanvasHistoryService.push`는 모든 편집을 예외로 거부하고 편집기의 트랜잭션이 문서를 되돌립니다. 편집기는 이 상태를 직접 검사하지 않습니다 ([ADR 0020](adr/0020-history-refuses-edits-while-disabled.md)).
- **자동 저장 및 세션 복구**: 앱 시작 시 빈 작업공간을 열며, **File ▸ Recover Unsaved Work…**에서 비정상 종료된 세션의 스냅샷을 저장되지 않은 새 사본으로 제공합니다 ([ADR 0017](adr/0017-explicit-recovery-and-editor-state-policies.md)). 예기치 않은 종료는 애플리케이션 캐시의 PID 바인딩 세션 매니페스트로 추적됩니다.

## 데이터 및 렌더 흐름

### 대화형 편집 흐름

```mermaid
flowchart LR
    view["CanvasView<br/>(pointer / keys)"] --> tool["Tool / input controller"]
    tool --> edit["Editing controller"]
    edit --> model["Current document model"]
    edit --> scene["Qt graphics / renderer"]
    tool --> transaction["Gesture / command transaction"]
    transaction --> history["HistoryCommand<br/>commit / rollback"]
```

### 헤드리스 문서 작업 흐름
헤드리스 CLI 명령(`inspect-document`, `apply-patch`, `render-document`)은 GUI 창이나 세션 복구 없이 독립적으로 소스를 검증하고 실행합니다.

### 기존 계산 계획
문서에 이미 저장된 계획은 현재 그림과 맞을 때 유지됩니다. 그 계획이 빠지는 저장은 거부됩니다. Chemvas는 반응을 대응시키거나 `machine.json`을 쓰지 않습니다 ([ADR 0035](adr/0035-retire-rdkit-chemistry-provider.md)).

## 화학 및 파일 형식 제약 사항

- **내보내기 범위**: 분자 내보내기는 화학 그래프 데이터만 포함하며, 분자가 아닌 주석(화살표, 대괄호, 텍스트)은 제외합니다. 약어 라벨은 펼치지 않습니다.
- **지원되는 작용기 약어**: `ATOM_ALIAS_DEFINITIONS`에 정의된 정규 별칭:
  `Me`, `Et`, `OH`, `NH2`, `SH`, `Ph`, `PPh3`, `OMe`, `Boc`, `CO2Me`, `t-Bu`, `tBu`, `i-Pr`, `CF3`, `OTs`, `Ts`, `OMs`, `Ms`, `OTf`, `Tf`, `Ns`, `OAc`, `Ac`.
- **입체화학**: 쐐기/해시 결합은 단일 결합에만 적용됩니다.
- **형식 호환성**: Chemvas는 문서 버전 7, 8, 9를 읽으며, 저장 시 버전 9(스키마 1)로 기록합니다.

## 아키텍처 결정 기록 (ADR)

ADR을 언제 쓰는지, 작성 규칙과 템플릿은 [ADR 안내](adr/README.md)에 있습니다(영어).

- [ADR 0001: 기능 지향 모듈화](adr/0001-feature-oriented-modularization.md)
- [ADR 0002: 단일 롤백 커널](adr/0002-single-rollback-kernel.md)
- [ADR 0003: 선택 이동 저장점 범위](adr/0003-scoped-move-savepoint.md)
- [ADR 0004: 뷰 독립적 장면 렌더링](adr/0004-view-independent-scene-rendering.md)
- [ADR 0005: 책임을 기준으로 한 편집기 경계](adr/0005-responsibility-based-editor-boundaries.md)
- [ADR 0006: 문서가 소유하는 도형](adr/0006-document-owned-shapes.md)
- [ADR 0007: 문서가 소유하는 주석 컬렉션](adr/0007-document-owned-annotation-collections.md)
- [ADR 0008: 공통 주석 렌더링과 문서 레코드](adr/0008-shared-annotation-rendering-and-records.md)
- [ADR 0009: 문서가 소유하는 고리 채움](adr/0009-document-owned-ring-fills.md)
- [ADR 0010: 문서가 소유하는 노트와 마크](adr/0010-document-owned-notes-and-marks.md)
- [ADR 0011: 그룹과 히스토리의 문서 ID](adr/0011-document-identities-for-groups-and-history.md)
- [ADR 0012: 평탄한 편집기 런타임과 `ui` 하위 패키지](adr/0012-flat-editor-runtime-and-ui-packages.md)
- [ADR 0013: 모듈 분할, 창 포트, `core` 범위](adr/0013-editor-followups-splits-ports-core-scope.md)
- [ADR 0014: 캔버스·창 상태의 단일 표기](adr/0014-one-spelling-for-canvas-and-window-state.md)
- [ADR 0015: 모델·장면 아이템 접근의 소유자, Qt 없는 `features`](adr/0015-owners-and-qt-free-features.md)
- [ADR 0016: 타입이 있는 창 경계와 상태 쓰기의 소유자](adr/0016-typed-window-boundary-and-state-owners.md)
- [ADR 0017: 명시적 복구와 편집기 상태 정책](adr/0017-explicit-recovery-and-editor-state-policies.md)
- [ADR 0018: 반응 쌍 핸드오프와 폐기된 precomplex](adr/0018-reaction-pair-handoff-and-retired-precomplex.md)
- [ADR 0019: 반응 쌍 핸드오프와 해석하지 않는 끝점 보관 데이터](adr/0019-reaction-pair-handoff-and-opaque-endpoint-archives.md)
- [ADR 0020: 비활성 히스토리는 편집을 거부한다](adr/0020-history-refuses-edits-while-disabled.md)
- [ADR 0021: 대칭을 기준으로 세는 고리 변화 원자 대응](adr/0021-ring-changing-correspondences-up-to-symmetry.md)
- [ADR 0022: 명시적 반응식 배치 연결 요소](adr/0022-explicit-reaction-layout-connectors.md)
- [ADR 0023: 데스크톱 반응식 배치 기능 제거](adr/0023-retire-desktop-scheme-arrangement.md)
- [ADR 0024: 벤젠 미리보기와 삽입의 공통 배치 계획](adr/0024-shared-benzene-placement.md)


### 통합한 편집 책임

`CanvasMoveController.set_atom_positions`가 상대 이동과 함께 원자 위치의 절대
적용을 소유합니다. History와 선택 변환이 같은 소유자를 사용하며, 명시적 깊이의
정확한 복원과 화면 이동에 따른 깊이 보존을 구분합니다
([ADR 0025](adr/0025-shared-atom-position-mutation.md)).

도형·괄호·화살표의 회전과 반전은 Qt-free record 변환을 사용하며, History의 상태
코덱은 UI 경계에 남습니다
([ADR 0027](adr/0027-record-based-annotation-transforms.md)).

단순 결합 길이·속성 Undo 명령은 `history_command_transaction`을 재사용합니다.
문서 교체 스냅샷은 테스트 전용 대체 장면 대신 실제 Qt 장면 계약을 사용합니다.

브라우저 화학 클립보드는 기존 선택 페이로드 빌더와 붙여넣기 계획기를 재사용하여
별도의 화학 스키마 없이 원자 ID 재매핑, 그룹 및 주석 변환을 보존합니다. 브라우저
자동 복구 드래프트는 Qt 복구와 분리되어 `bootstrap/web_drafts.py`가 단일 서버
프로세스 잠금과 봉투 저장을 소유합니다
([ADR 0032](adr/0032-browser-clipboard-and-drafts.md)).

- [ADR 0025: Shared atom position mutation](adr/0025-shared-atom-position-mutation.md)
- [ADR 0026: Endpoint selection draft](adr/0026-endpoint-selection-draft.md)
- [ADR 0027: Record-based annotation transforms](adr/0027-record-based-annotation-transforms.md)
- [ADR 0028: 설정 가능한 용지 크기](adr/0028-configurable-paper-dimensions.md)
- [ADR 0029: 기존 편집 소유자 기반의 브라우저 화면 어댑터](adr/0029-browser-adapter.md)
- [ADR 0031: 독립 계약 검증](adr/0031-standalone-contract-validation.md)
- [ADR 0032: 브라우저 화학 클립보드와 복구 드래프트](adr/0032-browser-clipboard-and-drafts.md)
- [ADR 0035: RDKit 화학 provider 제거](adr/0035-retire-rdkit-chemistry-provider.md)
