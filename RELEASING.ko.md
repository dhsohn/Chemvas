# Chemvas 릴리스

[English](RELEASING.md)

Chemvas는 GitHub Actions에서 **Trusted Publishing**(OIDC)으로
[PyPI](https://pypi.org/project/chemvas/)에 게시합니다. API 토큰은 저장하지
않습니다. `v*` 태그를 push하면
[`.github/workflows/release.yml`](.github/workflows/release.yml)이 실행되어
sdist와 wheel을 빌드하고 업로드합니다.

버전의 단일 원본은 `chemvas.__version__`
([`app/chemvas/__init__.py`](app/chemvas/__init__.py))이며, `pyproject.toml`은
`dynamic = ["version"]`으로 이를 읽습니다.

## 1회 설정 (PyPI Trusted Publisher)

첫 릴리스 전에, `chemvas` 프로젝트가 아직 PyPI에 없는 상태에서 한 번만 합니다.

1. PyPI에 로그인 → **Your account ▸ Publishing ▸ Add a pending publisher**.
2. 다음을 입력합니다.
   - **PyPI Project Name:** `chemvas`
   - **Owner:** `dhsohn`
   - **Repository name:** `Chemvas`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. (권장) GitHub 저장소에 `pypi`라는 **Environment**를 만들고(Settings ▸
   Environments) 보호 규칙을 추가합니다. 예: 리뷰어 필수, `main` 브랜치와 `v*`
   태그로 제한.

`release.yml`의 `environment: pypi`와 `permissions: id-token: write`는 위의
pending publisher와 일치해야 합니다.

## 릴리스 컷

1. `app/chemvas/__init__.py`의 `__version__`을 올립니다(예: `0.1.0`).
2. [`CHANGELOG.md`](CHANGELOG.md)에서 `## [Unreleased]` 제목을
   `## [0.1.0] - YYYY-MM-DD`로 바꾸고, 그 위에 빈 `## [Unreleased]`를 새로 만들고,
   하단의 링크 참조를 갱신합니다.
3. 이 변경으로 PR을 열고 CI가 초록이면 머지합니다. 태그를 달기 전에 `main`으로의
   push가 촉발한 CI 실행이 바로 그 머지 커밋에서 통과할 때까지 기다립니다. 릴리스
   provenance 검사는 성공한 `main` push CI를 요구하며, PR의 CI 결과만으로는
   충족되지 않습니다.
4. `main`의 머지 커밋에 태그를 달고 push합니다.
   ```bash
   git checkout main && git pull
   git tag -a v0.1.0 -m "Chemvas 0.1.0"
   git push origin v0.1.0
   ```
5. **Release** 워크플로를 지켜봅니다. 성공하면 확인합니다.
   ```bash
   pip install chemvas
   chemvas
   ```

## 참고

- 태그 버전(`v0.1.0`)은 `__version__`(`0.1.0`)과 같아야 합니다. PyPI는 기존 버전의
  재업로드를 거부하므로 릴리스마다 `__version__`을 올립니다.
- 데스크톱 바이너리(PyInstaller를 통한 `.app`/`.exe`/AppImage,
  [`packaging/`](packaging/) 참조)는 아직 여기서 게시하지 않습니다. GitHub
  Release에 첨부하는 것은 계획된 후속 작업입니다.
- [Windows 준비 안내](packaging/windows/README.ko.md)는 로컬 x64 설치 프로그램
  빌드와 인수 점검 목록을 제공합니다. 로컬 빌드는 서명되지 않았으며, 설치
  프로그램을 게시하기 전에 서명, 깨끗한 기계에서의 인수 검사, 번들 의존성 배포
  검토가 선행되어야 합니다.
