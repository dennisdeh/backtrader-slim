# 2026-08-23 — Timing the engine, fixing concurrency, and breaking it on purpose

A scan of the whole tree for where time goes, the concurrency work the scan
turned up, and a chaos pass over the engine's exception handling. Everything
measured here is reproducible with `python tools/benchmark.py`, which this
session added.

Environment: Python 3.13.15, conda env `backtrader`, 64 cores.

---

## What the scan found

### The engine floor and the two execution paths

Over `datas/yhoo-1996-2014.txt` (4713 daily bars), minimum of five runs:

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

Reading the feed is 61 ms — over a third of an otherwise empty vectorised run.
Everything above that is engine overhead, and the gap between the two
execution paths is the headline: **`runonce` is about 5x faster than `next`
under real indicator load.** One SMA costs 14 ms vectorised and 104 ms bar by
bar.

### `len()` is the hottest thing in the library

cProfile puts `builtins.len` at the top in both modes — 632k calls under
`runonce`, 2.66M under `next`, where it accounts for 0.85 s of 6.7 s. The
cause is a three-deep proxy chain: `LineSeries.__len__` → `Lines.__len__` →
`LineBuffer.__len__` → `self.lencount`, three Python frames for one integer.

Flattening it measured **8.8% faster in `runonce` and 6.4% in `next`** (CPU
time, both variants alternated inside one process), suite green, lengths and
indicator values verified identical. Not applied — see
`IMPROVEMENT_SUGGESTIONS.md` for why it wants its own commit.

### One indicator dominates the rest

Surveyed all 293 exported indicator names (many are aliases), net of the
165 ms engine floor. `HurstExponent` costs **1816 ms**, more than the next 25
indicators combined, and is the only one that gains nothing from `runonce`
(ratio 1.1) because it overrides `next()` but not `once()`. Behind it, the
`DirectionalMovement` family and `KST` run ~10x slower in `next` mode.

Replacing Hurst's per-bar `numpy.polyfit` with the closed-form degree-1 slope
measured 12% faster with identical results — worth having, but it shows the
real cost is the 18 small numpy calls per bar, not the fit.

### Import cost

`import backtrader` is ~126 ms. Most of it is metaclass work at class-creation
time and inherent. The avoidable parts are `multiprocessing` (5.6 ms) and the
stdlib networking `feeds/yahoo.py` pulls in for an online feed most users never
touch.

---

## What the scan turned into

The timing work kept running into the same theme — process-wide state — so the
session followed it.

### Concurrent cerebros corrupted each other

The object cache behind `objcache` lived on the `MetaIndicator` and
`MetaLineActions` metaclasses, and `cerebro.run()` clears it and toggles it on
every call. Two cerebros in different threads clobbered each other: a run
declaring `objcache=False`, running alongside one using `objcache=True`,
silently received the other's indicator instances and built two indicators
where it had declared three.

`tests/test_concurrency.py` reproduces this deterministically rather than by
luck — it pins the interleaving with two events, so the uncached run is
blocked inside its strategy's `__init__` at the moment the cached run's
prologue flips the global flag. Against the unfixed tree:

```
uncached run (objcache=False) -> (4117.964, 2)   expected (4117.964, 3)
RESULT: FAIL - the uncached run was infected
```

Fixed by making the storage thread-local, in one shared `metabase.ObjectCache`
instead of the copy-pasted logic in both metaclasses.

### Optimization would have broken on Python 3.14

Python 3.14 removes pickle support from `itertools`, and optimization pickles
the cerebro to its workers. Four attributes held one — `Cerebro._dataid`,
`Cerebro.stcount`, `Strategy._alnames`, `WriterFile._len` — and
`Cerebro.optstrategy` stored its parameter grid as a live `itertools.product`.
All are plain ints and a list now. `pyproject.toml` already advertises 3.14.

Materializing the grid fixed a second defect for free: the iterator was
single-use, so a second `run()` on an optimizing cerebro saw it exhausted.

### `multiprocessing.Pool` → `concurrent.futures`

Requested during the session. `executor` (default `'process'`) picks the pool.
`'thread'` gives each worker a private copy of the cerebro, through the same
`__getstate__` contract the process pool pickles through, so both return
identical results — verified across `maxcpus=1`, `maxcpus=2` process,
`maxcpus=2` thread and `maxcpus=None`.

**`'thread'` will not speed up optimization on a GIL-carrying interpreter.**
The work is CPU-bound Python. It is there for free-threaded builds and for
debugging in one address space, and the docstring says so rather than letting
someone discover it by benchmarking.

The pool is closed through a context manager; the old code called
`pool.close()` and never joined.

### Two data wrapper classes had never run

`DataFilter` and `DataFiller` raised `AttributeError: _tzinput` on their first
bar. Nothing hands the inner feed to cerebro, so nothing gave it an
environment, and they called the wrapped feed's `start()` where only `_start()`
reaches `_start_finish()`. Nothing in the tree exercised either class — the
`data-filler` sample names them in its `--help` text but uses the unrelated
`SessionFilter`/`SessionFiller`.

Both start the inner feed properly now. Two defects behind that are recorded in
`OPEN_ITEMS.md` and pinned by strict `xfail` rather than fixed: `DataFilter`
double-delivers under preload, and `DataFiller` reads the numeric `sessionend`
where it needs the `datetime.time`.

---

## Chaos: what happens when the inputs are wrong

A third pass broke things on purpose. The result splits cleanly in two.

**User code is handled well.** Everything a user can write — strategy
`__init__`/`start`/`prenext`/`next`/`stop`/`notify_*`, analyzer, observer,
sizer, indicator in both execution paths, writer — propagates what it raises.
Nothing is swallowed, and `StrategySkipError` is correctly the single
exception. That took no fixing; it took tests to say so.

**Input parsing was not.** Every defect was in the feeds.

- **The Yahoo feed fabricated data.** A bare `except: v = 0.0` around the
  volume field was commented as covering a `"null"` volume — but a null never
  reaches it, because a loop at the top of the same method skips any row
  carrying one. What it actually caught was a row *too short to have a volume
  column*, which it turned into a silent zero. Every volume-based indicator
  and sizer downstream then computed against invented data, and nothing said
  anything.

- **A truncated CSV row raised a bare `StopIteration`** with an empty message.
  Wrong type — `StopIteration` is the iteration protocol's sentinel — and a
  PEP 479 hazard: any caller that is a generator would silently turn it into a
  `RuntimeError`. Nothing in the tree is such a caller today, which is the only
  reason it had not bitten.

- **No CSV error named its line.** `could not convert string to float: 'abc'`,
  against a million-row file. `CSVDataBase._load` now re-raises row failures as
  a `ValueError` naming the file, the line and the row, with the original kept
  as `__cause__`. The line counter lives in the base class, so every CSV feed
  gained it.

- **Five bare `except:` clauses**, each also swallowing `KeyboardInterrupt`,
  `SystemExit` and `MemoryError`. All narrowed.

- **`Store.getdata` failed with `'NoneType' object is not callable`** when a
  subclass had not set `DataCls`. No class in the tree subclasses `Store` any
  more — every store integration was deleted in the slimming — so nothing had
  ever exercised it. 33% → 73% covered.

Two of the new tests are mechanical rather than behavioural: the package must
contain no bare `except:`, and must never catch `BaseException`. CLAUDE.md
prefers a check that can be run to a rule that has to be remembered, and both
defects these guard against were real.

### Two more, fixed after a second look

Both were filed as pinned-not-fixed first, then fixed on request.

**A feed could go back in time and nothing said anything.** A source whose rows
ran backwards, or had one date out of place, loaded without a word — and every
indicator, the broker and every analyzer then computed against a timeline that
never existed. `AbstractDataBase.load()` now refuses a bar older than the one
before it, naming both dates. Equal stamps stay legal, because tick data
routinely carries several ticks within one second, and the new `checkorder`
parameter turns the check off for a source that orders itself.

The worry that stopped it the first time was cost and false positives. Both
turned out to be small: the check sees only the raw source stream, because
filter-produced bars return through `_fromstack()` before reaching it, so
resampling and replay are untouched; `Chainer` already enforced the same rule
on itself and `reverse=True` reverses the file at `start()`. Measured cost is
**+2.4%** of CPU on a bare feed load and **+0.7%** with ten indicators
attached.

One wrinkle was worth the trouble: the golden-value tests drive *one* feed
object through the whole `runonce × preload × exactbars` matrix, so the last
bar of one run is still remembered when the next begins. The reset belongs in
`start()`, which runs every time, not in `_start_finish()`, which runs once.
Putting it in the wrong one failed 84 tests, which is a good argument for
having them.

**A NaN size or price was refused as a margin call.** These reached the broker
intact, and the cash arithmetic turned them into `Order.Margin` — NaN compares
false against everything, so `cash >= 0.0` failed. The strategy was told the
account was short of money when it had asked for something meaningless.
`OrderBase` now raises `ValueError` for a size that is `None`, NaN, infinite or
negative, and for a NaN or infinite price, pricelimit, trailamount or
trailpercent. A genuine funding shortfall still reports `Order.Margin`.

**A correction to the original finding:** it also claimed `buy(size=-5)` was
mislabelled. It was not. `Strategy.buy()` takes `abs(size)`, so that call buys
5 — and the `Margin` observed when the finding was written was entirely real,
5 units at ~3600 against the default 10000 of cash. Size is a magnitude and the
direction comes from `buy()`/`sell()`. Only the direct `broker.buy(size=-5)`
path, which skips that normalisation, is refused now.

---

## Clearing the board

Every finding the session had filed as pinned-not-fixed was then fixed. Six of
them; the notes below are what each turned out to be, since in three cases the
recorded reason for leaving it alone did not survive contact.

**`DataFilter` delivered every bar twice under preload.** `_load` asked
`not len(dataname)` to mean "not started yet" — but `len()` is also 0 right
after `home()` rewinds a preloaded feed, so it restarted the source, reopened
the file it had just closed, and read the whole thing again. Both wrappers
start their inner feed from `start()` now. The time-order check added earlier
the same day found this on its own: the second pass showed up as bar 256 dated
2006-01-02, after 2006-12-29.

**`DataFiller` read the numeric `sessionend`.** One word — `p.sessionend`, not
`sessionend`. What had held it up was that the class had never run, so its
output was unverified. It is verified now, by hand rather than by recording
what the code does: given a feed carrying 10:31 and 10:34 of one session, the
filler inserts 10:32 and 10:33 priced at the 10:31 close, with the configured
fill volume, and leaves the real bars alone.

**`Position.set` reported nothing opened from flat.** It read `self.size` — the
old size, always 0 in that branch — where its siblings say `size`.

**Two `Vortex` indicators.** The exported one lived in
`backtrader/indicators/contrib/`, so importing the identical top-level module
silently re-registered the name. The top-level copy survives — it is the
Black-formatted one, and the contrib copy carried a duplicated copyright line
from the licence sweep. `backtrader/indicators/contrib/` held nothing else, so
the package is gone.

**`PivotPoint`'s pivot line.** The mechanism turned out to be worth
understanding before touching: `.p` is not shadowed by anything clever.
`LineSeries.__getattr__` is what forwards an unknown attribute to `.lines`, and
`__getattr__` only runs when normal lookup *fails* — so the params instance
attribute won and the line never got a look in. No alias can reclaim `.p`. The
line is `pivot` now, and `linealias = dict(pivot="p")` keeps `.lines.p`
returning the same line object, so the only spelling that ever worked still
works.

**PandasData's timestamps.** A DataFrame index carries a bare date, landing on
midnight, while every CSV feed stamps a daily bar at the session end — so the
same session came out a day apart depending on which feed loaded it. Both
pandas feeds apply the house convention now. Only a bar with *no time of day at
all* is moved, and only for daily or coarser timeframes: intraday data, where
midnight is a real time rather than a missing one, is untouched.

### And the unpinned one

**`frompackages` defeated static analysis.** The reason it had been left alone
was that importing the names normally would make numpy and statsmodels hard
dependencies of a package whose `dependencies` list is deliberately empty. True
— but that is an argument against *module-level* imports, not against visible
ones. Each module now declares the names it needs at module level and binds
them in a small helper called from `__init__`: the import still happens on
first construction, and now says which package is missing and how to install
it. `calmar.py` turned out to be asking for `collections` and `math` — stdlib,
with no optionality to preserve at all.

pyflakes over the three modules: **19 undefined names → 1**, and the one left
is an alias in an `__all__`.

The invariant is now checked instead of trusted: a test runs `import
backtrader` in a fresh interpreter and fails if numpy, pandas, statsmodels,
matplotlib or requests arrives with it, and pins that numpy shows up exactly
when a `HurstExponent` is built. Another fails if any module declares the
directive again. The mechanism itself stays — it is a documented extension
point, and `test_metaclass.py` still exercises it.

The original entry also listed `factorial` among the injected names. It is not
in `backtrader/` at all — it is in `tests/testcommon.py`, which uses the
directive on purpose in order to test it.

### What is left

One item, newly filed, and it is the residue of the above: **the `alias`
directive is invisible to a static checker too**. Aliases are made by the
metaclass, so pyflakes reports `TR` in `atr.py`, `ROC` in `momentum.py` and
`RSI` three times in `rsi.py`.

The obvious fix — substitute the canonical class name — is wrong, and worth
recording as wrong. An alias is *not* the same object: `RSI.__mro__` is
`RSI -> RelativeStrengthIndex`, and `RSI_SMA` inherits from `RSI`. Rewriting
`class RSI_SMA(RSI)` would silently change the class hierarchy. CLAUDE.md
already warns that aliases are public API; this is what that warning is for.

Five undefined names in three lines, all the same understood pattern, is a
different thing from nineteen spread through three modules hiding whatever else
was wrong in them.

---

## Tests and coverage

259 → **434 passed**, 1 skipped, 50.7 s — and no `xfail`s left, because
every defect they guarded is fixed.
Coverage 73% → **76% of statements**, 69% → **72%** counting branches.
`store.py` 33% → 73%, `feed.py` 69% → 73%.

The chaos pass moved the total only slightly — most of what it exercises are
error paths a line or two long — but it is where the defects were.

| file | added | subject |
|---|---|---|
| `test_concurrency.py` | 21 (new) | executors, `ObjectCache`, concurrent cerebros |
| `test_position.py` | +23 | every branch of `set`, the short side of `update`, clone/fix |
| `test_trade.py` | +20 | lifecycle both directions, `TradeHistory`, pickle round-trip |
| `test_filters_sizers.py` | +12 | bar splitters and the two data wrappers |
| `test_chaos.py` | 83 (new) | malformed input, raising callbacks, orders, ordering, `Store` |

New tests went into the existing files rather than parallel ones. The
concurrency tests are new because nothing covered the subject.

---

## Also found along the way

All of these are fixed; they are listed because none was what the session set
out to look for.

- **A corrupt shebang** in `strategy.py` (`#!/usr/bin389/env python`) — the
  only such line in the tree.
- **The conda env is `backtrader`, not `slim-backtrader`.** `environment.yml`
  declared the distribution name, so `conda env create` built an env none of
  the documented `conda activate` lines matched. Fixed in four files.
- **The last Python 2 shims** in `cerebro.py` and `writer.py`
  (`collectionsAbc`, with a Russian comment) and in
  `test_strategy_optimized.py` (a `time.clock` fallback, removed from Python
  in 3.8). CLAUDE.md authorizes deleting these on sight; they went in their own
  mechanical commit so as not to bury the behaviour changes.

## Where the suite's time goes

`test_strategy_optimized.py::test_run` is **20.4 s of the 48 s suite** — 43%,
in one test. It runs a 21-combination optimization single-threaded. Nothing
was changed about it, but it is the obvious target if suite time ever matters.
