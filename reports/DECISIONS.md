# Decisions

Things that were examined and found to be correct, deliberate, or the lesser
evil. Do not re-open these without new evidence.

*Last updated: 2026-08-23*

## Upstream is dormant, and this fork already contains all of it

*2026-08-23*

Checked on 2026-08-23, after a request to pull new upstream commits: **there
are none, and there is nothing to merge.**

`mementum/backtrader` last received a commit on **2023-04-19** (`b853d7c`,
"Version 1.9.78.123"). That is the tip of both `master` and `development`. The
three other branches are older still - `fix-compression` 2018-10-10,
`merge_memento_backtrader` 2020-07-06, `numpylines` 2017-02-19 - and upstream
never merged them. The repository is not archived; it is simply inactive.

More importantly, the fork is **content-identical** to that tip. Our history
diverged from upstream's at `8ee132c` (2018-01-25) and re-applied the same work
on parallel commits, so `git log master..upstream/master` prints 165 commits
that look missing and are not: `git diff upstream/master 2a64c42` is **empty**,
byte for byte, and `2a64c42` is an ancestor of `master`. Everything after it on
`master` is this fork's own work.

The `git log` commit count is therefore the wrong instrument here and will
mislead the next reader too. Compare trees, not commit lists:

```shell
git fetch upstream
git diff upstream/master 2a64c42     # empty == fully in sync
```

`upstream` (`https://github.com/mementum/backtrader.git`) is now a configured
remote so this check costs one command. Do not re-open the question without
first seeing that diff come back non-empty.

## Distribution `slim-backtrader`, import `backtrader`

*2026-08-23*

The PyPI name `backtrader` belongs to upstream (checked 2026-08-23: the JSON
API returns 200), and a name on PyPI is never reusable — not even after the
project owning it is deleted. The fork therefore publishes as
`slim-backtrader`, which was free on the same date.

The **import** package deliberately stays `backtrader`, so `import backtrader
as bt` keeps working and no strategy code has to move. The accepted cost: this
fork and upstream cannot be installed into the same environment, because both
own the top-level `backtrader` module. Renaming the import package would
remove that clash and was rejected — it is a far larger API break than a
packaging change should carry, and it would break every consumer for the
benefit of a side-by-side install nobody has asked for.

Do not "fix" the clash by renaming the import package without that request
arriving first. See `reports/sessions/2026-08-23_pypi-packaging.md`.

## Removing the live-trading integrations

*2026-08-22*

Interactive Brokers, VisualChart and Oanda were removed wholesale, along with
the blaze, InfluxDB and Quandl feeds and the pyfolio analyzer. The decision was
made on dependency evidence, not on taste — each one requires a package that
cannot be installed or used on Python 3.13:

| removed | required | state |
|---|---|---|
| IB store/broker/feed | `ib.opt`, `ib.ext` (IbPy) | Python 2 only, unmaintained |
| VisualChart store/broker/feed | `comtypes`, `_winreg` | `_winreg` is the Python 2 spelling; the product is retired; Windows only |
| Oanda store/broker/feed | `oandapy` | unmaintained; REST v1 discontinued by Oanda |
| blaze feed | `blaze` | no release since 2016 |
| InfluxDB feed | `influxdb` 1.x client | the 1.x server line is end-of-life |
| Quandl feed | quandl.com HTTP API | retired into Nasdaq Data Link |
| pyfolio analyzer | `pyfolio` | abandoned; already marked deprecated upstream |

They had been imported under `try: ... except ImportError: pass`, so they were
silently absent for years rather than failing loudly. That pattern is why the
rot went unnoticed, and it is not reintroduced: what remains either has no
dependency at all or imports it lazily with a clear error message.

The VisualChart *file* readers (`vchart`, `vchartcsv`) went with the rest of
the family even though they had no dependency — they read files produced by a
product that no longer ships.

## Keeping the CSV feeds that have no dependencies

*2026-08-22*

`SierraChartCSVData` and `MT4CSVData` are four-line subclasses of
`GenericCSVData`. They cost nothing, work offline and cannot rot, so "slim
down" does not apply to them.

## Keeping the TA-Lib bindings

*2026-08-22*

`backtrader/talib.py` is 3% covered and imports `talib`, but TA-Lib is alive and
maintained, and the import is lazy. It stays, behind the `talib` extra.

## Plotting stays non-interactive

*2026-08-22*

`plotter.show()` is commented out and the matplotlib backend is forced to `Agg`
(`MacOSX` on darwin) — a deliberate change made before this work
(commit `ea3d0d3`). `cerebro.plot()` returning figures without opening a window
is the intended behaviour. Tests render through it, which is why plotting could
be covered at all.

## AnnualReturn's dependency on the Broker observer

*2026-08-22*

`AnnualReturn` reads `strategy.stats.broker` and therefore raises
`AttributeError` under `stdstats=False`. Its own source says "Must have
stats.broker". Left as it is — changing it would alter the analyzer's contract
— but now pinned by a test so the coupling is visible rather than surprising.

## `todate` excludes a daily bar stamped at the session end

*2026-08-22*

A daily bar carries `23:59:59.999` as its time, so `todate=datetime(2006, 6, 30)`
excludes 2006-06-30. This looks like an off-by-one when splitting a feed on a
date boundary; it is the documented consequence of session-end stamping.
Pinned by `test_todate_excludes_a_bar_stamped_at_the_session_end`.
