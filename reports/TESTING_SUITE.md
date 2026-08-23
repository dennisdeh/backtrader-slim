# Testing suite

What is tested, how it is selected, and what it costs.

*Last updated: 2026-08-23*

## Running it

```shell
conda activate backtrader
pytest                  # 259 tests, ~47 s
pytest --cov            # adds coverage, ~4 min
pytest -m "not plotting"   # skip the two matplotlib rendering tests
```

`pytest` is configured in `pyproject.toml`: `testpaths = ["tests"]`, so it runs
from the repository root. The suite is offline, needs no credentials and must
stay that way. `filterwarnings` turns backtrader's own `DeprecationWarning`s
and any `SyntaxWarning` into errors.

## What is in it

| file | tests | subject |
|---|---|---|
| `test_ind_*.py` (70 files) | 70 | golden-value regressions, one per indicator |
| `test_analyzers.py` | 30 | every built-in analyzer |
| `test_cerebro.py` | 23 | running, optimisation, resampling, timers, writer, plotting, the btrun CLI |
| `test_utils.py` | 27 | date conversion, AutoDict family, mathsupport, TimeFrame |
| `test_orders_advanced.py` | 19 | stop/trailing/bracket/OCO orders, order_target_* |
| `test_broker.py` | 17 | cash and value accounting, order types, commission, slippage |
| `test_resampling_intraday.py` | 18 | intraday resample/replay, trading calendar, PSAR, PivotPoint |
| `test_feeds.py` | 16 | CSV family, PandasData, Chainer, RollOver |
| `test_filters_sizers.py` | 23 | filters, sizers, fillers, commission schemes |
| `test_strategy_*.py`, `test_writer.py`, `test_metaclass.py`, others | 11 | strategy runs, writer output, metaclass machinery |
| `test_licensing.py` | 5 | GPLv3 notices, upstream copyright, modification notices, LICENSE, README attribution |

## The golden-value contract

The indicator tests are regressions against recorded output. `chkvals` holds
the indicator's value formatted to six decimals at three points — the latest
bar, the first valid bar, and the midpoint — plus `chkmin`, the computed
minimum period.

`testcommon.runtest` runs each case across every combination of
`runonce ∈ {True, False}`, `preload ∈ {True, False}` and
`exactbars ∈ {-2, -1, False}`. An indicator has two independent
implementations — `next()` bar by bar and `once()` vectorised — and this matrix
is what stops a fix landing in only one of them.

**A changed golden value means the library computes something different.**
Never edit one to make a test pass: either the change was intended, and it is
recorded in `changelog.txt`, or it is a bug.

Regenerate a block by running the test file directly
(`python tests/test_ind_sma.py`), which prints it via `main=True` — but that
generator blesses whatever the implementation currently does, so check the
numbers against the formula before pasting them in.

## Fixtures

`tests/conftest.py` holds the shared paths and fixtures. Data comes from
`datas/`, which is tracked, so a fresh clone can run the suite immediately.
`csvdata()` builds the standard 2006 daily feed; `daily_data`, `weekly_data`,
`cerebro` and `cerebro_with_data` are the fixtures.

The `bt.Strategy` subclasses used inside tests are named `TestStrategy` for
historical reasons and carry `__test__ = False`, because pytest would otherwise
try to collect them as test classes.

## Coverage

**73% of statements**, 69% once branches are counted (10582 statements, 3314
branches, measured 2026-08-22). The baseline before this session's work was
**43%** statement-only over 14205 statements — the statement count fell because
the dead integrations were deleted.

Markers: `plotting` (needs matplotlib) and `network` (needs internet; nothing
currently uses it, and nothing should without being marked).
