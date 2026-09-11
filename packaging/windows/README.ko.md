# Windows 배포 준비

[English](README.md)

이것은 서명되지 않은 로컬 Windows 빌드 경로이며 게시된 데스크톱 릴리스가
아닙니다. 릴리스된 배포물은 여전히 Python 패키지입니다. 64비트 Windows에서
Python 3.12+로 빌드하세요. PyInstaller는 Linux나 macOS에서 Windows용을 만드는
크로스 컴파일러가 아닙니다.

## 빌드

새 Windows 체크아웃이나 소스 사본, 그리고 전용 환경을 쓰세요. WSL UNC 경로를
통해 빌드하거나 기존 애플리케이션 환경을 수정하지 마세요.
[Inno Setup 6](https://jrsoftware.org/isdl.php)를 설치하고 게시자 서명을
확인하세요. `/PORTABLE=1` 모드를 쓰면 컴파일러를 전용 디렉터리에 둘 수 있습니다.
DLL과 서명 파일을 포함해 컴파일러 디렉터리를 온전히 유지하세요.

소스 디렉터리의 PowerShell에서:

```powershell
py -3.13 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install ".[rdkit]" -r packaging\windows\requirements-build.txt
.\packaging\windows\build.ps1 -Python .\.venv-windows\Scripts\python.exe -Iscc 'C:\Tools\Inno Setup 6\ISCC.exe'
```

스크립트는 주어진 도구를 쓸 뿐 패키지를 설치하거나 PATH를 바꾸지 않습니다.
빌드마다 새 출력 디렉터리를 만들고 그 위치를 출력합니다. 애플리케이션 버전은
`chemvas.__version__`에서 오며, 로컬 설치 프로그램을 만든다고 릴리스가 생기거나
그 버전이 바뀌지는 않습니다.

출력물에는 다음이 들어 있습니다.

- `chemvas.exe`: 콘솔 창 없는 데스크톱 그리기와 문서 열기.
- `chemvas-cli.exe`: 같은 애플리케이션에 문서 명령, `--help`, `--version`의 콘솔
  출력이 붙은 것.
- 애플리케이션 폴더와 런타임 의존성을 담은 설치 `.exe`.

설치 프로그램을 쓰거나, 애플리케이션 폴더 **전체**를 함께 두세요. `chemvas.exe`만
복사하는 것으로는 부족합니다. 이 Windows 설치 프로그램 빌드는 SMILES와 3D 기능을
위해 RDKit extra가 필요합니다. RDKit 없는 그리기 전용 설치는 이 설치 프로그램
경로가 아니라 Python 패키지로 계속 가능합니다.

## 설치와 그림 열기

설치 프로그램은 관리자 권한을 요구하지 않고 현재 사용자용으로
`%LOCALAPPDATA%\Programs\Chemvas`에 설치하며 시작 메뉴 바로가기를 만듭니다.
Chemvas를 `.chemvas` 그림의 애플리케이션으로 등록합니다. 기존 기본 앱을 대체하거나
Windows의 보호된 `UserChoice`를 편집하지는 않습니다.

첫 더블클릭 때 Windows가 어떤 앱으로 열지 물을 수 있습니다. **Chemvas**와
**항상**을 고르세요. 또는 **연결 프로그램 > 다른 앱 선택**이나 Windows **설정 >
앱 > 기본 앱**을 쓰세요. 이 1회 선택은 Windows의 몫이며 설치 프로그램이 강제하지
않습니다.

설치를 다시 실행하면 사용자별 설치가 갱신됩니다. 업데이트 전에 Chemvas를 닫으세요.
제거는 Windows의 설치된 앱이나 설치된 제거 프로그램으로 합니다. 제거는 설치된
프로그램 파일과 Chemvas의 등록을 지우며, 저장한 그림이나 복구 데이터는 지우지
않습니다. 그림 파일을 예제로 바꿔치기하지도 않습니다.

애플리케이션은 지원되는 첫 문서 인자를 엽니다. 한 프로세스에서 파일을 다시 열면
기존 창이 활성화되고, 다른 실행 파일을 띄우면 별도 프로세스가 생깁니다. 프로세스
간 단일 인스턴스 라우팅은 이 첫 설치 프로그램에 포함되지 않습니다.

## 공개 릴리스 전 인수 검사

소스 변경에 대해 `make check`를 돌린 뒤, 실제 Windows 산출물을 시험합니다.

1. `chemvas-cli.exe --version`과 `--help`를 실행하고, 소스 디렉터리 밖에서 공개
   `.chemvas` 예제를 inspect하고 render합니다.
2. 데스크톱을 실행해 경로에 공백과 비ASCII 문자가 든 그림을 엽니다. 캔버스, 아이콘,
   저장, 저장본 다시 열기를 확인합니다.
3. 설치하고 Windows 파일 연결로 그림을 연 뒤 설치를 다시 실행합니다. 기존의 다른
   기본 앱이 보존되는지 확인합니다.
4. 제거합니다. Chemvas 등록과 설치된 실행 파일이 지워졌고 저장한 그림은 그대로인지
   확인합니다.
5. RDKit이 켜진 빌드라면 SMILES 삽입과 3D/내보내기도 시험합니다.

소스 검사는 Windows 설치나 시각적 인수 검사를 대신하지 못합니다. 이 단계의 실행
파일은 서명되지 않았습니다. 서명과 깨끗한 Windows 기계에서의 시험은 릴리스
작업으로 남아 있으며, 서명되지 않은 시험을 통과시키려고 Windows 보안 보호를 끄지
마세요.

Chemvas 소스의 라이선스는 여전히 MIT입니다. 번들 의존성은 각자의 조건이 있습니다.
특히 [PyQt는 GPLv3 또는 상용 라이선스](https://riverbankcomputing.com/commercial/pyqt)입니다.
바이너리를 배포하기 전에 정확한 의존성 버전, 라이선스 고지, 대응 소스 의무를
검토하고 필요한 자료를 제공하세요. 라이선스 파일을 번들에 넣는 것만으로 그 의무가
이행됐다고 주장할 수는 없습니다.
