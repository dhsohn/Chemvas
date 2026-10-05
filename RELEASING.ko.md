# Chemvas 릴리스

[English](RELEASING.md)

Chemvas는 GitHub Actions의 Trusted Publishing (OIDC)을 통해 [PyPI](https://pypi.org/project/chemvas/)에 패키지를 배포합니다. `v*` 태그를 푸시하면 [`.github/workflows/release.yml`](.github/workflows/release.yml)이 실행되어 sdist와 wheel을 빌드하고 업로드합니다.

배포용 빌드 아티팩트(wheel 및 sdist)는 Qt 데스크톱 앱과 헤드리스 CLI만 포함합니다. 독립 실행형 번들 spec에도 같은 Qt 전용 경계를 선언합니다. 실험적 브라우저 편집기 파일은 `setup.py`와 `MANIFEST.in`을 통해 패키지에서 제외되며, `packaging/chemvas.spec`에서도 `chemvas.bootstrap.web_adapter`와 `chemvas.bootstrap.web_drafts`를 제외하여 동일한 경계를 적용합니다(Qt, 아이콘 및 라이선스 메타데이터는 보존). 묶을 화학 extra는 없습니다. GitHub 릴리스 태그 소스 아카이브는 개발용 저장소 파일을 보존하지만, 별도로 출시된 웹 제품이 아닙니다.

버전 정보는 [`app/chemvas/__init__.py`](app/chemvas/__init__.py)의 `chemvas.__version__`에서 관리됩니다. 아직 발행하지 않은 후보는 `0.25.0.dev0`일 수 있습니다. Windows 번들과 `v*` 태그는 숫자 `major.minor.patch`가 필요하며, Windows에서 `packaging/chemvas.spec`은 그 외 형식을 거부합니다. 그 번호를 정하고 changelog 절을 옮기는 것은 릴리스 준비입니다. 태그와 발행은 그다음 단계입니다.

## 릴리스 절차

1. `app/chemvas/__init__.py`의 `__version__`을 갱신합니다.
2. [`CHANGELOG.md`](CHANGELOG.md)의 Unreleased 항목을 신규 버전 섹션으로 정리합니다.
3. PR을 열어 `main`에 머지한 후, 정확한 `main` 커밋에서 CI가 통과했는지 확인합니다. 이어서
   `main`에서 **Platform tests** 워크플로(Actions → Platform tests → Run workflow)를
   실행해 macOS와 Windows 테스트가 통과하는지 확인합니다. PR CI는 이 테스트를
   돌리지 않습니다. 로컬에서 배포 아티팩트를 검증합니다:
   ```bash
   python -m build
   python scripts/verify_dist.py dist/*
   ```
   `python -m build`는 sdist를 먼저 빌드한 뒤 해당 sdist로부터 wheel을 빌드합니다. `scripts/verify_dist.py`는 아티팩트의 파일 목록과 포함된 빌드 입력을 확인하며, 자체적으로 재빌드를 실행하지는 않습니다. CI는 실제 배포 아티팩트와 설치된 환경의 CLI 동작을 검사합니다. Windows 잡은 번들 spec과 네이티브 설치 프로그램 컴파일러를 검사하며, 전체 PyInstaller 앱을 빌드하고 실행하지는 않습니다. 동결 앱 번들을 배포할 때는 해당 번들을 별도로 검증해야 합니다.
4. 정확한 `main`에서 릴리스 태그를 생성하고 푸시합니다:

```bash
git checkout main && git pull
git tag -a v0.24.0 -m "Chemvas 0.24.0"
git push origin v0.24.0
```

5. 깨끗한 가상 환경에서 배포된 패키지를 검증합니다:

```bash
python -m venv .release-check
.release-check/bin/python -m pip install "chemvas==0.24.0"
.release-check/bin/chemvas --version
.release-check/bin/chemvas
```
