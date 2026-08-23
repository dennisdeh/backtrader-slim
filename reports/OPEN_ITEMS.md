# Open items

Places where the code does something other than what it should. Fixed entries
move out of this file; things that turn out to be deliberate move to
`DECISIONS.md`.

*Last updated: 2026-08-23*

## Open

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
