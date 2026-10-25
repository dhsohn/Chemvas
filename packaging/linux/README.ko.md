# Linux 사용자 설치

[English](README.md)

압축을 풀고 해당 디렉터리에서 실행합니다.

```bash
bash install.sh
~/.local/bin/chemvas --version
```

설치에 sudo나 Python은 필요하지 않습니다. Ubuntu에는 등록 데이터베이스 갱신용
`shared-mime-info`, `desktop-file-utils`가 필요합니다. 목표 데스크톱은 Ubuntu
24.04 x86_64 GNOME이며 Wayland와 X11을 따로 검증합니다. WSL CLI 검사는
해당 데스크톱 검증을 대신하지 않습니다.

프로그램은 `$XDG_DATA_HOME/chemvas`(기본 `~/.local/share/chemvas`)에 설치하고
`~/.local/bin/chemvas` 링크와 사용자 앱 메뉴·MIME·아이콘을 등록합니다.
앱 메뉴에는 절대 실행 경로를 사용합니다. 터미널에서 `chemvas`를 입력하려면
필요에 따라 `~/.local/bin`을 PATH에 추가하세요. 기존 CDXML 기본 앱은 바꾸지 않습니다.
경로의 공백과 한글을 지원하며 HOME/XDG_DATA_HOME의 제어 문자와 `=`/`%`는 거부합니다.

프로그램 디렉터리는 설치 파일 전용입니다. 문서는 다른 곳에 저장하세요.
제거할 때는 설치 당시와 같은 XDG_DATA_HOME을 사용합니다.

```bash
bash "${XDG_DATA_HOME:-$HOME/.local/share}/chemvas/uninstall.sh" --uninstall
```

프로그램 디렉터리 밖의 문서와 Qt 설정은 보존합니다. 설치 후 다른 내용으로 교체된
앱 메뉴·MIME·아이콘·실행 링크도 보존합니다. 기존 경로는 덮어쓰지 않으므로 업데이트는
Chemvas를 닫고 기존 버전을 제거한 뒤 새 패키지를 설치합니다. 중간에 실패한 설치도
같은 제거 명령으로 정리하고 재시도할 수 있습니다. 강제 종료로
`$XDG_DATA_HOME/.chemvas-install.lock`이 남았다면 실행 중인 설치기가 없음을 확인한 뒤
빈 잠금 디렉터리만 제거하세요. 설치와 제거를 동시에 실행하지 마세요.

## 빌드

Linux x86_64에서 Conda가 아닌 독립 CPython 3.13을 사용합니다.

```bash
python3 -m venv .venv-package
.venv-package/bin/python -m pip install . PyInstaller==6.22.2
PYTHON_BIN="$PWD/.venv-package/bin/python" bash packaging/linux/build.sh dist/linux-candidate
```

출력 디렉터리는 새 경로여야 합니다. 번들, 설치용 디렉터리, tar.gz가 생성됩니다.
빌드는 PyQt6·Qt·sip·Pillow wheel이 제공하는 라이선스 파일 포함 여부를 검사합니다.
파일 포함은 재배포 조건 검토를 대신하지 않습니다. 공개 배포 전 릴리스 수락표를 완료하세요.

설치 영수증 기록 전에 중단되어 빈 프로그램 디렉터리만 남으면 제거는 거부됩니다.
그 빈 디렉터리를 `rmdir`로 제거한 뒤 재시도하세요.
