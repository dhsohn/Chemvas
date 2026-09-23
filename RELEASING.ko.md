# Chemvas 릴리스

[English](RELEASING.md)

Chemvas는 GitHub Actions의 Trusted Publishing (OIDC)을 통해 [PyPI](https://pypi.org/project/chemvas/)에 패키지를 배포합니다. `v*` 태그를 푸시하면 [`.github/workflows/release.yml`](.github/workflows/release.yml)이 실행되어 sdist와 wheel을 빌드하고 업로드합니다.

버전 정보는 [`app/chemvas/__init__.py`](app/chemvas/__init__.py)의 `chemvas.__version__`에서 관리됩니다.

## 릴리스 절차

1. `app/chemvas/__init__.py`의 `__version__`을 갱신합니다.
2. [`CHANGELOG.md`](CHANGELOG.md)의 Unreleased 항목을 신규 버전 섹션으로 정리합니다.
3. PR을 열어 `main`에 머지한 후, `main` 브랜치의 CI가 통과했는지 확인합니다.
4. 릴리스 태그를 생성하고 푸시합니다:

```bash
git checkout main && git pull
git tag -a v0.1.0 -m "Chemvas 0.1.0"
git push origin v0.1.0
```

5. 깨끗한 가상 환경에서 배포된 패키지를 검증합니다:

```bash
python -m venv .release-check
.release-check/bin/python -m pip install "chemvas==0.1.0"
.release-check/bin/chemvas --version
.release-check/bin/chemvas
```
