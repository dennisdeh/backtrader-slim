# Preparing the first PyPI upload

Branch `packaging-pypi`. The goal was to get `2.0.0` into a state where a
single `twine upload` publishes a correct distribution — the PyPI project does
not exist yet, so this is the release that creates it.

## The blocker: the name `backtrader` is not available

`GET https://pypi.org/pypi/backtrader/json` returns **200** (2026-08-23):
upstream owns it. A PyPI name is never reusable, not even after a project is
deleted, so the fork needed its own distribution name.

**Chosen: `slim-backtrader`** — matches the README's title, and
`https://pypi.org/pypi/slim-backtrader/json` returned **404** on 2026-08-23.
`backtrader-slim` was also free and was the runner-up.

The **import** package is deliberately unchanged. `import backtrader as bt`
still works, so no strategy code moves. The cost of that choice, recorded here
so it is not rediscovered as a bug report: **this fork and upstream backtrader
cannot coexist in one environment** — both install a top-level `backtrader`.
Renaming the import package would fix it and was rejected as far too large an
API break for a packaging change.

## Applying the name across the tree

`slim-backtrader` is the project name everywhere the *project* is named, not
just in `pyproject.toml`: the README and CLAUDE.md headings, and the conda
development environment in `environment.yml` (`backtrader` ->
`slim-backtrader`), which the README, CLAUDE.md and `TESTING_SUITE.md` all
activate by name. A pre-existing local env keeps its old name until
`conda rename -n backtrader slim-backtrader` is run.

Left as `backtrader` on purpose, because they name something other than the
project: the import package and every `import backtrader` in the tree, the
`backtrader/` source directory, the repository and its GitHub URLs, and every
reference to *upstream* backtrader.

## The defect the verification found

The sdist shipped `tests/` **without `tests/conftest.py`**, so every test in it
failed at collection with `ModuleNotFoundError: No module named 'conftest'` —
88 collection errors, 0 tests run.

Cause: with no `MANIFEST.in`, setuptools falls back to a legacy heuristic that
matches `test*.py` and nothing else. `conftest.py` does not match that glob,
and neither does the `datas/` tree the fixtures read. The suite passed in a
clone and was broken in the artefact, which is exactly the failure a
`python -m build` alone never shows.

Fix: `MANIFEST.in` grafts `tests` and `datas` explicitly, and prunes the
upstream material being removed (`contrib`, `samples`, `tools`) plus `reports`
and local tooling directories.

The alternative was to prune `tests` from the sdist entirely. Shipping a
runnable suite won because it lets a downstream packager verify the artefact
without a clone, and it costs 650 KB.

## Verification (2026-08-23, Python 3.13.15)

| check | result |
|---|---|
| `pytest` in the repository | 254 passed, 1 skipped, 45.65 s |
| `pytest` inside the **extracted sdist** | 254 passed, 1 skipped, 46.44 s |
| `twine check dist/*` | PASSED for wheel and sdist |
| wheel in a fresh `venv` | installs `pip` + `slim-backtrader` only — no runtime deps |
| `import backtrader` from that venv | `2.0.0 (2, 0, 0)`, `bt.indicators.SMA` resolves |
| `btrun --help` from that venv | prints usage; entry point registered |

Artefact sizes: wheel 328 KB, sdist 896 KB. No `__pycache__` or `.pyc` in
either.

## Published

`slim-backtrader` **2.0.0** was uploaded to PyPI on **2026-08-23**, from the
artefacts built at commit `4bb2e51`. That upload is what created the project;
there was no pre-registration step. No TestPyPI rehearsal was possible - the
token was scoped to pypi.org, and TestPyPI is a separate account.

Verified afterwards against the live index: `pip install slim-backtrader` into
a fresh venv installs `pip` and `slim-backtrader` and nothing else,
`import backtrader` gives `2.0.0 / (2, 0, 0)`, and `btrun --help` works. The
served metadata reports the SPDX license `GPL-3.0-or-later`,
`Requires-Python >=3.13` and **no** non-extra dependencies.

https://pypi.org/project/slim-backtrader/2.0.0/

## 2.0.1: the licensing correction

Auditing the GPL attribution, on 2026-08-23, found that three shipped files had
lost their entire GPLv3 header block - upstream's copyright line included -
when commit `3359215` rewrote the import lists at the top of them. **2.0.0 went
to PyPI in that state**, verified by downloading the published wheel. GPL-3.0
section 4 requires those notices to survive every copy conveyed.

Fixed, together with two gaps found in the same pass: no file carried the
modification notice that section 5(a) requires of a modified work, and the nine
fork-authored test modules had no licence header at all.
`backtrader/plot/multicursor.py` is matplotlib-licensed rather than GPL, and
its licence asks a derivative to summarise its changes, so it now does.

`tests/test_licensing.py` is the check that defect earned, and it was
demonstrated red against the pre-fix tree before the fix was kept. The suite is
254 -> 259 tests. `reports/OPEN_ITEMS.md` carries the defect record.

**2.0.1 was published on 2026-08-23** (commit `3a35267`), because a published
version's files and metadata are immutable - the corrections could not reach
the public any other way. Verified against the live index afterwards:
`pip install slim-backtrader` resolves 2.0.1, the previously-stripped file
ships with its notices restored, LICENSE installs into the dist-info, and the
project page renders the *License and attribution* section crediting Daniel
Rodriguez.

https://pypi.org/project/slim-backtrader/2.0.1/

## What is left

*Two of these were overtaken on 2026-08-24 by `2026-08-24_ci-and-pypi.md`,
which put releases on GitHub Actions. The upload token no longer wants
replacing with a project-scoped one — trusted publishing needs no token at
all, so it wants revoking outright. And the `~/.pypirc` gap stops mattering,
because the TestPyPI rehearsal now runs in the workflow rather than from a
workstation. Everything else below still stands.*

- **Rotate the upload token.** Both uploads used an *account*-scoped token,
  which is the only kind that can create a project. The project exists now, so
  revoke it and mint one scoped to `slim-backtrader` alone. The token was also
  pasted into a chat transcript, which is a second reason.
- **2.0.0, 2.0.1 and 2.1.0 are spent.** PyPI refuses a re-upload of a version
  even after its files are deleted. Corrections ship as a new version; bump
  `__version__` in `backtrader/version.py` and nothing else follows.
  (2.1.0 was published on 2026-08-23 - see
  `2026-08-23_performance-scan-and-concurrency.md`.)
- **`~/.pypirc` has no `[testpypi]` section**, so the README's dry-run step
  fails with `InvalidConfiguration` and the real upload runs straight after it
  if both lines are pasted together. Either add the section - repository
  `https://test.pypi.org/legacy/`, username `__token__`, and a TestPyPI token,
  which is separate from the PyPI one - or drop the dry run from the runbook.
- **The simple index lags the upload by a few minutes.** After 2.1.0 was
  uploaded, `pip install` still reported "no matching distribution" while the
  JSON API already listed it, because a CDN edge was serving a stale index. It
  is not evidence of a failed upload. `curl -s -H "Accept:
  application/vnd.pypi.simple.v1+json" https://pypi.org/simple/slim-backtrader/`
  is the check, and it agrees with pip once the edge expires.
- 2.0.0 remains on PyPI with the stripped headers. Yanking it would push users
  to 2.0.1 without breaking pinned installs, and is worth considering.
- The release runbook is the README's *Releasing* section. Nothing is
  automated, and no CI is proposed.
