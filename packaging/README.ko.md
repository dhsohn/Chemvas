# 패키징 자산

[English](README.md)

[`app/chemvas/assets/icon/chemvas.svg`](../app/chemvas/assets/icon/chemvas.svg)에서 생성된 플랫폼별 아이콘 및 번들 설정입니다.

| 파일 | 대상 |
| --- | --- |
| `icons/chemvas.icns` | macOS `.app` 번들 아이콘 |
| `icons/chemvas.ico` | Windows 실행 파일 및 설치 프로그램 아이콘 |
| `icons/chemvas-1024.png` | 마스터 고해상도 래스터 이미지 |

## 아이콘 재생성

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_icons.py
```

## 데스크톱 번들 빌드 (PyInstaller)

[`chemvas.spec`](chemvas.spec)을 사용하여 독립 실행형 데스크톱 번들을 빌드합니다:

```bash
python -m pip install -e ".[rdkit]" pyinstaller   # rdkit optional
pyinstaller packaging/chemvas.spec
```

출력 파일은 `dist/Chemvas.app`(macOS) 또는 `dist/chemvas/`(Windows/Linux)에 생성됩니다.

## Windows 설치 프로그램

독립 실행형 Inno Setup 설치 프로그램 빌드 방법은 [Windows 빌드 안내](windows/README.ko.md)를 참고하세요.

## Linux 데스크톱 통합

데스크톱 아이콘 및 `.chemvas` MIME 연결 등록:

```bash
xdg-mime install --novendor packaging/linux/chemvas.xml
xdg-icon-resource install --context mimetypes --size 256 \
  app/chemvas/assets/icon/chemvas-256.png application-x-chemvas
install -Dm644 app/chemvas/assets/icon/chemvas-256.png \
  ~/.local/share/icons/hicolor/256x256/apps/chemvas.png
desktop-file-install --dir="$HOME/.local/share/applications" packaging/linux/chemvas.desktop
update-desktop-database ~/.local/share/applications
```
