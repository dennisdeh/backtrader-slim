# Putting the suite on CI, and the release on a tag

Two workflows landed, and nothing else in the engine changed. Until now the
local `pytest` run was the only gate anywhere — `.travis.yml` went in 2.0.0 and
nothing replaced it — and publishing was a maintainer typing `twine upload`
with an account-scoped API token.

## What CI runs

`.github/workflows/ci.yml`, on every push to any branch, every pull request,
and on demand. Four jobs and an aggregate:

| job | what it establishes |
|---|---|
| `black` | the tree is formatted |
| `pytest` | 3.13 and 3.14 on Linux, 3.13 on macOS and Windows |
| `coverage` | `--cov-fail-under=70` |
| `build and verify artefacts` | the sdist and wheel are correct and self-verifying |
| `CI passed` | one status to require in branch protection |

Black is pinned to `26.5.1` rather than the `>=24.3` floor in
`pyproject.toml`: its stable style changes between releases, and a floating
version turns somebody else's release into a red build here.

## The matrix, and why the non-Linux rows are gates

`pyproject.toml` claims `Operating System :: OS Independent`. That claim had
never been executed anywhere. Rather than assume it, the hazards were checked
on 2026-08-24 before making the rows blocking:

| hazard | finding |
|---|---|
| POSIX-only imports (`fcntl`, `pwd`, `termios`, …) | none in `backtrader/` or `tests/` |
| `sys.platform` branches | two: the plotting backend, wrapped in `except Exception`, and a win32 branch in `utils/flushfile.py` |
| locale-default `open()` on Windows | `feed.py` and `writer.py` open without `encoding=`, but `datas/` is pure ASCII, so cp1252 decodes it identically |
| `spawn` vs `fork` for the optimization pools | `pytest -p spawnplug tests/test_concurrency.py tests/test_strategy_optimized.py` with `multiprocessing.set_start_method("spawn", force=True)`: **22 passed in 21.05 s**. `spawn` inherits `sys.path`, so the module-level strategy classes unpickle in the child. |

The Linux 3.13 row installs `[dev,calendars]`. Without
`pandas_market_calendars` the trading-calendar test skips itself silently;
`pandas_market_calendars` 5.4.0 installs cleanly and turns
`tests/test_resampling_intraday.py` from 17 passed + 1 skipped into 18 passed.

## The artefact job, and the defect it found

The suite passing in a clone says nothing about what gets uploaded — 2.0.0
shipped an sdist whose 88 test modules all failed at collection, and the suite
was green the whole time. So the job installs the **sdist** into a venv holding
pytest, pyflakes and the engine, and runs the suite the sdist itself ships.

That found a real defect, red before the fix:

```
FAILED tests/test_metaclass.py::TestNothingOptionalIsImportedEagerly::
       test_numpy_arrives_only_when_hurst_is_built
       - subprocess.CalledProcessError: ... returned non-zero exit status 1
1 failed, 426 passed, 8 skipped in 48.65s
```

`test_numpy_arrives_only_when_hurst_is_built` asserts that numpy *arrives* in
`sys.modules` once `HurstExponent` is built, so it needs numpy installed — and
it had no `pytest.importorskip`, unlike every one of its neighbours guarding an
optional package. In the documented dev environment numpy is always present,
pulled in by matplotlib and pandas, so the gap could not surface locally. It
surfaces for anyone verifying the artefact, which is the audience the sdist
ships a suite for.

Fixed with one `pytest.importorskip("numpy")`. The same venv afterwards:
**426 passed, 9 skipped in 50.31 s**, the ninth skip being that test.

## Publishing

`.github/workflows/release.yml`. `git push origin v2.2.0` builds from a
pristine checkout, refuses to continue if the tag and `__version__` disagree,
runs `twine check --strict`, verifies the artefacts on 3.13 and 3.14, uploads
to PyPI, and then creates the GitHub release with the artefacts attached and
that version's `changelog.txt` section as the notes.

The `verify` job deliberately does not check the repository out. It installs
what would be uploaded and runs the suite that artefact carries — testing the
checkout instead would re-test what CI already tested and would have missed the
2.0.0 defect entirely.

**No API token is involved.** PyPI is configured to trust this workflow file,
in this repository, running in the `pypi` environment, and mints a credential
good for one upload. The reasoning, and what was rejected, is in
`reports/DECISIONS.md`.

## What the maintainer still has to do

CI works the moment this branch reaches `master`. Publishing does not: PyPI has
to be told to trust the workflow first.

1. **Add the publisher** at
   <https://pypi.org/manage/project/slim-backtrader/settings/publishing/>:
   owner `dennisdeh`, repository `backtrader-slim`, workflow `release.yml`,
   environment `pypi`. Until this exists, a tag push builds and verifies and
   then fails at the upload step — it cannot publish the wrong thing, it simply
   will not publish.
2. **Revoke the account-scoped API token** that uploaded 2.0.0–2.1.0. It was
   pasted into a chat transcript, and trusted publishing makes it unnecessary.
   This closes the first item that
   `reports/sessions/2026-08-23_pypi-packaging.md` left open.
3. **Optional: require `CI passed`** on `master` in branch protection, and add
   a required reviewer to the `pypi` environment if the upload should need an
   approval click.
4. **Optional: the TestPyPI rehearsal.** Add a *pending* publisher at
   <https://test.pypi.org/manage/account/publishing/> with project name
   `slim-backtrader` and environment `testpypi`, then run the Release workflow
   manually with the TestPyPI box ticked. That closes the second open item from
   the packaging session — `~/.pypirc` having no `[testpypi]` section stops
   mattering, because the rehearsal no longer runs from a workstation.

## Verification (2026-08-24)

Everything below was executed; nothing is inferred from reading the YAML.

| check | result |
|---|---|
| `actionlint` (1.7.12) + `shellcheck` on both workflows | 0 errors |
| `pytest` on Python 3.13.15 | 434 passed, 1 skipped, 49.98 s |
| `pytest` on Python 3.14.7 | 434 passed, 1 skipped, 52.70 s |
| `pytest --cov` | 72% (statements and branches), 237 s |
| `black --check .` | 247 files unchanged |
| `python -m build` in a clean clone | wheel + sdist |
| `twine check --strict dist/*` | PASSED, both |
| sdist contains `conftest.py`, `testcommon.py`, `datas/`, `LICENSE` | present |
| `.pyc` / `__pycache__` in either artefact | none |
| the sdist's suite, in a venv with no optional packages | 426 passed, 9 skipped, 50.31 s |
| the wheel in an empty venv | one package installed, `2.1.0 (2, 1, 0)`, `btrun --help` works |
| the tag-vs-version guard | matches `v2.1.0`, rejects `v9.9.9` |
| the changelog-to-release-notes step | ran the real `run:` block out of the YAML, for a version that exists and one that does not |

The `verify` and `publish` jobs of `release.yml` cannot be run locally — they
need the runner's OIDC identity and, for `publish`, a configured publisher on
PyPI. Their shell was executed here; their GitHub-side behaviour has not been.
The first real tag is where that gets proven, which is an argument for
rehearsing on TestPyPI once.

## Also corrected

CLAUDE.md carried **259 tests, ~47 s, 73%/69% coverage**, which had been stale
since `test_chaos.py`, `test_concurrency.py`, `test_position.py` and
`test_trade.py` landed on 2026-08-23. It now says 434 / ~50 s / 72%, matching
`reports/TESTING_SUITE.md`, which was already right. The README said 259 too.
