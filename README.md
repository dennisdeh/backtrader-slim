# slim-backtrader

[![CI](https://github.com/dennisdeh/backtrader-slim/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/dennisdeh/backtrader-slim/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/slim-backtrader)](https://pypi.org/project/slim-backtrader/)
[![Python](https://img.shields.io/pypi/pyversions/slim-backtrader)](https://pypi.org/project/slim-backtrader/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

A fork of [backtrader](https://github.com/mementum/backtrader), slimmed down and
brought up to date with modern Python.

Aims of this project:

- Slim down unnecessary features
- Improve performance
- Update aged implementations

The work so far has removed every integration that depended on an abandoned
package, deleted the Python 2 compatibility layer, and moved the project onto a
standard PEP 621 build. See `changelog.txt` for the record and `reports/` for
the detail.

Feel free to contribute!

---

## Installation

```shell
pip install slim-backtrader
```

The distribution is named **`slim-backtrader`**; the import name stays
`backtrader`, so existing strategy code keeps working unchanged:

```python
import backtrader as bt
```

Upstream owns `backtrader` on PyPI and a name there can never be reused, hence
the different distribution name. The flip side is that **this fork and upstream
cannot be installed side by side** — both claim the `backtrader` import name.
Uninstall one before installing the other.

The engine has **no third-party runtime dependencies**. Optional features are
installed as extras:

```shell
pip install "slim-backtrader[plotting]"    # matplotlib, for cerebro.plot()
pip install "slim-backtrader[pandas]"      # pandas >= 2.2, for the PandasData feed
pip install "slim-backtrader[online]"      # requests, for the Yahoo online feed
pip install "slim-backtrader[calendars]"   # pandas_market_calendars
pip install "slim-backtrader[talib]"       # TA-Lib indicator bindings
```

To work on the fork itself, install it editable from a clone instead:

```shell
pip install -e ".[dev]"         # the test suite and tooling
```

## Python Compatibility

**Python >= 3.13.** Older interpreters are not supported: the compatibility
shims that made 2.7 and early 3.x work have been removed, and the code uses
`zoneinfo` from the standard library rather than `pytz`.

## Features

- **Data feeds**
  - CSV files: the backtrader format, a fully configurable generic reader,
    SierraChart and MetaTrader 4 exports, and Yahoo CSV downloads
  - Yahoo Finance online (needs `requests`)
  - *pandas* DataFrames
  - Composite feeds: `Chainer` (concatenate) and `RollOver` (futures rolling)
- **Data management**
  - Filters: Heikin-Ashi, Renko bricks, session filtering and filling,
    calendar-day filling, day-step splitting
  - Multiple data feeds and strategies, multiple simultaneous timeframes
  - Integrated resampling and replaying
- **Backtesting modes** — step-by-step (`next`) or vectorised (`runonce`)
- **Indicators** — 122 built in, plus optional *TA-Lib* bindings and an easy
  path to writing your own
- **Analyzers** — TimeReturn, Sharpe, SQN, DrawDown, TradeAnalyzer, VWR,
  Calmar, PeriodStats, Transactions and more
- **Broker simulation** — Market, Close, Limit, Stop, StopLimit, StopTrail,
  StopTrailLimit, OCO and bracket orders, slippage, volume-based filling,
  continuous cash adjustment for futures-like instruments
- **Position sizing** via Sizers, and `order_target_size/value/percent`
- **Cheat-on-close and cheat-on-open** modes
- **Schedulers and trading calendars**
- **Plotting** *(requires matplotlib)*

### Removed in 2.0.0

Interactive Brokers, VisualChart and Oanda (live trading and their data
feeds), the pyfolio analyzer, and the blaze, InfluxDB and Quandl feeds. Each
depended on a package that is abandoned, Python-2-only, or serves an API that
no longer exists. See `reports/DECISIONS.md`.

## Plotting is non-interactive

`cerebro.plot()` renders through the `Agg` backend and does not open a window.
It returns the figures, so save them yourself:

```python
figs = cerebro.plot(iplot=False)
figs[0][0].savefig("result.png")
```

## Running the tests

```shell
conda env create -f environment.yml
conda activate backtrader
pip install -e ".[dev]"
pytest                       # 434 tests, ~50 s
pytest --cov                 # adds coverage, ~4 min
```

The suite is offline: no network, no credentials, no services. `datas/` is
tracked, so a fresh clone can run it immediately.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push to
`master`, every pull request, and on demand. It is the gate; running `pytest`
locally first is still the faster way to find out.

| job | what it establishes |
|---|---|
| `black` | the tree is formatted (88 columns, `py313`) |
| `pytest` | the suite passes on 3.13 and 3.14 on Linux, and on 3.13 on macOS and Windows — one row also installs the optional extras, so the trading-calendar tests actually run instead of skipping |
| `coverage` | coverage has not collapsed; the XML report is kept as an artefact |
| `build and verify artefacts` | the sdist and wheel build, `twine check --strict` passes, the sdist carries a suite that passes with **no** optional packages installed, and the wheel installs into an empty environment pulling in nothing |

`CI passed` is the aggregate status; require that one in branch protection and
adding a job later needs no change to the rule.

The macOS and Windows rows exist because `pyproject.toml` claims
`Operating System :: OS Independent`; they are what makes that claim checkable
rather than aspirational.

## Documentation

- **Project reports and decisions**: [`reports/`](reports/)
- **Original backtrader repository**: https://github.com/mementum/backtrader
- **Blog**: [Backtrader Blog](http://www.backtrader.com/blog)
- **Docs**: [Full Documentation](http://www.backtrader.com/docu) — written for
  upstream; the removed integrations above no longer apply
- **Indicators Reference**: [List of Built-in Indicators](http://www.backtrader.com/docu/indautoref.html)

## Releasing

A release is one tag; CI does the rest.

```shell
$EDITOR backtrader/version.py       # __version__ = "2.2.0" - the whole change
$EDITOR changelog.txt               # UNRELEASED -> "2.2.0: 2026-08-24"
git commit -am "Release 2.2.0"
git tag -a v2.2.0 -m "slim-backtrader 2.2.0"
git push origin master v2.2.0
```

Pushing a `vX.Y.Z` tag runs
[`.github/workflows/release.yml`](.github/workflows/release.yml), which:

1. builds the sdist and wheel from a pristine checkout — no editable install
   has run there, so nothing local can leak into the artefacts;
2. **stops if the tag and `__version__` disagree**;
3. runs `twine check --strict`;
4. installs the sdist on 3.13 and 3.14 and runs the suite the sdist itself
   ships, then installs the wheel into an empty environment and checks that it
   pulls in no dependencies, that `import backtrader` reports the right
   version, and that `btrun --help` works;
5. publishes to PyPI, and only then;
6. creates the GitHub release, with the artefacts attached and that version's
   `changelog.txt` section as the notes.

Nothing is uploaded until every step above has passed.

**There is no PyPI API token in this repository.** Publishing uses PyPI's
trusted publishing: GitHub mints a short-lived OIDC credential, and PyPI
accepts it only for this workflow file, in this repository, running in the
`pypi` environment.

### One-time setup on PyPI

At <https://pypi.org/manage/project/slim-backtrader/settings/publishing/>, add
a GitHub publisher:

| field | value |
|---|---|
| Owner | `dennisdeh` |
| Repository name | `backtrader-slim` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Then revoke the account-scoped API token that uploaded 2.0.0–2.1.0: it is no
longer needed, and an account-scoped token is the widest credential PyPI
issues.

Optionally add a required reviewer to the `pypi` environment in the
repository's settings, which turns the upload into an approval click.

To rehearse on TestPyPI, add a *pending* publisher at
<https://test.pypi.org/manage/account/publishing/> with the same fields, the
project name `slim-backtrader` and the environment name `testpypi`, then run
the Release workflow manually with the **TestPyPI** box ticked. TestPyPI
accounts are separate from PyPI ones.

### Notes that save a wasted upload

- **A version can only be uploaded once.** PyPI rejects a re-upload of the same
  version even after a delete, so a correction is a new version: bump
  `__version__` and tag again. 2.0.0, 2.0.1 and 2.1.0 are spent.
- **The tag is the trigger.** Pushing `v2.2.0` publishes 2.2.0. There is no
  other confirmation step unless the `pypi` environment has a reviewer.
- **The simple index lags an upload by a few minutes.** `pip install` reporting
  "no matching distribution" straight after a release is a stale CDN edge, not
  a failed upload. `curl -s -H "Accept: application/vnd.pypi.simple.v1+json"
  https://pypi.org/simple/slim-backtrader/` is the check that agrees with pip
  once the edge expires.
- **Manual fallback**, if Actions is unavailable: `rm -rf dist build && python
  -m build && twine check --strict dist/* && twine upload dist/*`, with a PyPI
  API token as username `__token__`. It skips every verification above, so use
  it only when the workflow cannot run at all.

## Version Numbering

Plain semantic versioning, `X.Y.Z`, starting at `2.0.0`:

- `X`: Major version — incompatible API changes. Removing features is the point
  of this fork, so expect these.
- `Y`: Minor version — new functionality, backwards compatible.
- `Z`: Patch — bug fixes and documentation.

Upstream backtrader used a fourth digit for the number of built-in indicators
(`1.9.78.123`). That digit is retired as of `2.0.0`, and `__btversion__` is now
a 3-tuple.

## License and attribution

**slim-backtrader is a modified version of
[backtrader](https://github.com/mementum/backtrader), originally written by
Daniel Rodriguez.** All of the engine's design and the overwhelming majority of
its code are his work; this fork subtracts from it and modernizes it rather
than replacing it.

- Copyright © 2015–2023 Daniel Rodriguez (original work)
- Copyright © 2026 Dennis Hansen (modifications)

Licensed under the **GNU General Public License, version 3 or later**, the same
licence as upstream. The full text ships with the package in `LICENSE`; if you
did not receive it, see <https://www.gnu.org/licenses/>.

This program comes with ABSOLUTELY NO WARRANTY. It is free software, and you
are welcome to redistribute it under the conditions of the GPL.

Every source file modified by this fork says so in its header, with the year,
as GPL-3.0 section 5(a) requires. What was changed is recorded in
`changelog.txt` — the 2.0.0 entry lists the removed integrations, the dropped
Python 2 layer and every API break.

One file is **not** under the GPL: `backtrader/plot/multicursor.py` is derived
from matplotlib 1.2.0 and carries its own licence from John D. Hunter
(Copyright © 2002–2011), reproduced in full at the top of that file, along with
a summary of the changes made to it. It is GPL-compatible, which is why it can
be distributed as part of this work.
