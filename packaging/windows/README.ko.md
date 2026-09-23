# Windows 배포 준비

[English](README.md)

64비트 Windows 환경에서 PyInstaller 및 Inno Setup을 사용하여 독립 실행형 Windows 설치 프로그램을 빌드하는 방법입니다.

## 빌드 요구사항

- 64비트 Windows 환경 및 Python 3.12+
- [Inno Setup 6](https://jrsoftware.org/isdl.php)

저장소 루트의 PowerShell에서 다음 명령을 실행합니다:

```powershell
py -3.13 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install ".[rdkit]" -r packaging\windows\requirements-build.txt
.\packaging\windows\build.ps1 -Python .\.venv-windows\Scripts\python.exe -Iscc 'C:\Tools\Inno Setup 6\ISCC.exe'
```

### 빌드 결과물

- `chemvas.exe`: 콘솔 창 없는 데스크톱 GUI 애플리케이션
- `chemvas-cli.exe`: 터미널 스크립팅 및 문서 조작용 명령줄 실행 파일
- 설치 프로그램 실행 파일 (`Output/Chemvas-Setup-*.exe`)

## 설치 및 파일 연결

설치 프로그램은 관리자 권한 없이 `%LOCALAPPDATA%\Programs\Chemvas`에 설치되며, `.chemvas` 확장자에 대한 애플리케이션 연결을 등록합니다.
