# CDXML 내보내기

[English](CDXML_EXPORT.md)

Chemvas는 파일 > 그림 내보내기(`.cdxml` 형식)와 CLI
`render-document --output file.cdxml`로 편집 가능한 CDXML(ChemDraw XML)을
내보냅니다.

ChemDraw 검증 범위는 아래에 명시한 사례로 한정되며 전체 문서의 시각적
동등성을 뜻하지 않습니다. CDXML 가져오기는 지원하지 않으며,
`.chemvas` 형식이 문서 원본입니다.

## 지원

| 영역   | 출력 내용                                                |
|--------|----------------------------------------------------------|
| 원자   | 순수 원소(주기율표), 색상, 명시적 C, Charge 주석; 그룹 라벨 `Me`, `Ph`, `tBu`는 내부 그래프 전체를 담은 `Nickname` 노드로 출력(아래 원자 라벨 참조) |
| 결합   | single/1, double_center/2 (`Center`), 옆배치 double/2 및 double_outer/2 (그려진 선 기준 `Left`/`Right`, 벤젠 및 고리 이중결합 포함), triple/3, single 스타일로 저장된 레거시 2/3차 결합, 시작 원자가 좁은 끝인 쐐기/1 (`WedgeBegin`) 및 해시/1 (`WedgedHashBegin`); bold_in/1 및 bold_out/1 (`Bold`, 아래 네이티브 굵은 결합 참조) |
| 직선   | 머리 없는 실선·굵은 선·파선(`LineType="Dashed"`, 소비 프로그램 대시 무늬), 방향을 보존한 Tail3D/Head3D |
| 화살표 | 그룹 선 구성요소(축 + 머리), M/L 경로 명령만               |
| TS 괄호 | `square_pair`, `square_left`는 그려진 M/L 꼭짓점의 그룹 내 머리 없는 arrow; `dagger`, `double_dagger`는 정확한 글리프를 담은 `<t>` 하나(아래 파선과 TS 괄호 참조) |
| 도형   | rect, circle; 선만, 채움만, 또는 같은 색                  |
| 노트   | 줄별 `<t>`, 실행별 실제 폰트 패밀리, 크기, 굵기, 색상      |
| 기타   | 아무것도 그리지 않는 고리 기록(선 없고 투명한 기본 채움)은 고리 구조 내보내기를 위해 무시됨 |

## 거부 (파일 작성 전 오류 발생)

| 영역   | 거부 내용                                                |
|--------|----------------------------------------------------------|
| 원자   | 그 밖의 별명(Ac/Ts, `t-Bu`, `Et`, `OMe` 포함), 형식화된 바인딩이 없는 `Hᵃ` 같은 식별자 수소, 일반 단일 연결이 정확히 하나가 아닌 고정 fragment 라벨, 지원하지 않는 연결의 generic aryl, 전하/라디칼이 있는 라벨, 라디칼, 지원하지 않는 독립 장면 마크; 숨겨진 원자는 제외되고 해당 결합은 거부됨 |
| 결합   | bold_center, 단일 order가 아닌 굵은 결합, 정확한 정수 order 1이 아닌 화학 점선, double_either; 그려진 옆선이나 좁은 시작 방향을 확인할 수 없는 결합; 스타일/순서 불일치 |
| 직선   | 물결; 미러                                          |
| TS 괄호 | 둥근 괄호, 중괄호; 변환·반투명·외곽선 항목; 기록을 그리지 않는 항목; 단검 글리프 대체 폰트 |
| 화살표 | 곡선, 이중, 기타 종류, 라벨, 미러                          |
| 도형   | 타원, 둥근 사각형, 파선/점선 획, 반투명 채움, 혼합 색상     |
| 노트   | 이탤릭, 밑줄(대시/점/물결 포함 모든 스타일), 윗줄, 취소선, 미지원 수직 정렬, 대소문자 변환(대문자, 작은 대문자), 사용자 지정 단어 간격, 기본값 외 폰트 확장, 목록, 표, 비균일·비등각·투영 변환, 400/700 이외 두께, 왼쪽 정렬 아닌 경우, 상자/테두리, 윤곽이 없는 글리프, 모호한 혼합 글꼴 cluster·surrogate 매핑 |
| 겹침 | 교차 fragment의 실제 잉크 겹침; fragment 레이어 사이 노트 잉크 접촉; 직선·화살표·단검 TS 괄호의 경계 접촉; paint 순서를 뒤집는 사각 bracket 획 접촉; child 표식의 검증되지 않은 잉크 겹침; 다른 원자·결합이 나누는 항목 paint 순서; INT16 drawable `Z` 초과(32767) |
| 기타   | 눈에 보이는 고리 채움(획 또는 투명도 > 0 채움), 이미지, 오비탈, 원근법, 그룹, 빈 페이지 |

## 원자 라벨

라벨의 의미가 형식화되어 있을 때만 화학 정보와 함께 내보냅니다. 라벨 문자열, 색, 이웃 원자, 범례로 의미를 추측하지 않습니다. 그려진 라벨 문자열, resolved 폰트 이름, 색, 기준선은 유지합니다. 크기는 네이티브 형식의 0.05 pt 단위로 가장 가까운 값에 기록하므로 인코딩 오차는 최대 0.025 pt입니다. 공통 라벨 배치의 시작·끝 기준에 맞춰 Left/Right 정렬을 명시합니다(ADR 0048). 네이티브 기준선과 실제 폰트 face 차이는 남을 수 있습니다.

- **순수 원소 기호**는 이전과 같이 `<n Element=Z>`가 됩니다.
- **`Me`, `Ph`, `tBu`**는 `NodeType="Nickname"` 노드가 됩니다. 각 노드는 그룹의 탄소(메틸은 `NumHydrogens` 3, 페닐은 ipso 탄소 하나를 가진 Kekulé 고리, tert-부틸은 중심 탄소와 메틸 셋)와 바깥 이웃 위치에 놓인 `ExternalConnectionPoint` 하나를 담은 내부 `<fragment>`를 가집니다. 바깥 결합은 native `B`/`E` 순서를 유지하고 nickname 노드에 연결됩니다. 그룹에는 일반 단일 연결이 정확히 하나 있어야 합니다. 연결이 없거나 여러 개인 경우, 이중/삼중/쐐기/해시 연결, 그룹의 전하·라디칼 주석은 거부합니다. 다른 별명도 거부합니다.
- **literal `Ar`**는 명시적인 의미 바인딩이 없으면 모호하므로 거부합니다. `generic_aryl()`은 표시 `Ar`를 유지한 `Nickname` 안에 native `GenericNickname="ARY"` query를 둡니다. 명시적 `element_identity("Ar")`는 아르곤으로 유지하며 특정 고리·치환 위치를 추론하지 않습니다.
- **위첨자 소문자 식별자가 붙은 `H`**(`Hᵃ`, `Hᵇ`)는 형식화되지 않으면 거부합니다. 동위원소, 전하, 헬륨으로 해석하지 않습니다.

호출자는 `preflight_cdxml(..., label_bindings={atom_id: CdxmlLabelBinding...})`로 형식화된 의미를 넘기고, 같은 매핑을 `serialize_cdxml`에도 넘깁니다.

| 바인딩 | 적용 대상 | 출력 |
|--------|-----------|------|
| `element_identity("Ar")` | `Ar` | `Element="18"` |
| `element_identity("H")` | `H` + 위첨자 문자 | `Element="1"`, `Isotope` 없음, 라벨 그대로 |
| `generic_aryl()` | 기존 order-1 single/wedge/hash/dotted 연결 0~2개인 `Ar` | 표시 `Ar` nickname 안에 `ARY` query, 연결이 있으면 공유 외부 접속점 하나 |
| `aryl_fragment("Ph")` | 일반 단일 연결 하나인 `Ar` | 페닐 그래프를 가진 `Nickname`, 라벨 `Ar` |
| `aryl_label(author_note)` | `Ar` (typed API 또는 v2 sidecar;보내기 범위에서 보이는 atom) | 페이지 `<t InterpretChemically="no">`에 보이는 `Ar`(장면 라벨 위치·글꼴), `author_note`·캡션 메타데이터용 Chemvas `objecttag`; Ar용 `<n>` 없음. 기록용이 아닌 결합이 문서에 남아 있으면(상대 endpoint가 선택 밖이어도) 거부 |

각 의미는 자기 필드 하나만 정확한 `str`로 받습니다(`element_identity`는 `element`, `aryl_fragment`는 `fragment`, `generic_aryl`은 없음). 불필요하거나 충돌하는 필드, 빠지거나 `str`이 아닌 값, 알 수 없는 의미를 가진 바인딩은 거부하며, 버리거나 변환하지 않습니다.

바인딩은 `.chemvas` 파일에 저장되지 않습니다. CLI는 명시적 sidecar에서만 바인딩을 받고 GUI는 받지 않으므로, GUI의 모호한 `Ar`는 거부합니다. typed export plan에서 표시문자와 화학적 의미를 구분합니다. `ARY`는 불특정 aryl query이며 구체적인 고리·분자식을 뜻하지 않습니다.

generic aryl이 order-1 쐐기/해시의 넓은 끝에 있으면 B/E 및 native
WedgeBegin/WedgedHashBegin 방향을 유지합니다. 좌우 반전한 O/P→Ar 대조군 8개에서
저장·새 프로세스 재열기 후 ARY 정의, Element=18 부재, 끝점 및 좁은 끝부터 넓어지는
표시를 확인했습니다. 실제 OMe의 generic-Ar 입체결합 28개도 보존됩니다. 불특정 query의
절대 CIP 배치나 고정 phenyl 의미를 추정하지 않습니다. aryl_fragment("Ph")의
쐐기/해시, 바인딩 없는 모호한 Ar, 저장된 bond.a와 반대인 그림 방향은 계속 거부합니다.

### 라벨 바인딩 sidecar (CLI)

`render-document --cdxml-label-bindings labels.json`은 그림을 그려 각 라벨의
의미를 아는 사람이 작성한 엄격한 JSON sidecar를 읽습니다. Chemvas는 sidecar를
스스로 만들지 않으며 의미를 추측하지 않습니다.

```bash
chemvas render-document doc.chemvas --output out.cdxml --cdxml-label-bindings labels.json
```

```json
{
  "format": "chemvas-cdxml-label-bindings",
  "version": 1,
  "source_sha256": "<SHA-256 of the exact .chemvas bytes>",
  "bindings": [
    {"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"},
    {"atom_id": 4, "expected_label": "Ar", "meaning": "aryl_fragment", "fragment": "Ph"},
    {"atom_id": 7, "expected_label": "Hᵃ", "meaning": "element", "element": "H"}
  ]
}
```

- `source_sha256`은 입력 `.chemvas`의 정확한 바이트의 SHA-256입니다. 문서를
  편집하거나 바꾸면 값이 달라지고, 다른 바이트용으로 작성된 sidecar는
  거부됩니다. CLI는 문서를 한 번만 읽으며, 해시·라벨 검사·내보낸 그림이 모두
  같은 바이트에서 나옵니다.
- 각 바인딩은 `atom_id` 하나, 정확히 그려진 라벨 `expected_label`(코드포인트
  단위 비교, 정규화 없음), `meaning` 하나를 가집니다. `meaning`은
  `element`(`element` 필드와 함께), `generic_aryl`, `aryl_fragment`(`fragment`
  필드와 함께) 중 하나입니다. 이후 exporter가 위 바인딩 표를 적용하며 여전히
  거부할 수 있습니다.
- 출력을 쓰기 전에 거부: 엄격하지 않은 JSON(중복 키, NaN/Infinity, 뒤따르는
  데이터), 잘못된 `format`·`version`, 알 수 없는 키·의미, 잘못된 타입
  (`bool`이나 `1.0`은 atom id가 아님), 빈 바인딩 목록이나 중복 바인딩, 해시
  불일치, 없거나 숨겨졌거나 내보내기 범위 밖의 atom, 라벨 불일치, 그리고
  exporter의 모든 거부.
- SVG, PDF, PNG 출력에 이 옵션을 쓰면 오류입니다. 내보내기에 실패해도 기존
  파일은 그대로이며, 원본 문서는 수정되지 않습니다.
- 보고서에 sidecar 경로, sidecar SHA-256, 결속된 원본 SHA-256, 적용된 바인딩을
  담은 `cdxml_label_bindings`가 추가됩니다. 버전 `2` sidecar는 같은 블록에
  `version`과 `documentary_contacts`도 포함하고, 버전 `1` 보고서 형식은 그대로입니다.

**버전 2(기록용 TS 접촉).** `documentary_contacts`와 `aryl_label` 바인딩을
추가합니다. 목록의 각 접촉은 보내는 문서의 order-1 점선 결합과 일치해야
하고, 허용된 접촉만 화학 `<b>`가 아닌 파선 그래픽으로 나갑니다. 그 밖의
order-1 점선 결합은 화학 `<b Order="1" Display="Dash">`로 유지됩니다. `aryl_label`의 `Ar`는 화학 노드가 아닌 페이지 캡션으로
보내고, Ar에 기록용이 아닌 화학 결합이 남아 있으면 거부합니다. ChemDraw
25.0.2.14에서는 이전 `Unspecified`·`GenericNickname` 노드 인코딩 모두 Save As
후 아르곤(`Element="18"`)으로 열리는 것이 관측되었습니다.
[ADR 0038](adr/0038-documentary-contacts-and-aryl-labels.md) (Proposed). 소비자
표시·메타데이터 유지·화학 라운드트립은 검증되지 않았으며 통과를 주장하지
않습니다.

sidecar는 `.chemvas` 스키마나 GUI를 바꾸지 않습니다. 실제 그림의 바인딩은 그
그림의 작성자가 정해야 하며, 테스트 fixture의 바인딩은 실제 `Ar`나 `Hᵃ`의
의미에 대해 아무것도 말하지 않습니다.

## 파선과 TS 괄호

그려진 기록을 하나의 균일 배율로 그대로 따릅니다. 추측, 정렬, 평탄화는 하지 않습니다.

- **파선**(`line_dashed`): 실선과 같이 기록의 끝점 순서, 화살표 선 두께와 색을 가진 `<arrow LineType="Dashed">` 하나입니다. CDXML `LineType`에는 대시 길이와 간격이 없으므로 대시 무늬는 소비 프로그램이 그리며 Chemvas 무늬와 다를 수 있습니다. 선은 파선으로 남습니다. 실선 조각으로 나누거나 이미지로 바꾸지 않습니다.
- **사각 TS 괄호**(`square_pair`, `square_left`): 장면과 같은 사각형과 결합 길이로 만든 `bracket_path_commands`의 `L` 명령마다 머리 없는 `arrow` 하나를 담은 `<group>` 하나입니다. 두께는 `bracket_stroke_width(bond_line_width)`에 배율을 곱한 값이고 색은 항목의 칠 색입니다. 꼭짓점은 정확하며, 모서리 이음과 선 끝 모양은 소비 프로그램이 그립니다(장면은 평평한 끝과 마이터 이음으로 그림).
- **단검 TS 괄호**(`dagger`, `double_dagger`): `bracket_symbol_layout`의 기준선 위치에 정확한 † (U+2020) 또는 ‡ (U+2021)을 담은 `<t>` 하나입니다. 글리프 폰트의 실제 패밀리와 픽셀 크기에 배율을 곱한 크기를 씁니다. 대체 폰트가 필요하거나 윤곽이 없는 글리프는 거부합니다.
- 거부: 둥근 괄호와 중괄호(3차 곡선 획), 이동·확대·회전·반투명·외곽선이 있는 괄호 항목, 기록의 경로를 더 이상 그리지 않는 항목, 글리프 실행이나 폰트가 종류와 맞지 않는 단검.
- 겹침: z 순서에서 결합된 분자의 결합과 원자 라벨 사이에 있는 괄호(기본 z값)는 그 분자의 원자·결합 항목 바운딩 렉트에 닿으면 거부됩니다. 사각 괄호는 자기 바운딩 렉트가 아니라 실제로 그리는 영역으로 비교합니다. 정확한 획 사각형(두께 `bracket_stroke_width(bond_line_width)`, 평평한 끝, 마이터로 채운 모서리)에, 소비 프로그램이 사각 끝을 그릴 수 있으므로 자유 끝마다 두께의 절반을 더한 영역입니다. 그래서 구조를 둘러싼 괄호도 획이 분자에 닿지 않으면 내보내며, 맞닿기만 해도 접촉으로 봅니다. 단검 괄호와, 그리는 영역을 정확히 정할 수 없는 사각 괄호는 바운딩 렉트 규칙을 그대로 씁니다. 이때 분자는 괄호 위에 프래그먼트 하나로 쓰이며, 둘이 겹치지 않으므로 그려진 영역의 순서는 바뀌지 않습니다.
- Z 순서: CDX ZOrder 속성(`Z`, INT16)은 Node, Bond, Text, Graphic/Arrow 객체에 적용되고 Group, Fragment, Page에는 적용되지 않습니다. `Z`가 없으면 0으로 보고, 0끼리의 순서는 정해지지 않습니다. 그래서 모든 `n`, `b`, `t`, `graphic`, `arrow`(괄호 획과 화살표 선분 하나하나 포함)이 자기 양수 `Z`를 가지며 `group`과 `fragment`에는 쓰지 않습니다. 페이지 객체는 장면 순서를 지키며 각각 연속된 블록 하나를 받습니다. 분자 안에서는 원자와 결합이 장면에서 그려지는 순서를 따르고, 노드 바로 뒤에 축약 그룹과 라벨이 옵니다. 32767을 넘으면 출력 전에 거부합니다.

## 축척

하나의 균일 축척 `s = out_w_pt / source_w`가 모든 좌표, 폰트 크기, 선 너비,
기하에 적용됩니다. `--width-mm`을 지정하지 않으면 CLI는 결합 길이 기준으로
크기를 정합니다(고정 페이지 너비 없음). GUI 사용자 지정 너비 기본값은
84 mm입니다. 170 mm 페이지는 `--width-mm 170`으로 지정합니다.
수치 정밀도는 유효 숫자 12자리입니다.

## 폰트 처리

원자 라벨의 기존 resolved-font·대체 글꼴 guard는 유지합니다. 노트는 실제
QTextDocument paint glyph run의 글꼴과 픽셀 크기를 사용합니다. 단순 혼합 글꼴
텍스트는 원래 UTF-16 문자 순서의 기존 `<s>` run으로 나누며 행 기준선·색·face를
유지합니다. 모호한 cluster, surrogate, 역방향 위치, 서로 다른 기준선·face와
윤곽이 없는 글리프는 거부합니다. 글꼴 설치나 원문 대체는 하지 않습니다.

## GUI 및 CLI

- **GUI**: 파일 > 그림 내보내기 > CDXML 형식. 대화상자 라벨:
  "CDXML - ChemDraw XML (not verified in ChemDraw)".
- **CLI**: `chemvas render-document doc.chemvas --output out.cdxml`
  (`--width-mm`, `--background`, 위 sidecar용 `--cdxml-label-bindings`도
  사용 가능). `--min-font-pt`는 CDXML 출력에서 지원하지 않습니다.

## 원본 형식

`.chemvas` 원본 문서는 내보내기로 수정되지 않습니다. 파일 작성 전 사전 검사를
수행하므로 오류 발생 시 기존 대상 파일이 보존됩니다. CDXML 가져오기는 지원하지
않으며, `.chemvas` 형식이 편집 원본으로 유지되고 CLI 내보내기는 완전한 왕복 변환이
아닙니다.

## 제한 사항

- 이중결합 배치 규칙: `DoublePosition`은 원자 B에서 원자 E를 바라보는 기준으로
  그려진 선 오프셋에 따라 `Left` 또는 `Right`로 출력되며, 공개 CDXML 규격 미러
  ([ChemApps CDXML reference](https://chemapps.stolaf.edu/iupac/cdx/sdk/IntroCDXML.htm)의
  B→E 방향 기준 오른쪽 보조선 정의)와 일치합니다. 외부 렌더러 및 ChemDraw에서의
  실제 시각적 외형은 검증되지 않았습니다.
- 화학 소비자: 이 버전은 RDKit 소비자 검사를 실행하지 않습니다.
  ChemDraw에서의 완전한 시각적 동등성은 검증되지 않았습니다.
- Nickname, GenericNickname, ExternalConnectionPoint 노드와 그 내부 좌표,
  `NumHydrogens`, 해당 노드의 원래 라벨 `<t>`는 공개 CDX 규격 미러를 따릅니다.
  아래의 제한된 generic aryl 저장·재열기 결과는 ChemDraw 25.0.2.14에서 확인했습니다.
  native 그룹 전개·대화식 재연결과 다른 소비자 동작은 검증되지 않았습니다.
- 그룹화된 화살표와 도형은 네이티브 ChemDraw 반응 도구가 아닌 CDXML
  그래픽으로 내보내집니다.
- 완전한 CDXML 호환성, DTD 유효성, 가져오기/완전한 왕복 변환, 광범위한 소비자 상호운용성을
  주장하지 않습니다.
- DTD는 포함되지 않으며 DTD 유효성은 주장하지 않습니다.
- 폰트 charset, U+2028 소프트 줄바꿈, 탭 문자, 둥근 끝/연결, 수소 추론,
  `CaptionLineHeight`는 출력되지만 소비자 동작은 검증되지 않았습니다.

### 기존 dotted 화학 결합

기존 `Bond.style="dotted"`와 정확한 정수 order 1은 화학 fragment의
`<b Order="1" Display="Dash">`로 출력합니다. 끝점과 화학 그래프를 유지합니다.
독립적인 `Arrow.kind="line_dashed"`는 dashed page arrow으로 유지합니다.
명시적 documentary permission만 기존 비화학 graphic 계약을 사용합니다.
화학 dotted 결합과 literal/generic Ar 연결의 다른 order 및 mutable bool/float
order는 preflight와 serializer에서 거부합니다. 이 정확한 타입 검증 주장은
별도의 명시적 documentary API를 포함하지 않습니다.
명시적 generic aryl은 기존 바깥 연결 0~2개를 유지하며 3개 이상은 거부합니다.
내부에는 ARY query와, 연결이 있으면 첫 이웃 좌표의 공유 ExternalConnectionPoint
하나를 둡니다. 특정 aryl 원자·치환 위치를 추론하지 않습니다. ChemDraw 25.0.2.14
저장·재열기에서 OMe의 ARY 정의 48개와 바깥 결합 238개가 유지됐으며 아르곤으로
바뀐 노드는 없었습니다. 단일 연결 query 하나에는 분자식 계산 불가 경고가
남으며, 두 접촉 query에는 이 경고가 없습니다. 실제 아르곤은 혼합 witness에서 별도로 대조합니다. 이는 native 그래프
보존 검사이며 수동 편집·그룹 확장·검색엔진 의미 검증은 아닙니다.
[ADR 0042](adr/0042-native-generic-aryl-meaning.md)를 참고합니다.

## 노트 회전

노트는 양의 균일 affine 확대와 회전에서 실제 paint 글꼴 선언과 변환된 텍스트
기준선을 보존합니다. `RotationAngle`은 부호 있는 각도에 65536을 곱한 값이며,
기울이기, 반사, 비균일 확대와 투영 변환은 거부합니다. ChemDraw는 글꼴을
대체할 수 있습니다. 실제 한글 노트는 저장·재열기 후 텍스트와 기준선이
유지되었지만 글꼴과 글리프 범위가 바뀌었습니다. 소비자 환경의 글꼴이 다르면
이 매핑은 동일한 글리프 geometry를 보장하지 않습니다.

## 원자에 붙은 텍스트 표식

원자에 붙은 가시적인 plus/minus 표식은 원래 글리프·글꼴·변환된 기준선을
상대 offset을 갖는 node child objecttag로 보존한다. ChemDraw 25에서 개별 원자
이동, Undo/Redo, 저장·재열기 후 표시와 부착 관계를 확인했다. 프로듀서는 원래
node Charge를 계속 출력하지만 소비자 재저장에서 이 값이 사라진 사례가 있다.
전하 추론이나 화학분석 의미 보존을 보장하지 않는다. 독립 표식, 지원하지 않는
변환, child paint 순서가 검증되지 않은 잉크 겹침은 거부한다. 사각 bracket의
interleaving은 실제 잉크와 fragment의 page rank를 검사하며 접촉 선의 순서가
역전되면 거부한다.

Note와 fragment 겹침은 텍스트 hit box 여백 대신 기존 Qt의 실제 paint ink
bounds로 검사한다. 실제 잉크가 겹치고 paint 순서가 교차하면 계속 거부한다.

### 네이티브 굵은 결합

단일 Bold 토큰(`bold_in`, `bold_out`)과 정확한 정수 order 1은 화학 결합
`<b Order="1" Display="Bold" BoldWidth="…">`로 내보냅니다. 시작·끝 원자,
원자 좌표와 결합 색상을 보존하고 Qt 렌더러의 실제 획 굵기에 그림 배율을
적용해 BoldWidth를 기록합니다. 굵은 획이 기본 선보다 굵지 않아(렌더러의
1e-6 허용치 포함) 일반 선으로 그려지면 그 일반 선 굵기를 사용합니다.
기존 문서 기본 BoldWidth는 바꾸지 않습니다.

기존 문서와 새 문서 모두 두 토큰을 연결축 중심의 같은 굵은 획으로 그립니다(ADR 0046).
원자를 이동하거나 분자 결합을 장식 graphic으로 대체하지 않습니다. 라벨 간격·혼합 접합부의
소비자 비교는 남아 있으며 독립 획 일치를 전체 문서 또는 GUI 동등성으로 확대하지 않습니다.
bold_center, 단일 order가 아닌 굵은 결합, generic/literal Ar의 굵은 연결은 계속 거부합니다.
이중결합의 방향·간격은 실제 화면 중심선에서 읽습니다. 저장된 native SVG 기준으로 page의
양의 법선 쪽은 Left, 반대쪽은 Right입니다. BondSpacing은 실제 B-E 거리를 기준으로 하며
화면의 1.1배 간격을 포함합니다. native 실증은 평면 육각고리와 길이 20/40/80의
독립 이중결합에 한정됩니다.
ChemDraw 25.0.2.14는 저장할 때 간격 백분율을 소수 첫째 자리까지 버립니다.
길이 80 대조군은 목표 4.84pt 대신 4.80pt로 재열리며, 170mm OMe 도면의
최대 간격 차이는 0.0087pt입니다. 좌표 직렬화 반올림도 별도로 존재합니다.
이 차이를 감추기 위해 원자를 이동하지 않습니다.

아래는 공통 renderer 변경 전의 역사적 실험 기록입니다.
ChemDraw 25.0.2.14에서 각각 원자 12개·결합 6개인 기본 굵기 및 런타임
사용자 굵기 합성 문서의 열기·저장·새 프로세스 재열기를 확인했습니다.
기본 문서는 라벨이 있는 끝 원자 하나 이동, Undo/Redo, 저장과 새 프로세스
재열기도 확인했으며 다른 원자 11개와 결합 연결·실제 굵기를 보존했습니다.
사용자 굵기의 편집은 별도로 검사하지 않았습니다. 저장된 기본 BoldWidth는
4.75817199341에서 4.76 pt, 사용자 BoldWidth는 7.14874683616에서
7.15 pt로 반올림되었습니다. 기본 native SVG 실측에서 굵기는 일치했지만
원본 띠 중심은 원자 축에서 1.29768327 pt 치우쳤고 네이티브 띠는 축에
대칭이었습니다. 정확한 윤곽 동등성은 실패했습니다. 이 검사는 소비 프로그램의
화학 경고나 화학적 해석, 전체 제품 인수 또는 배포를 승인하지 않습니다.

## 실험적 소비자 측정 기반 캡션 배치

선택 옵션 `--cdxml-layout-reference layout.json`은 지정한 소비자가 저장한
글자 경계를 사용해 선택 노트를 이동한다. 먼저 일반 내보내기를 수행하고, 해당
CDXML을 소비자에서 편집 없이 새 파일로 저장한다. 참조 v2는 원본 문서, 보정 전
CDXML, 라벨 바인딩 파일의 SHA-256과 전체 내보내기 옵션을 결합한다. v1은 거부한다.
다음 필드는 실제 파일에서 채운다. 예시 프레임 수치를 그대로 복사하지 않는다.

```json
{
  "version": 2,
  "source_sha256": "<exact .chemvas SHA-256>",
  "producer_sha256": "<uncorrected CDXML SHA-256>",
  "consumer_sha256": "<saved consumer CDXML SHA-256>",
  "consumer_file": "consumer-saved.cdxml",
  "notes": [
    0,
    1
  ],
  "export_options": {
    "format": "cdxml",
    "scope": "sheet",
    "sizing": "bond",
    "background": "white",
    "dpi": 300,
    "width_mm": 170,
    "max_height_mm": null,
    "min_font_pt": null
  },
  "label_bindings_sha256": null,
  "producer_frame": [
    0,
    0,
    481.889763779528,
    600
  ],
  "consumer_frame": [
    0,
    0,
    540,
    719.75
  ],
  "font_mapping": {
    "Arial": "Arial"
  },
  "consumer_environment": {
    "creation_program": "ChemDraw 25.0.2.14",
    "platform": "Windows",
    "executable_sha256": "<consumer executable SHA-256>"
  }
}
```

`notes`는 문서 노트 목록의 중복 없는 0부터 시작하는 인덱스다. 선택한 노트의 모든
줄은 함께 평행이동한다. `label_bindings_sha256`은 사용한 바인딩 파일 해시이며,
바인딩이 없으면 `null`이다. 두 프레임은 pt 단위 `[왼쪽, 위, 오른쪽, 아래]`로,
각각 실제 파일과 일치해야 한다. 생산자 프레임은 현재 내보내기 계획과도 비교한다.
좌표의 물리적 배율, 실제 잉크 경계, 소비자의 도면·인쇄 페이지는 별개다.
생산자 폭을 지정했다고 소비자 페이지도 같은 폭이라는 뜻은 아니다.

`font_mapping`은 사용한 모든 원본 글꼴과 예상 소비자 글꼴의 대응표다. 대체 글꼴은
명시해야 하며 원본 글꼴 보존으로 간주하지 않는다. 크기는 정확히 일치하거나,
소비자가 0.05pt 단위로 양자화했을 때만 최대 0.025pt 차이를 허용한다. 보정 CDXML의
원본 글꼴 이름과 크기는 유지한다. 생성 프로그램은 대조하지만 플랫폼·실행파일
해시 선언이 현재 실행 환경이나 설치 글꼴을 인증하지는 않는다.

ID가 사라진 원자 라벨·부착 표식까지 객체 경로로 각각 대조한다. 모든 문자열,
글꼴, 크기, 굵기·기울임, 색상, 기준점, 회전, 정렬과 분자 노드·결합 목록,
연결성, 원소·라벨 의미, 좌표 및 지정된 배율·획 크기를 보정 전 생산자와 비교한다.
CaptionJustification/LabelJustification은 상속을 적용하고 옛 Justification보다
우선합니다. 추가·삭제된 명시적 수소 수와 graphic ArrowType 변경도 거부합니다.
입증하지 못한 소비자의 수소 정규화도 자동 수용하지 않습니다.
이는 부적합한 참조를 거부하는 검사이며 모든 그래픽 확장과 시각적 일치를 증명하지
않는다.

생산자·소비자 프레임이 겹치는 영역 안에서 선택 노트의 위치만 이동한다. 기존 가로 간격을 복원하고, 모든 이동이 끝난 뒤에도
각 선택 노트의 측정 잉크에 사방 최소 1mm와 반올림 여유 0.02pt가 있어야 한다.
수치 비교 허용오차와 안전 여백은 별개다. 공간 부족·미지원 충돌은 글자나 페이지를
줄이지 않고 출력을 거부한다. 원본부터 있던 겹침과 분자·그래픽과의 간격 조정은
포함하지 않는다.

`consumer_file`은 참조 파일 기준 상대 경로나 절대 경로다. JSON은 1MiB,
소비자 XML은 64MiB까지다. 동일한 옵션과 새 출력 경로를 사용한다.

```sh
chemvas render-document input.chemvas --output corrected.cdxml \
  --width-mm 170 --cdxml-layout-reference layout.json
```

보고서에 실험 기능 여부, 해시, 프레임, 글꼴 대응·대체 및 실행 환경 미검증을 남긴다.
기본 캡션 배치는 그대로다. 색상 채널은 전체 부동소수점 정밀도로 직렬화해 소비자의
8비트 채널 절삭을 방지한다. 실제 저장·재열기 측정과 수동 GUI 편집·Undo/Redo 검증은
구분한다. [ADR 0041](adr/0041-consumer-measured-caption-layout.md)을 참고한다.

### native formal charge 보존

표시 라벨이 있는 전하 원자는 원래 라벨·별도 ± 표시의 위치를 유지하는 Fragment
안에 원자·전하 정의를 둡니다. 기존 바깥 결합마다 외부 접속점을 하나 두며, 여러
연결은 BondOrdering/ConnectionOrder로 대응합니다. 바깥 결합과 입체방향은 유지합니다.
이로써 ChemDraw가 P/O 라벨을 중성으로 다시 해석해 Charge를 버리는 문제를 막습니다.
OMe native 저장·재열기에서 P+ 4개/O− 4개가 유지됐고, MOL 비교에서도 288원자·
286결합과 쐐기/해시 표시 30개가 유지됐습니다. 원시 참조 승인·전체 외형·대화식 편집의
통과를 뜻하지 않습니다. [ADR 0043](adr/0043-native-formal-charge-definitions.md).

### native 라벨 해석과 수소 수

실제 저장·재열기로 확인한 정확한 P/O/H 원소 라벨과 Me/tBu 고정 조각 라벨은
`InterpretChemically="yes"`로 기록합니다. 기존 화학 그래프와 글자·배치는 유지합니다.
다른 표기는 기존 동작을 유지하며, 식별자가 붙은 H 및 구체적 조각으로 바인딩한
Ar를 보이는 글자만으로 다시 해석하지 않습니다. 전하·generic aryl 정의는 기존 매핑을 씁니다.

`NumHydrogens` 생략을 무조건 0으로 간주하지 않습니다. native의 속성 생략·명시화는
화학 변화와 별도로 분석합니다. consumer-reference 검증기는 실증된 무라벨 중성 C의
결합수 1/4, 정확한 P/O/H 및 P+/O- 라벨과 결합수 조합, ARY 부가 표기만 정규화합니다.
나머지 수소 수·문맥·명시값 간 변경은 거부합니다. 정의 fragment ID는 같은 atom owner,
같은 구성원·port 순서가 유지될 때만 재번호를 허용합니다. 이는 범용 원자가 엔진이나
OMe raw native reference 승인이 아닙니다. 원본 그래프에서 비롯된 원자가 경고를 숨기지 않습니다(ADR 0044).
예외 TS 원자 7개의 정규화는 모두 order-1인 실증 결합 구성·표시·방향과 전하 정의 또는
page-level H 문맥도 요구합니다(ADR 0045). 결합차수 합만 같은 이중결합 대안은 거부합니다.

연구·TS 도면의 native 원자가 경고 자체를 변환 손상으로 판단하지 않습니다. 저장된
order-1 점선 결합·전하·라벨을 유지하며 부분 결합 차수나 정상 원자가 보정을 추정하지
않습니다. [ADR 0045](adr/0045-native-reference-semantic-normalization.md).


[ADR 0047](adr/0047-native-line-width-and-reference-spacing.md)에 따라 직선은
개별 굵기를 보존하는 머리 없는 native arrow로 씁니다. 실제 arrow의 상속 적용
굵기·색·끝점·소유 관계와 검증된 SupersededBy 관계만 비교하며 임의 ID 대응은
허용하지 않습니다. 연속 저장에서 arrow ID가 바뀌므로 인접 저장본 사이의 근거가
필요합니다. 개별·상속 BondSpacing 백분율 변경도 거부합니다. native 소수점 절삭을
좌표 허용오차로 숨기지 않으며, 남은 글꼴·라벨·색·채움 도형 차이를 승인하지 않습니다.

## 네이티브 텍스트와 겹치는 요소의 순서

ADR 0048은 공통 compact 라벨 배치, 0.05 pt 크기 정밀도, 제한된 저장·재열기
근거를 기록합니다. 폰트 이름 일치는 실제 폰트 파일·대체 글리프 일치를
보장하지 않습니다. 폰트·기준선·전하·색 차이에 대한 전체 reference gate는
계속 거부 상태입니다. 직선 획이 불투명한 축 정렬 사각형 채움과 실제 면적으로
겹치면 상대 그리기 순서를 보존해야 합니다. Z 번호 재배치는 허용하지만 순서
반전과 동률은 거부합니다. 모든 겹침 유형을 검증한다는 의미는 아닙니다.

## 네이티브 저장 진단과 팔레트 복구

원본 내보내기 CDXML과 ChemDraw 25.0.2.14의 첫 SaveAs 파일을 보관합니다.
다음 명령은 글꼴·스타일 변경과 팔레트 안정성을 JSON으로 보고합니다.

```bash
chemvas review-cdxml producer.cdxml --native first-save.cdxml
```

새 출력 파일로 복구하려면:

```bash
chemvas review-cdxml producer.cdxml --native first-save.cdxml --recover-palette recovered.cdxml
```

복구 출력은 기존 파일이 없는 새 `.cdxml` 경로여야 합니다. 대응하는 객체와
텍스트의 논리 색과 측정된 writer의 정확한 소수값이 같은지 확인한 뒤 팔레트 숫자만 원래 8비트 RGB로
되돌립니다. 나머지 바이트와 원본 문서는 보존하며, 실제 재색칠·미측정 writer·
이미 손실된 파일은 거부합니다. 입력은 각각 64 MiB 이하이며 원본의 정확한
8비트 RGB가 필요합니다. 보고된 대체 안정 색은 적용하지 않습니다.

성공 종료는 진단 또는 제한된 팔레트 복구의 완료를 뜻합니다.
`full_fidelity_accepted`는 계속 `false`이며 글꼴·글리프·도형·화학의 동일성을
승인하지 않습니다. 없는 물리 글꼴은 charset이나 이름 표기로 복원되지 않으며
치환은 보고서에 남습니다. 네이티브 SaveAs마다 소수 반올림이 다시 발생하므로
원본을 보관하고 매 저장본을 다시 가져오기 전에 복구해야 합니다. 네이티브 CDX는
측정 대조군에서 색을 보존했지만 전체 문서의 동일성을 보장하지 않습니다.
[ADR 0051](adr/0051-measured-native-cdxml-palette-recovery.md)을 참고하세요.


정확한 팔레트 값도 저장 이력이나 편집 의도를 증명하지 않습니다. 의도적 편집의
결과가 같은 바이트라면 자동 구분할 수 없으므로, 사용자가 첫 저장본임을 알고
있을 때만 명시적으로 실행합니다. 이력이 불명확한 파일은 변경하지 않습니다.
`provenance_runtime_verified`는 계속 `false`입니다. XML 주석은 보존하고 실제
색 요소만 바꾸며, 실제 출력 팔레트를 다시 파싱해 확인한 후 새 파일을 만듭니다.
[ADR 0052](adr/0052-parse-and-verify-native-palette-recovery.md)를 참고하세요.

## 편집 가능한 텍스트의 서체 계약

같은 서체 이름만으로 같은 물리 face·버전·대체 글꼴을 보장하지 않습니다. 원본
서체 요청과 실제 fallback run을 유지하고, 없는 서체는 호환성 한계로 명시합니다.
공통 서체를 쓸 별도 사본은 사용자 선택 후에만 만들며 원본을 자동 변경하지 않습니다.
양쪽의 regular/bold face와 한글·위첨자·아래첨자 지원을 확인한 다음 실제 네이티브
글리프·단어 시작점·기준선·배치를 검증해야 합니다.

측정된 원본의 316개 span은 각각 배정된 Mac 서체로 모두 그려집니다. `₆` 한 번과
`−` 여섯 번은 이미 Helvetica fallback span으로 분리됩니다. 한 서체가 모든 문자를
지원해야 한다는 조건은 적용하지 않습니다. Windows에는 원본 Apple/Helvetica
구성이 없지만 실제로는 Arial과 Gulim/Microsoft Sans Serif fallback으로 그려지므로,
요청 서체 부재를 모든 글리프의 출력 불가로 표현하지 않습니다.

앞선 공통 21종은 Windows GDI 목록의 교집합입니다. WPF에는 Gill Sans가 추가로
나타나며 이 환경의 요청은 Gill Sans Ultra Bold face로 해석됩니다. 목록 API와
실제 해석된 face를 함께 확인해야 합니다. Windows에 이미 있는 Malgun Gothic/Tahoma
regular/bold run 조합은 설치 없이 원문 169문자를 지원합니다. 이는 원본 Mac의
외형·수치·전체 배치가 같다는 증거가 아닙니다. 서체 대체는 별도 파생본에 대한
명시적 선택이며 renderer의 자동 변경으로 적용하지 않습니다.
[서체 검토 설계안](FONT_COMPATIBILITY_REVIEW.ko.md)은 측정된 미리보기와 제안 설계이며,
구현된 GUI 기능이 아닙니다. Mac ChemDraw가 없는 환경의 roundtrip도 미검증입니다.


## 데스크톱에서 검토한 라벨 의미 선택

**File → Export Figure**에서 CDXML을 선택하고 현재 저장된 그림에 해당하는
검토된 binding JSON을 직접 고릅니다. 다음 대화상자에는 자동 재사용되지 않습니다.
편집했다면 먼저 저장하고 그 버전의 의미를 다시 검토해야 합니다. 미저장 변경,
이전 버전 binding, 외부 파일 변경, 불확실한 snapshot은 출력 전에 거절합니다.
원본 그림을 고치거나 Ar 의미를 추측하지 않습니다.

굵은 평탄선은 공통 굵기의 native 무화살촉 선으로 출력합니다. HTML 태그와 CSS
첨자는 native face 비트와 기존 굵게·색·글꼴을 유지합니다. 첨자가 있는 줄은 실제
glyph 위치를 유지하는 개별 편집 가능한 native text run으로 출력되며, 하나의 흐르는
문단은 아닙니다. 일반 줄의 기존 출력과 미지원 서식 거절은 유지됩니다.
[ADR 0053](adr/0053-reviewed-desktop-cdxml-and-script-geometry.md)을 참고하세요.

검토 binding을 사용하는 데스크톱 CDXML은 확인한 저장 문서의 독립 snapshot 하나로
의미 검사·preflight·출력을 수행합니다. 결합 삭제 후 저장하여 파일의 bond ID가
압축되어도, 새 저장본에 대해 검토한 v2 documentary contact를 재열기 없이 즉시
출력할 수 있습니다. 표시 여부·선택은 저장된 참조로 옮깁니다. 출력 범위에 닿는
그룹은 계속 거부하며 선택 밖의 그룹은 포함하지 않습니다. 원본 바이트, sidecar ID,
live 편집 모델과 Undo 이력을 바꾸지 않습니다.
[ADR 0054](adr/0054-saved-cdxml-export-snapshot.md)를 참고하세요.
