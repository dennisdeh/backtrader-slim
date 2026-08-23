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

## What is left

- **Rotate the upload token.** The 2.0.0 upload used an *account*-scoped token,
  which is the only kind that can create a project. Now that the project
  exists, revoke it and mint a token scoped to `slim-backtrader` alone.
- **`2.0.0` is spent.** PyPI refuses a re-upload of a version even after the
  files are deleted, so any correction ships as `2.0.1` - bump `__version__` in
  `backtrader/version.py` and nothing else.
- The release runbook is the README's *Releasing* section. Nothing about it is
  automated, and no CI is proposed; Trusted Publishing is worth revisiting only
  if this repository ever gains a workflow.
