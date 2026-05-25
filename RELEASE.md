# Release Guide — nirikshaai (Python SDK)

> Product: [niriksha.ai](https://niriksha.ai) · Company: [sandatasystem.ai](https://sandatasystem.ai)  
> Maintainer: vbhadauriya@redcloudcomputing.com

---

## Versioning Scheme

This SDK follows [Semantic Versioning 2.0.0](https://semver.org):

```
v MAJOR . MINOR . PATCH
  │       │       └── Bug fixes, security patches (backwards compatible)
  │       └────────── New features (backwards compatible)
  └────────────────── Breaking API changes
```

### Version Lifecycle

| Version Pattern | Meaning | Published to |
|----------------|---------|-------------|
| `0.2.0.devN` | Auto dev build (every merge to `main`) | PyPI (pre-release) |
| `0.2.0a1` | Alpha — early feature preview | PyPI (pre-release) |
| `0.2.0b1` | Beta — feature complete, needs testing | PyPI (pre-release) |
| `0.2.0rc1` | Release candidate — final testing | PyPI (pre-release) |
| `0.2.0` | Stable release | PyPI (stable) |
| `1.0.0` | First stable API contract | PyPI (stable) |

> **Why not v0.0.0?** We start at `v0.1.0` / `v0.2.0`. `v0.0.0` is a placeholder meaning "not yet versioned". Even our pre-1.0 releases have real version numbers. `0.x.y` means the public API may still change; `1.0.0` signals a stable, committed public API.

### Install a specific version

```bash
# Stable
pip install nirikshaai==0.2.0

# Latest dev build (auto-published on every main merge)
pip install --pre nirikshaai

# Specific dev build
pip install "nirikshaai==0.2.0.dev42"

# Alpha / Beta / RC
pip install "nirikshaai==0.2.1a1"
```

---

## Branching Strategy

```
main                  ← Protected. Every merge auto-publishes a dev build.
│
├── feature/xxx       ← New features. PR → main.
├── fix/xxx           ← Bug fixes. PR → main.
├── hotfix/xxx        ← Urgent production patches. PR → main.
├── enhance/xxx       ← Improvements (docs, CI, deps). PR → main.
└── release/x.y.z     ← Release preparation. PR → main, then tag.
```

### Branch rules (configure in GitHub → Settings → Branches)

| Branch | Protection |
|--------|-----------|
| `main` | Require PR, require CI to pass, no force-push |
| `release/*` | Require PR, require CI to pass |

### Lifetime of a branch

```
Create from main → develop → open PR → CI green → merge → branch deleted
```

---

## Release Types

### 1. Patch Release (v0.2.0 → v0.2.1)
**When:** Bug fix, security patch, dependency bump. No new public API.

```bash
# 1. Branch from main
git checkout main && git pull
git checkout -b release/0.2.1

# 2. Bump version in pyproject.toml and nirikshaai/__init__.py
#    Change: version = "0.2.0"  →  version = "0.2.1"
vim pyproject.toml nirikshaai/__init__.py

# 3. Update CHANGELOG.md
#    Move entries from [Unreleased] to [0.2.1] with today's date

# 4. Commit and open PR
git add pyproject.toml nirikshaai/__init__.py CHANGELOG.md
git commit -m "chore: release 0.2.1"
git push -u origin release/0.2.1
gh pr create --base main --title "chore: release 0.2.1"

# 5. After PR is merged to main, tag it
git checkout main && git pull
git tag -a v0.2.1 -m "Release v0.2.1"
git push origin v0.2.1
# → GitHub Actions release.yml publishes to PyPI automatically
```

### 2. Minor Release (v0.2.0 → v0.3.0)
**When:** New backwards-compatible features or deprecations.

Same steps as patch, but bump the minor version:
```bash
git checkout -b release/0.3.0
# version = "0.2.0" → "0.3.0"
```

### 3. Major Release (v0.x.y → v1.0.0)
**When:** Breaking public API changes (removing/renaming exported symbols).

```bash
git checkout -b release/1.0.0
# version = "0.2.0" → "1.0.0"
# Also update: README install instructions, CHANGELOG, migration guide
```

> Before a major release, publish at least one RC (release candidate):
> `1.0.0rc1` → test with real users → `1.0.0`

### 4. Pre-release (alpha / beta / RC)
**When:** Sharing early features with select users before a stable release.

```bash
# Alpha — early preview, API may change
git tag -a v0.3.0a1 -m "Alpha 1 for v0.3.0"
git push origin v0.3.0a1

# Beta — feature complete, API stable, needs broader testing
git tag -a v0.3.0b1 -m "Beta 1 for v0.3.0"
git push origin v0.3.0b1

# Release Candidate — final testing before stable
git tag -a v0.3.0rc1 -m "RC 1 for v0.3.0"
git push origin v0.3.0rc1
```

All pre-release tags trigger `release.yml`, which publishes to PyPI as a pre-release.  
Users install with `pip install --pre nirikshaai`.

### 5. Dev Build (automatic)
**When:** Every merge to `main` — no manual action required.

The `dev-release.yml` workflow automatically:
1. Computes version `0.2.0.dev{RUN_NUMBER}` (PEP 440 compliant)
2. Builds wheel + sdist
3. Publishes to PyPI as a pre-release
4. Creates a GitHub pre-release entry

Users install with `pip install --pre nirikshaai`.

---

## Required Secrets & Setup (One-time)

### PyPI Trusted Publisher (recommended — no token needed)
1. Go to [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
2. Add a new trusted publisher:
   - **Owner:** `san-data-systems`
   - **Repository:** `niriksha-sdk-python`
   - **Workflow filename:** `release.yml`
   - **Environment:** `pypi`
3. Add a second publisher for dev builds:
   - Same repo, workflow `dev-release.yml`, environment `pypi-dev`
4. Create the `pypi` and `pypi-dev` environments in GitHub → Settings → Environments

### Alternative: PyPI API Token
If trusted publisher is not used:
1. Go to [pypi.org/manage/account/token](https://pypi.org/manage/account/token/)
2. Create a token scoped to `nirikshaai`
3. Add to GitHub → Settings → Secrets → `PYPI_TOKEN`
4. Update workflow: replace `pypa/gh-action-pypi-publish` with token-based publish

### NVD API Key (speeds up OWASP scans)
1. Register at [nvd.nist.gov/developers/request-an-api-key](https://nvd.nist.gov/developers/request-an-api-key)
2. Add as GitHub secret: `NVD_API_KEY`

---

## Release Checklist

Before tagging any stable release:

- [ ] All CI checks green on `main`
- [ ] `pytest tests/ --cov=nirikshaai` passes with ≥70% coverage
- [ ] `ruff check nirikshaai/` clean
- [ ] `mypy nirikshaai/` clean
- [ ] CHANGELOG.md updated — `[Unreleased]` entries moved to `[x.y.z]` with date
- [ ] Version bumped in `pyproject.toml` AND `nirikshaai/__init__.py`
- [ ] PR merged to `main`
- [ ] Tag pushed: `git tag -a vX.Y.Z -m "Release vX.Y.Z" && git push origin vX.Y.Z`
- [ ] GitHub Release created (auto by workflow)
- [ ] PyPI page updated (auto by workflow)

---

## Hotfix Process

For urgent production bugs:

```bash
# Branch from main (which always reflects the latest release)
git checkout main && git pull
git checkout -b hotfix/fix-critical-bug

# Make the fix + add test
# Bump patch version (e.g. 0.2.0 → 0.2.1)
# Update CHANGELOG.md

git commit -m "fix: critical bug description"
git push -u origin hotfix/fix-critical-bug

# PR → main, get review, merge
# Then tag immediately
git checkout main && git pull
git tag -a v0.2.1 -m "Hotfix: critical bug description"
git push origin v0.2.1
```

---

## CHANGELOG Management

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

```markdown
## [Unreleased]          ← new changes go here first
## [0.2.1] - 2025-06-01 ← moved here when releasing
## [0.2.0] - 2025-05-01
```

**Section types:** `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`

Every PR must include a CHANGELOG entry under `[Unreleased]`.
