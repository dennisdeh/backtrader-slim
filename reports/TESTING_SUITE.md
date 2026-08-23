# Testing suite

What is tested, how it is selected, and what it costs.

*Last updated: 2026-08-23*

## Running it

```shell
conda activate backtrader
pytest                  # 416 tests, ~48 s
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
| `test_filters_sizers.py` | 35 | filters, sizers, fillers, commission schemes, bar splitters, data wrappers |
| `test_strategy_*.py`, `test_writer.py`, `test_metaclass.py`, others | 11 | strategy runs, writer output, metaclass machinery |
| `test_licensing.py` | 5 | GPLv3 notices, upstream copyright, modification notices, LICENSE, README attribution |
| `test_concurrency.py` | 21 | the optimization executors, `ObjectCache`, concurrent cerebros |
| `test_position.py` | 24 | size/price arithmetic, every branch of `set` and `update` |
| `test_trade.py` | 21 | the trade lifecycle, both directions, `TradeHistory` |
| `test_chaos.py` | 83 | malformed input, raising callbacks, nonsense orders, `Store` |

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

**76% of statements**, 72% once branches are counted (10618 statements, 3318
branches, measured 2026-08-23). It was 73%/69% on 2026-08-22, and **43%**
statement-only over 14205 statements before the slimming session — the
statement count fell because the dead integrations were deleted.

`reports/IMPROVEMENT_SUGGESTIONS.md` lists which modules are still thin and
which of them cannot be covered offline.

Markers: `plotting` (needs matplotlib) and `network` (needs internet; nothing
currently uses it, and nothing should without being marked).

## Known defects are pinned, not skipped

Two tests carry `@pytest.mark.xfail(..., strict=True)`, both in
`test_filters_sizers.py`, both against defects listed in `OPEN_ITEMS.md`.
`strict=True` matters: a defect that gets fixed reports as an *unexpected
pass* and fails the run, so the fix cannot land without the entry moving out
of `OPEN_ITEMS.md`. A plain `xfail` would quietly go green and leave the
record stale.

Where a defect is inert rather than reproducible — `Position.set` reporting
nothing opened from flat — the test asserts today's behaviour instead, with a
docstring saying so. Either way the rule is the same: never leave a known
defect unpinned, and never let a pinned one be mistaken for intended
behaviour.

## Chaos: breaking things on purpose

`test_chaos.py` asks what happens when the inputs are wrong, and holds two
rules apart.

**Nothing a user writes may be swallowed.** A strategy, indicator, analyzer,
observer, sizer or writer that raises has found something the caller needs to
see; a run that quietly finishes after eating the exception has computed the
wrong answer and said nothing. Every such callback is covered, in both
execution paths, and `KeyboardInterrupt`, `SystemExit` and `MemoryError` are
covered too — those are what a bare `except:` takes with it.
`StrategySkipError` is the single deliberate exception, and is tested as one.

**Broken input must be reported precisely.** A malformed row names the file,
the line and the row, and raises `ValueError` — never a bare `StopIteration`,
and never a silently fabricated value.

Two of the tests are mechanical rather than behavioural: the package must
contain no bare `except:` and must never catch `BaseException`. Both defects
this pair guards against were real, and CLAUDE.md prefers a check that can be
run to a rule that has to be remembered.

Where a finding is real but fixing it is a behaviour decision — bars are never
checked for time order, a negative-size buy is refused as a margin failure —
the test asserts today's behaviour and `OPEN_ITEMS.md` carries the reasoning.

## Measuring, rather than testing

`python tools/benchmark.py` reports where the engine spends its time: engine
phases, per-indicator cost in both execution modes, a cProfile of the hot path,
and import cost. It is offline and deterministic, reading only `datas/`.

It is not part of the suite and nothing asserts on its numbers — a timing
threshold on a shared machine is a flaky test. It exists so that a performance
claim can carry the number and the command that produced it, which
`CLAUDE.md` requires. Current figures are in
`reports/IMPROVEMENT_SUGGESTIONS.md`, dated.
