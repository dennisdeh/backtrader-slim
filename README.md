# Slim Backtrader

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
pip install -e .
```

The engine has **no third-party runtime dependencies**. Optional features are
installed as extras:

```shell
pip install -e ".[plotting]"    # matplotlib, for cerebro.plot()
pip install -e ".[pandas]"      # pandas >= 2.2, for the PandasData feed
pip install -e ".[online]"      # requests, for the Yahoo online feed
pip install -e ".[calendars]"   # pandas_market_calendars
pip install -e ".[talib]"       # TA-Lib indicator bindings
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
pytest                       # 254 tests, ~50s
pytest --cov                 # with coverage
```

## Documentation

- **Project reports and decisions**: [`reports/`](reports/)
- **Original backtrader repository**: https://github.com/mementum/backtrader
- **Blog**: [Backtrader Blog](http://www.backtrader.com/blog)
- **Docs**: [Full Documentation](http://www.backtrader.com/docu) — written for
  upstream; the removed integrations above no longer apply
- **Indicators Reference**: [List of Built-in Indicators](http://www.backtrader.com/docu/indautoref.html)

## Version Numbering

Plain semantic versioning, `X.Y.Z`, starting at `2.0.0`:

- `X`: Major version — incompatible API changes. Removing features is the point
  of this fork, so expect these.
- `Y`: Minor version — new functionality, backwards compatible.
- `Z`: Patch — bug fixes and documentation.

Upstream backtrader used a fourth digit for the number of built-in indicators
(`1.9.78.123`). That digit is retired as of `2.0.0`, and `__btversion__` is now
a 3-tuple.

## License

GPL-3.0-or-later, inherited from upstream backtrader.
