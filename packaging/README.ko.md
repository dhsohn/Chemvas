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
python -m pip install -e . pyinstaller
pyinstaller packaging/chemvas.spec
```

출력 파일은 `dist/Chemvas.app`(macOS) 또는 `dist/chemvas/`(Windows/Linux)에 생성됩니다.

## Windows 설치 프로그램

독립 실행형 Inno Setup 설치 프로그램 빌드 방법은 [Windows 빌드 안내](windows/README.ko.md)를 참고하세요.

## Linux 사용자 패키지

[Linux 설치·빌드 안내](linux/README.ko.md)를 참고하세요. tar.gz에는 사용자 설치·제거
스크립트, 실행 링크, 앱 메뉴, 아이콘, CDXML MIME 등록이 포함됩니다.
기존 기본 앱과 사용자 문서는 보존합니다.

모든 데스크톱 번들에 PyQt6·Qt·sip·Pillow 배포 메타데이터와 라이선스 원문을 포함합니다.
재배포 조건 검토는 별도로 필요합니다. Linux/Windows에서는 `_internal/*.dist-info`,
Mac 앱에서는 대응하는 `Contents/Resources` 경로에 포함됩니다.
