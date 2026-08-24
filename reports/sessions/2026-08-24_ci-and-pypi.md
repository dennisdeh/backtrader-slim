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

## A second defect, caught before the first push

As first committed, `ci.yml` triggered on `push: branches: [master]` and on
`pull_request`. This repository does neither: CLAUDE.md has feature work happen
on a branch in the main checkout, and says there is no PR workflow. A branch
push would therefore have triggered nothing, and the first run would have come
from the push of the merge — after the merge the gate exists to gate.
`workflow_dispatch` is no escape either, because GitHub only offers it once the
workflow is on the default branch, which is the same problem one step later.

`branches: ["**"]` puts the run where the decision is. `pull_request` stays for
contributions arriving from a fork, which never push a branch here, so the two
triggers do not overlap in practice.

It was found by asking what pushing the branch would actually cause, rather
than by pushing and seeing. Worth doing in that order: the answer was "nothing",
and nothing is indistinguishable from a queue that has not started yet.

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

CI needed nothing beyond the merge, which happened on 2026-08-24. The PyPI
publisher was configured before the first tag — unverifiable from outside the
account at the time, and proven after the fact by the attestations on 2.2.0.

1. **Revoke the account-scoped API token** that uploaded 2.0.0–2.1.0. Nothing
   depends on it now: 2.2.0 went out through OIDC, and the attestations name
   the workflow that did it. It was pasted into a chat transcript once, which
   was always the second reason. This closes the first item that
   `reports/sessions/2026-08-23_pypi-packaging.md` left open, and it is the
   only credential left in the picture.
2. ~~Optional: require `CI passed` on `master`.~~ **Done 2026-08-24, with
   bypass prevention on**, so the gate binds the maintainer too: a fresh commit
   pushed straight to `master` is rejected, and the way through is a green
   branch plus `git merge --ff-only`, which preserves the SHA and carries its
   checks. CLAUDE.md's *Git workflow* section and the README's release runbook
   were rewritten to match — the runbook's old `git push origin master v2.2.0`
   would now fail. Still optional: a required reviewer on the `pypi`
   environment, which would turn an upload into an approval click.
3. **Optional: the TestPyPI rehearsal.** Add a *pending* publisher at
   <https://test.pypi.org/manage/account/publishing/> with project name
   `slim-backtrader` and environment `testpypi`, then run the Release workflow
   manually with the TestPyPI box ticked. Never set up: 2.2.0 proved the
   release path in production instead. Worth having anyway before a release
   that matters, and it still closes the packaging session's `~/.pypirc` item,
   because the rehearsal no longer runs from a workstation.

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

The `verify` and `publish` jobs of `release.yml` could not be run locally —
they need the runner's OIDC identity and, for `publish`, a configured publisher
on PyPI. Only their shell was executed here. Everything below the line in
*Released as 2.2.0* is what proved the rest, later the same day.

## The first runs

| run | trigger | result | wall clock |
|---|---|---|---|
| #1 | push of `ci-and-pypi-publishing` | SUCCESS, 8/8 jobs | 3 min 33 s |
| #2 | `master`, after the fast-forward merge | SUCCESS, 8/8 jobs | 4 min 45 s |

macOS and Windows passed on their first execution anywhere, which settles the
`Operating System :: OS Independent` question the matrix section opens: the
claim holds, and it is now checked on every push rather than assumed. The
`coverage` job cleared the 70% floor, and the artefact job reproduced on a
clean runner what had only been shown locally — the sdist installs and runs the
suite it ships with no optional package present, and the wheel installs pulling
in nothing.

Per-job durations, and what they say about where the time goes, are in
`reports/TESTING_SUITE.md`.

`master` was fast-forwarded to `41d12f7` and pushed on 2026-08-24. Two more
commits followed the same day — the measured CI durations, and `Release 2.2.0`
— each gated by a green run of its own.

## Released as 2.2.0

Published to PyPI on 2026-08-24: https://pypi.org/project/slim-backtrader/2.2.0/

**The first release this project has not uploaded by hand.** `git push origin
v2.2.0` was the whole of it; nothing was built or uploaded from a workstation.
Release run #1 ran `build` -> `verify` on 3.13 and 3.14 -> `publish to PyPI` ->
`github-release`, with `publish to TestPyPI` correctly skipped, and the tag
guard confirmed `v2.2.0` against the built wheel before any of it.

The number was argued before the tag and settled deliberately. `git diff
667333c HEAD -- backtrader/` is **empty**: the installed engine is byte-identical
to 2.1.0. What 2.2.0 ships is the rewritten README — which is the PyPI project
page, and which no longer tells readers the project has no CI — plus one
`importorskip` in `tests/test_metaclass.py` inside the sdist. The README's own
scheme reads Z as "bug fixes and documentation", which is 2.1.1; 2.2.0 was
chosen as a project-level milestone, CI and automated releases being a
substantial change to how the project works.

Verified against the live index rather than the local build:

| check | result |
|---|---|
| `pip install slim-backtrader==2.2.0` into an empty venv | installs exactly one package |
| `import backtrader` from outside any source tree | `2.2.0 (2, 2, 0)`, `SMA` and `Cerebro` resolve |
| `btrun --help` | entry point registered |
| served `requires_dist` | every entry gated behind an `extra` — no runtime dependencies |
| served metadata | `Requires-Python >=3.13`, `GPL-3.0-or-later` |
| GitHub release `v2.2.0` | published, both artefacts attached at the same byte sizes PyPI serves, notes are the fenced changelog section |

**The attestations are the part worth keeping.** `GET
/integrity/slim-backtrader/2.2.0/<file>/provenance` returns 200 for both files
and names the publisher:

    {'kind': 'GitHub', 'repository': 'dennisdeh/backtrader-slim',
     'workflow': 'release.yml', 'environment': 'pypi'}

The same endpoint returns **404** for 2.1.0. That is the external, after-the-fact
proof that this upload came from the workflow through OIDC and not from a token
— the thing that could not be checked beforehand, because PyPI exposes publisher
configuration only inside the account that owns it.

## Also corrected

CLAUDE.md carried **259 tests, ~47 s, 73%/69% coverage**, which had been stale
since `test_chaos.py`, `test_concurrency.py`, `test_position.py` and
`test_trade.py` landed on 2026-08-23. It now says 434 / ~50 s / 72%, matching
`reports/TESTING_SUITE.md`, which was already right. The README said 259 too.
