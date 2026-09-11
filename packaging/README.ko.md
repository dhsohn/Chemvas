# 패키징 자산

[English](README.md)

데스크톱 번들용 플랫폼 아이콘 파일입니다. 모두 단일 마스터 SVG
[`app/chemvas/assets/icon/chemvas.svg`](../app/chemvas/assets/icon/chemvas.svg)에서
생성합니다.

| 파일 | 용도 |
| --- | --- |
| `icons/chemvas.icns` | macOS `.app` 번들 아이콘 (`CFBundleIconFile`) |
| `icons/chemvas.ico` | Windows 실행 파일 / 설치 프로그램 아이콘 |
| `icons/chemvas-1024.png` | 스토어 목록과 문서용 마스터 래스터 |

런타임 창/작업 표시줄 아이콘은 여기에 있지 **않습니다**. 그것은
`app/chemvas/assets/icon/`의 PNG 세트로, wheel 안에 담겨 배포되며
`chemvas.branding.app_icon()`이 로드합니다.

## 재생성

마스터 SVG를 편집한 뒤 전부(런타임 PNG, `.icns`, `.ico`)를 다시 렌더링합니다.

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_icons.py
```

래스터화는 Qt 자체 SVG 렌더러(앱이 툴바 글리프에 쓰는 것과 같은 렌더러)를
거칩니다. `.icns` 패킹은 macOS `iconutil`, `.ico` 패킹은 Pillow를 씁니다. 생성된
바이너리는 커밋되어 있으므로 번들을 빌드하는 데 추가 툴체인이 필요 없습니다.

## 데스크톱 번들 빌드 (PyInstaller)

[`chemvas.spec`](chemvas.spec)이 아이콘을, macOS에서는 `.chemvas` 문서 유형을
선언하는 `Info.plist`를 연결합니다.

```bash
python -m pip install -e ".[rdkit]" pyinstaller   # rdkit optional
pyinstaller packaging/chemvas.spec
```

출력은 `dist/Chemvas.app`(macOS) 또는 `dist/chemvas/`(Windows/Linux)입니다.
`.chemvas` 파일 열기는 플랫폼별로 처리됩니다. Windows/Linux는 `argv`로 경로를
넘기고(`_startup_document_path`가 읽음), macOS는 `QEvent.FileOpen`을 보내며
`chemvas.adapters.qt.FileOpenEventFilter`가 이를 부트스트랩 로더로 전달합니다.

## Windows 설치 프로그램

[Windows 빌드 안내](windows/README.ko.md)는 네이티브 x64 빌드, GUI와 콘솔 실행
파일, 사용자별 Inno Setup 설치 프로그램, `.chemvas` 연결 프로그램 등록을
설명합니다. 데스크톱 바이너리는 아직 로컬 시험 산출물이며 게시된 릴리스가
아닙니다.

## Linux 데스크톱 통합

[`linux/chemvas.desktop`](linux/chemvas.desktop)과
[`linux/chemvas.xml`](linux/chemvas.xml)(`application/x-chemvas` MIME 유형)이 앱과
파일 유형을 등록합니다. 번들을 `PATH`에 놓은 뒤:

```bash
xdg-mime install --novendor packaging/linux/chemvas.xml
xdg-icon-resource install --context mimetypes --size 256 \
  app/chemvas/assets/icon/chemvas-256.png application-x-chemvas
install -Dm644 app/chemvas/assets/icon/chemvas-256.png \
  ~/.local/share/icons/hicolor/256x256/apps/chemvas.png
desktop-file-install --dir="$HOME/.local/share/applications" packaging/linux/chemvas.desktop
update-desktop-database ~/.local/share/applications
```
