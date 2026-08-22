# Architecture

Which part owns what, and what flows between them.

*Last updated: 2026-08-22*

## The one idea to understand first

Everything in backtrader is a **lines object built by a metaclass**. Indicators,
Strategies, data feeds, Analyzers and Observers all descend from `LineSeries`,
and their class-level declarations are not plain attributes:

```python
class MovingAverageSimple(MovingAverageBase):
    alias = ("SMA", "SimpleMovingAverage")
    lines = ("sma",)
    params = (("period", 30),)
```

`metabase.MetaParams` and `lineseries.MetaLineSeries` turn those into real
machinery at class-creation time: `lines` becomes a generated `Lines` class,
`params` becomes the object reachable as `self.p`, and `alias` registers the
class under several names in `bt.indicators`. Renaming a class silently removes
names from the public namespace without any import error.

Reading `backtrader/metabase.py` and `backtrader/lineseries.py` first makes the
rest of the codebase legible; reading them last makes it look like magic.

## Layers

```
                    Cerebro                     orchestration: owns everything,
                       |                        runs the bar loop, optimises
        +--------------+--------------+
        |              |              |
     Strategy       Broker         DataFeed     the three things a run needs
        |              |              |
   Indicators     CommInfo/Sizer   Filters      per-strategy / per-order /
   Observers        Fillers        Resampler    per-feed collaborators
   Analyzers
```

- **`cerebro.py`** — the entry point. Holds data feeds, strategies, the broker,
  observers, analyzers, writers and timers; drives the bar loop; implements
  `run()`, `optstrategy()`, `resampledata()`, `replaydata()` and `plot()`.
- **`strategy.py`** — user code lives here. Owns positions per data feed,
  issues orders (`buy`/`sell`/`close`/`order_target_*`), receives
  `notify_order`/`notify_trade`/`notify_timer`.
- **`brokers/bbroker.py`** — the simulation broker: cash and value accounting,
  order matching per execution type, margin, interest, slippage and filling.
- **`feed.py` + `feeds/`** — bar production. `feeds/` holds the concrete
  readers; `feed.py` holds the base class and the CSV scaffolding.
- **`resamplerfilter.py`** — turns a fine timeframe into a coarser one
  (`resample`) or replays a coarse bar as it forms (`replay`).
- **`lineiterator.py`, `linebuffer.py`, `lineseries.py`, `lineroot.py`** — the
  line machinery: storage, indexing, minimum-period propagation, and the two
  execution modes.
- **`indicators/`** — 122 indicators, each with a `next()` and usually a
  vectorised `once()`.
- **`analyzers/`, `observers/`, `writer.py`** — read-only consumers of a run.
- **`plot/`** — matplotlib rendering, forced to the `Agg` backend.
- **`btrun/`** — the `btrun` console script, a CLI wrapper over Cerebro.

## Two execution modes

Every indicator is written twice:

- **`next()`** — called once per bar, sees `self.data.close[0]` as the current
  value and `[-1]` as the previous one.
- **`once()`** — called once for the whole range, filling arrays directly. Used
  when `runonce=True` (the default) and the data is preloaded.

A change to one that is not made to the other passes half the test matrix. This
is the single most common way to break an indicator here, which is why
`testcommon.runtest` sweeps both modes plus `preload` and `exactbars`.

## Minimum period

Indicators do not declare when they become valid — it is computed. An SMA(30)
over a data feed reports `minperiod == 30`, and a strategy's `next()` is not
called until every indicator it holds is ready. `nextstart()` fires on the first
valid bar. The golden-value tests assert the computed value (`chkmin`), so a
change in composition shows up immediately.

## Order lifecycle

```
strategy.buy()  ->  Order(Created)  ->  broker.submit()  ->  Submitted
                                                          ->  Accepted
     next bar: broker matches against the bar's OHLC
        filled            -> Completed  -> notify_order, then notify_trade
        not filled        -> stays Accepted (or Expired at `valid`)
        no cash           -> Margin
        cancelled         -> Canceled
```

Market orders execute at the **next** bar's open — the bar after the one the
decision was taken on — unless `cheat_on_open` is set. `order_target_*` sizes
from the close of the decision bar and rounds down to whole units, so the
achieved value undershoots the target by up to one unit.

## What was removed in 2.0.0

The `stores/` package is now empty of implementations: there are no live
integrations in this fork. `brokers/` holds only the simulation broker, and
`feeds/` only the readers that work offline plus Yahoo. See `DECISIONS.md`.
