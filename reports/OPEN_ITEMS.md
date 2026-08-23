# Open items

Places where the code does something other than what it should. Fixed entries
move out of this file; things that turn out to be deliberate move to
`DECISIONS.md`.

*Last updated: 2026-08-23*

## Open

### `DataFilter` delivers every bar twice when preloading

*Found 2026-08-23.* `bt.filters.DataFilter(dataname=feed, funcfilter=...)`
returns 510 bars for the 255-bar 2006 daily fixture, each date appearing
exactly twice. With `preload=False` it returns the correct 255.

`DataFilter.preload()` starts and preloads the wrapped feed, rewinds it with
`home()`, and then calls `super().preload()`, which walks it again through
`_load()`. One of the two passes is redundant, but which one is meant to win
is a design question, not an obvious edit.

Pinned by `test_data_filter_under_preload_does_not_duplicate_bars`, a strict
`xfail`, so a fix reports as an unexpected pass rather than going unnoticed.

*Why it is not fixed here:* nothing in the tree used the class at all until
2026-08-23, so there is no established behaviour to preserve, and picking a
pass to drop needs a decision about what `preload` means for a wrapping feed.

### `DataFiller` reads the numeric `sessionend` where it needs the time

*Found 2026-08-23.* `DataFiller._load()` calls
`datetime.combine(dtime_prev.date(), self.p.dataname.sessionend)` and raises
`TypeError: combine() argument 2 must be datetime.time, not float`.

On a started feed the two names differ: `p.sessionend` is the
`datetime.time(23, 59, 59, 999990)` the user configured, while `sessionend` is
the float date `_start_finish()` computed from it. The filler wants the former.

Pinned by `test_data_filler_inserts_the_missing_minutes`, a strict `xfail`.

*Why it is not fixed here:* the one-word change is obvious, but the class has
never run, so what it should produce is unverified — it needs a golden case
built by hand before its output can be trusted.

### `Position.set` reports nothing opened when opening from flat

*Found 2026-08-23.* Every branch of `Position.set` reports what the new size
opened, except the one taken when the position is currently flat, which reads
`self.upopened = self.size` — the *old* size, always 0 there — where its
siblings say `size`. `Position.update` reports `opened == size` for the same
transition, so the two disagree.

Inert today: nothing outside `position.py` reads `upopened` or `upclosed`, and
`set` is only ever called from `Position.__init__`. Reachable through the
public `Position` API.

Pinned by `test_setting_from_flat_reports_nothing_opened`, which asserts the
current behaviour so that correcting it is a deliberate act with a changelog
entry.

### Two `Vortex` indicators exist, and the exported one is not the maintained one

*Found 2026-08-23.* `backtrader/indicators/vortex.py` and
`backtrader/indicators/contrib/vortex.py` define the same indicator with
identical logic. `bt.indicators.Vortex` resolves to the **contrib** one, which
`indicators/contrib/__init__.py` installs explicitly; the top-level module is
imported by nothing, which is why it reports 0% coverage while
`tests/test_ind_vortex.py` passes.

The two differ only in formatting: the Black sweep of 2026-08-22 reached the
top-level copy and skipped the contrib one, because `extend-exclude` matches
any path containing `/contrib/`.

*Impact:* `import backtrader.indicators.vortex` re-registers `Vortex` in
`MetaIndicator._indcol`, so an innocuous-looking import silently swaps which
class `btind.Vortex` names.

*Why it is not fixed here:* deleting the duplicate is a one-line change, but
which copy should survive — and whether `indicators/contrib/` should keep its
Black exemption — is a layout decision.

### PandasData and the CSV feeds stamp the same bar differently

*Found 2026-08-22.* The CSV feeds stamp a daily bar at the session end
(`23:59:59.999`); `PandasData` takes the DataFrame index verbatim, so the same
session comes out at midnight. Feeding the same instrument from both sources
into one Cerebro therefore misaligns them by a day, silently.

Pinned, not fixed, by
`test_pandas_bars_are_stamped_at_midnight_not_session_end` — the test asserts
today's behaviour so a fix will show up as a failure rather than a surprise.

*Why it is not fixed here:* changing either side alters the timestamps every
existing strategy sees. It needs a deliberate decision about which convention
wins.

### `PivotPoint`'s pivot line is unreachable by its own name

*Found 2026-08-22.* The indicator declares a line named `p`, but `.p` on every
`LineIterator` is the params object, which shadows it. The line is only
reachable as `.lines.p`. Any other line name would work; `p` is the one that
collides.

Pinned by `test_pivotpoint_needs_a_coarser_timeframe`.

### `frompackages` defeats static analysis

*Found 2026-08-22.* The metaclass injects names (`pd`, `sm`, `coint`,
`asarray`, `factorial`) into class bodies at creation time, so pyflakes reports
them as undefined and cannot see genuine mistakes in those files. `ols.py`,
`hurst.py` and `calmar.py` are affected.

*Impact:* the static check that caught a real break during the Python 2 sweep
is blind in exactly those modules.

## Fixed after 2.0.1

### A feed could go back in time and nothing said anything

*Found 2026-08-23, fixed the same day.* A source whose rows ran backwards, or
had one date out of place, loaded without a word, and every indicator, the
broker and every analyzer then computed against a timeline that never existed.

`AbstractDataBase.load()` now refuses a bar older than the one before it,
naming both dates and the bar number. Equal stamps are still accepted - tick
data routinely carries several ticks within the same second. The new
`checkorder` parameter (default `True`) turns it off for a source that
delivers its own ordering on purpose.

The check sees the raw source stream only: bars a filter produced come back
through `_fromstack()` and return before reaching it, so resampling and replay,
which move the clock about deliberately, are unaffected. `Chainer` already
enforced the same rule for itself, and `reverse=True` feeds reverse the file at
`start()`, so both were already in order.

Cost, measured 2026-08-23 by alternating both settings inside one process:
**+2.4%** of CPU on a bare feed load, **+0.7%** with ten indicators attached,
within noise in `next` mode.

### A NaN size or price was refused as a margin call

*Found 2026-08-23, fixed the same day.* `buy(size=float('nan'))` and a limit
order at a NaN price reached the broker intact, and the cash arithmetic turned
them into `Order.Margin` - NaN compares false against everything, so the
broker's `cash >= 0.0` test failed. The strategy was told the account was short
of money when it had in fact asked for something meaningless.

`OrderBase.__init__` now raises `ValueError` for a size that is `None`, NaN,
infinite or negative, and for a NaN or infinite `price`, `pricelimit`,
`trailamount` or `trailpercent`. These are programming errors rather than
market conditions, so they fail loudly instead of arriving as a notification
the strategy would have to guess the meaning of. A genuine funding shortfall
still reports `Order.Margin`.

*Correction to the entry this replaces:* it also claimed `buy(size=-5)` was
mislabelled. It is not. `Strategy.buy()` takes `abs(size)`, so that call buys
5 - and the `Margin` seen when the finding was written was real, 5 units at
~3600 against the default 10000 of cash. Size is a magnitude and the direction
comes from `buy()`/`sell()`; only the direct `broker.buy(size=-5)` path, which
bypasses that normalisation, is now refused.


### The Yahoo feed fabricated a volume for a row that had none

*Found and fixed 2026-08-23.* `feeds/yahoo.py` wrapped the volume field in a
bare `except: v = 0.0`, commented as covering a "null" volume. A null never
reached it - the loop at the top of the same method skips any row carrying one.
What it caught was a row too short to have a volume column, which it turned
into a silent zero, corrupting every volume-based indicator and sizer
downstream without a word.

Found by `tests/test_chaos.py`, which feeds the parser rows that are broken in
each of the ways a real file is.

### A truncated CSV row raised a bare `StopIteration`

*Found and fixed 2026-08-23.* Empty message, and the wrong type: StopIteration
is the iteration protocol's sentinel, so raising it from a parser means that
under PEP 479 any caller that is a generator turns it into a RuntimeError
instead. Nothing in the tree is such a caller today, which is the only reason
it had not bitten.

`CSVDataBase._load` now re-raises row-level failures as a `ValueError` naming
the file, the line and the row, with the original kept as `__cause__`. Every
CSV feed gained the line number, which none of them had: the old message was
`could not convert string to float: 'abc'` with no way to tell which of a
million rows was meant.

### Five bare `except:` clauses

*Found and fixed 2026-08-23.* Besides the Yahoo one above:
`lineseries.plotlabel` (now `AttributeError`), the `lineiterator` argument
probe (now `TypeError, ValueError`), the matplotlib backend switch (now
`Exception`) and the plot artist unwrap (now `TypeError, IndexError,
KeyError`). A bare `except:` swallows `KeyboardInterrupt`, `SystemExit` and
`MemoryError` along with everything else.

`tests/test_chaos.py` carries the mechanical check that keeps them out: the
package must contain no bare `except:` and must never catch `BaseException`.

### `Store.getdata` failed with `'NoneType' object is not callable`

*Found and fixed 2026-08-23.* A `Store` subclass that has not set `DataCls` or
`BrokerCls` got that message, which says nothing about the contract it missed.
Both now raise `NotImplementedError` naming the attribute. No class in the tree
subclasses `Store` any more - every store integration was deleted during the
slimming - so nothing had exercised it; it was at 33% coverage, now 73%.


### Concurrent cerebros clobbered each other's object cache

*Found and fixed 2026-08-23.* The cache behind `objcache` lived on the
`MetaIndicator` and `MetaLineActions` metaclasses — process-wide — and
`cerebro.run()` clears it and switches it on or off on every call. Two cerebros
running in different threads therefore reached into each other: a run declaring
`objcache=False`, executing alongside one using `objcache=True`, silently
received the other's cached indicator instances and built two indicators where
it had declared three.

The storage is thread-local now, and the logic both metaclasses had
copy-pasted is one class, `metabase.ObjectCache`.
`tests/test_concurrency.py` pins the interleaving that reproduces it rather
than leaving it to chance, and was demonstrated red against the unfixed tree.

### Optimization would have broken outright on Python 3.14

*Found and fixed 2026-08-23.* Python 3.14 removes pickle support from
`itertools`, and optimization pickles the cerebro to its workers. Four places
held an `itertools` object on something that gets pickled: `Cerebro._dataid`,
`Cerebro.stcount`, `Strategy._alnames` and `WriterFile._len`. All are plain
ints now.

`Cerebro.optstrategy` also stored its parameter combinations as a live
`itertools.product` iterator; it stores a list. That fixed a second defect
alongside the pickling one — the iterator was single-use, so a second `run()`
on an optimizing cerebro saw it exhausted.

The classifiers in `pyproject.toml` already advertise Python 3.14.

### `DataFilter` and `DataFiller` could not load a single bar

*Found and fixed 2026-08-23.* Both wrap another feed rather than filtering one
in place, and both raised `AttributeError: _tzinput` on the first bar. Nothing
hands the inner feed to cerebro, so nothing gave it an environment; and they
called the wrapped feed's `start()`, where only `_start()` reaches
`_start_finish()` — the half that sets `_tzinput` and the trading calendar.

Both now start the inner feed through a `_startinner()` helper. Two further
defects sit behind that one and are listed under *Open* above.

Nothing in the tree exercised either class, samples included; the
`data-filler` sample names them in its `--help` description but uses
`SessionFilter`/`SessionFiller`, which are different classes in `session.py`.

### `strategy.py` carried a corrupt shebang

*Found and fixed 2026-08-23.* `#!/usr/bin389/env python`. Harmless, since the
module is imported rather than executed, and the only such line in the tree.

## Fixed after 2.0.0

### The GPLv3 header was stripped from three shipped files

*Found and fixed 2026-08-23. Shipped broken in 2.0.0.*

`backtrader/brokers/__init__.py`, `backtrader/feeds/__init__.py` and
`backtrader/stores/__init__.py` lost their entire GPLv3 header block —
upstream's copyright line included — in commit `3359215` ("Remove integrations
that depend on abandoned packages"), which rewrote the import lists at the top
of each file and took the comment block with them. 2.0.0 was uploaded to PyPI
in that state.

This matters beyond tidiness: GPL-3.0 section 4 requires that the licence and
copyright notices be kept intact on every copy conveyed, and these files are
conveyed in both the wheel and the sdist. It also broke the rule CLAUDE.md
states outright — the header block stays, even during a mechanical sweep.

The headers are restored, and `tests/test_licensing.py` now fails if any
shipped file loses its notice again. That test was demonstrated red against the
pre-fix tree before the fix was kept.

Related, found in the same pass and fixed with it: no file said it had been
modified, which GPL-3.0 section 5(a) requires of a modified work, and the nine
fork-authored test modules carried no licence header at all.

## Fixed in 2.0.0

| item | fix |
|---|---|
| `tzparse('UTC')` raised `AttributeError` without pytz | resolved through stdlib `zoneinfo`; `_ZoneInfo` supplies `.localize()` |
| `AutoDict._close()` never closed the dict | `__setattr__` had `if False and key.startswith("_")`; the flag became a dict entry |
| `TimeFrame.getname(tframe)` crashed on its own default | `compression=None` reached `None > 1` |
| `filters.CalendarDays` unusable with its documented default | `fill_price=None` reached `> 0` before the branch that handles None |
| ~740k warnings per test run | `\*` in two docstrings (SyntaxWarning) and `datetime.utcnow()` (DeprecationWarning) |
