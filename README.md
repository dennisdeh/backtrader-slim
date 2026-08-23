# slim-backtrader

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
pytest                       # 259 tests, ~47s
pytest --cov                 # with coverage
```

## Documentation

- **Project reports and decisions**: [`reports/`](reports/)
- **Original backtrader repository**: https://github.com/mementum/backtrader
- **Blog**: [Backtrader Blog](http://www.backtrader.com/blog)
- **Docs**: [Full Documentation](http://www.backtrader.com/docu) — written for
  upstream; the removed integrations above no longer apply
- **Indicators Reference**: [List of Built-in Indicators](http://www.backtrader.com/docu/indautoref.html)

## Releasing

Publishing is a manual, maintainer-only step — there is no CI and no automated
release. From a clean checkout of `master`:

```shell
conda activate backtrader
pytest                              # must be green before anything else
rm -rf dist build                   # stale artefacts get uploaded otherwise
python -m build                     # writes dist/*.tar.gz and dist/*.whl
twine check dist/*                  # metadata and README render
twine upload --repository testpypi dist/*      # dry run on TestPyPI first
twine upload dist/*                            # the real thing
```

Notes that save a wasted upload:

- **A version can only be uploaded once.** PyPI rejects a re-upload of the same
  version even after a delete, so bump `__version__` in `backtrader/version.py`
  rather than retrying. Everything else — the version in the wheel, the sdist
  and the metadata — is derived from that one string.
- Authenticate with a **PyPI API token** (username `__token__`), stored in
  `~/.pypirc` or passed as `TWINE_USERNAME` / `TWINE_PASSWORD`. Scope the token
  to this project once it exists.
- Verify the built artefacts before uploading, in a throwaway environment:
  `pip install dist/slim_backtrader-*.whl && python -c "import backtrader"`.

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
