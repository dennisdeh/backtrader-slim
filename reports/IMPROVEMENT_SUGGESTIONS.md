# Improvement suggestions

The code is correct here; it could be better. Nothing in this file is a defect
— those live in `OPEN_ITEMS.md`.

*Last updated: 2026-08-23*

## Performance

Measured 2026-08-23 with `python tools/benchmark.py`, Python 3.13.15, over
`datas/yhoo-1996-2014.txt` (4713 daily bars). Wall-clock figures are the
minimum of five runs on an idle box; the A/B figures below are **CPU time**
(`time.process_time`), measured by alternating both variants inside one
process, because the machine was under load and wall clock was worthless.

Where the time goes:

| case | ms | µs/bar |
|---|---|---|
| feed: load + preload only | 61 | 13.0 |
| empty strategy: runonce + preload | 163 | 34.6 |
| empty strategy: next mode | 232 | 49.1 |
| 1 indicator: runonce + preload | 179 | 37.9 |
| 1 indicator: next mode | 283 | 60.0 |
| 10 indicators: runonce + preload | 450 | 95.6 |
| **10 indicators: next mode** | **2241** | **475.5** |
| 10 indicators: exactbars=-2 | 2189 | 464.5 |

Two facts dominate everything else:

- **`runonce` is ~5x faster than `next` mode under real indicator load**
  (450 ms vs 2241 ms). Both are already the default, but anything that forces
  `next` — `exactbars`, replay, live feeds — pays that multiple.
- **Reading a length is the single hottest operation in the engine.**
  `builtins.len` is top of the profile in both modes: 632k calls in `runonce`,
  2.66M in `next`, where it is 0.85 s of 6.7 s under cProfile.

### Flatten the `__len__` proxy chain — measured 8.8% / 6.4%

`len(indicator)` costs three Python frames and three `len` dispatches:
`LineSeries.__len__` → `len(self.lines)` → `Lines.__len__` →
`len(self.lines[0])` → `LineBuffer.__len__` → `self.lencount`.

Returning `self.lines[0].lencount` from `Lines.__len__` and
`self.lines.lines[0].lencount` from `LineSeries.__len__` removes two frames.

Measured with both variants swapped in and out of one process, over ten
indicators on 4713 bars:

| mode | chained | flat | gain |
|---|---|---|---|
| runonce | 463.8 ms | 422.8 ms | **8.8%** |
| next | 2499.5 ms | 2340.7 ms | **6.4%** |

The full suite (333 passed, 1 skipped, 2 xfailed) is green with the change,
and a probe asserted identical lengths and indicator values.

*Why it is not done here:* it edits the two hottest methods in the metaclass
core to bypass a documented "proxy line operation" indirection, which is
exactly the kind of change CLAUDE.md wants kept off a branch that is already
carrying a behaviour change. It deserves its own commit and its own review.

### `HurstExponent` is 28x slower than any other indicator

Per-indicator survey, net of the 165 ms engine floor:

| indicator | runonce | next | next/once |
|---|---|---|---|
| Hurst / HurstExponent | 1816 ms | 1955 ms | 1.1 |
| KST | 68 ms | 684 ms | 10.1 |
| DirectionalMovement family | ~60 ms | ~600 ms | ~10 |
| Dickson MA family | ~170 ms | ~460 ms | ~2.7 |

Hurst costs more than the next 25 indicators put together, and is the only one
that gains nothing from `runonce` — it overrides `next()` but not `once()`, so
`once` becomes `once_via_next` and runs the same per-bar code.

Its `next()` does, per bar: 18 numpy `std`/`subtract` calls over slices of a
40-element window, then a `numpy.polyfit(x, y, 1)`.

Replacing `polyfit` with the closed-form degree-1 slope is safe — the x values
are the log10 lags, which never change, so the slope is one dot product against
a precomputed centred x. Measured: **2009.6 ms → 1765.5 ms, 12% faster**, with
results identical to ten decimal places.

12% is worth having but says the real cost is the 18 small numpy calls per bar,
not the fit. Vectorising the tau loop is the change that would matter, and
would need a golden-value review, since `test_ind_hurst.py`'s recorded values
are the contract.

### Import cost: 126 ms, and some of it is avoidable

`import backtrader` costs ~126 ms. Notable contributors, from
`python -X importtime`:

- `indicators/oscillator.py` 15 ms, `envelope.py` 7.5 ms, `basicops.py` 5.5 ms
  — metaclass work at class-creation time, inherent to the design.
- `multiprocessing` ~5.6 ms, pulled in eagerly by `cerebro.py` even for a
  plain backtest. Now that optimization goes through `concurrent.futures`,
  `ProcessPoolExecutor` still pulls it, but only when a pool is built if the
  import moves into `_optexecutor`.
- `feeds/yahoo.py` pulls `urllib.parse` (2.4 ms) and `socket` (2.2 ms) at
  import time for the online feed, which most users never touch. The module
  already defers `requests`; deferring the stdlib networking imports the same
  way would pay for itself.

### Delete the object cache rather than maintaining it

`objcache` has been **off by default since 2016-08-17**, and the comment above
it in `indicator.py` records why: an object reused inside another object
carries its `minperiod` across, so the first use is influenced by the second.

It is not free even when off: every `Indicator` and `LineActions` construction
— the hottest constructor path in the library — goes through
`ObjectCache.obtain` to find out the cache is disabled.

It was also the engine's only piece of process-wide mutable state, and the
source of the threading defect fixed on 2026-08-23. Removing it and the
`objcache` parameter would delete two metaclass `__call__` overrides and a
class, and take a documented-but-broken feature out of the public surface.
That is an API break, so it belongs in a release that records it.

### Give the star-exporting modules an `__all__`

Nearly every module is re-exported with `from .module import *` and has no
`__all__`, so imported names leak into the public namespace. Until this
session `bt.feeds.ProxyHandler` and `bt.feeds.urlopen` existed for that reason
alone. An explicit `__all__` per module would make the public surface
intentional and let static analysis work.

### The golden-value tests cannot say which run mode failed

`testcommon.runtest` loops over `runonce × preload × exactbars` inside one test
function, so a failure reports the assertion but not the combination that
produced it. Parametrising at the pytest level would name the failing mode in
the test id. It touches all 70 indicator tests, so it was not done here.

### Coverage is thin in places that matter

Measured 2026-08-23: 75% of statements, 71% counting branches. The figures in
the table are branch-inclusive.

| module | coverage | what is missing |
|---|---|---|
| `talib.py` | 3% | needs the TA-Lib C library; see below |
| `plot/finance.py` | 24% | the candlestick/OHLC artists |
| `store.py` | 33% | the live-trading base class, unreachable offline |
| `indicators/pivotpoint.py` | 37% | the Fibonacci and DeMark variants |
| `feeds/yahoo.py` | 39% | the online feed; the CSV half is covered |
| `btrun/btrun.py` | 48% | most CLI argument combinations |
| `resamplerfilter.py` | 70% | boundary logic for weekly/monthly/yearly rollover |
| `brokers/bbroker.py` | 68% | margin calls, interest accrual, futures-style cash |
| `strategy.py` | 71% | notification paths and multi-data bookkeeping |

`plot/` is largely uncovered by design — one rendering test guards it and the
backend is forced to `Agg`. `store.py` and the online half of `feeds/yahoo.py`
cannot be covered without network, which the suite must not need.

### `talib.py` is untested

3% covered, because TA-Lib is not installed in the dev environment. The tests
would need `pytest.importorskip("talib")` and a CI job that installs the C
library.

### The samples are unverified

68 sample programs, none executed by anything. Several referenced feeds that
were removed years before this session. A smoke test that imports each one (or
runs it against tracked data) would keep them honest.

### `setup.py`-era metadata is gone but `contrib/` was not reviewed

`contrib/` holds a pair-trading sample and two data files. It was left alone
beyond deleting the InfluxDB import scripts; it deserves the same pass the rest
of the tree got.
