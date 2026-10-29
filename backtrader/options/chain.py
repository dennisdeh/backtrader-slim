#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2026 Dennis Hansen
#
# This file is part of slim-backtrader, a modified version of backtrader
# (Copyright (C) 2015-2023 Daniel Rodriguez).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
"""Whole option chains, without a data feed per contract.

``OptionChain`` holds one underlying's chain for the current bar, as columns,
and hands a strategy ``ContractView``s of the contracts it picks. A view is
what the broker, orders, trades, margin, settlement and analyzers need of a
data feed (prices ``[ago]``, ``datetime``, a name, a contract) and nothing
more: only the contracts actually traded or watched cost anything per bar.

The chain is read lazily: on first use in a bar, it loads that day's
snapshot from its source and moves its views on. That is why it works the
same preloaded or not, and needs no clock of its own beyond its underlying.

Sources, all yielding one snapshot per day:

  - ``PandasChainSource``: a DataFrame of daily chains, sliced by day with
    numpy. The fast path, for real data.
  - ``CSVChainSource``: the same columns from a CSV file sorted by date,
    streamed with the standard library: no pandas needed, but slow.
  - ``ModelChainSource``: a strike grid on standard monthly expiries, priced
    from the underlying (as ``ModelOptionData`` prices one contract).

numpy is needed (``pip install slim-backtrader[options]``); it is imported
only when a chain is built.
"""

import bisect
import collections
import csv
import datetime
import math

from ..utils import date2num, num2date
from . import pricing
from .contract import OptionContract

__all__ = [
    "OptionChain",
    "ContractView",
    "PandasChainSource",
    "CSVChainSource",
    "PartitionedChainSource",
    "ModelChainSource",
]

_HISTORY = 5  # bars of prices a view keeps: [0] back to [-4]
_SQRT2 = math.sqrt(2.0)


def _numpy():
    try:
        import numpy
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError(
            "option chains need numpy: pip install slim-backtrader[options]"
        ) from e
    return numpy


def _key(ordinal, strike, iscall):
    """One integer per contract: expiry, strike to 1/1000, right."""
    return (int(ordinal) << 40) | (int(round(strike * 1000.0)) << 1) | int(iscall)


def _keys(np, expiry, strike, iscall):
    keys = (np.asarray(expiry, dtype=np.int64) << 40) | (
        np.rint(np.asarray(strike) * 1000.0).astype(np.int64) << 1
    )
    return keys | np.asarray(iscall, dtype=np.int64)


def third_friday(year, month):
    day = datetime.date(year, month, 15)
    return day + datetime.timedelta(days=(4 - day.weekday()) % 7)


class Snapshot:
    """One day's chain as columns sorted by contract key."""

    FIELDS = ("expiry", "strike", "iscall", "bid", "ask", "mark")

    def __init__(self, day, expiry, strike, iscall, bid, ask, mark, keys=None):
        """``keys``, if given, are the rows' contract keys, already sorted:
        a source that sorts once up front saves a sort per day."""
        np = _numpy()
        self.day = day
        expiry = np.asarray(expiry, dtype=np.int64)
        strike = np.asarray(strike, dtype=float)
        iscall = np.asarray(iscall, dtype=bool)
        bid = np.asarray(bid, dtype=float)
        ask = np.asarray(ask, dtype=float)
        mark = np.asarray(mark, dtype=float)
        if keys is None:
            keys = _keys(np, expiry, strike, iscall)
            order = np.argsort(keys, kind="stable")
            keys, expiry, strike, iscall = (
                x[order] for x in (keys, expiry, strike, iscall)
            )
            bid, ask, mark = (x[order] for x in (bid, ask, mark))
        self.keys, self.expiry, self.strike, self.iscall = keys, expiry, strike, iscall
        self.bid, self.ask = bid, ask
        # no mark given: the mid
        self.mark = np.where(np.isfinite(mark), mark, 0.5 * (bid + ask))

    def __len__(self):
        return len(self.keys)

    def find(self, key):
        i = int(self.keys.searchsorted(key))
        return i if i < len(self.keys) and self.keys[i] == key else -1


class _Series:
    """``[ago]`` over a view's last few values, as a line would give."""

    __slots__ = ("_view", "_values")

    def __init__(self, view):
        self._view = view
        self._values = collections.deque(maxlen=_HISTORY)

    def __getitem__(self, ago):
        self._view._chain._sync()
        return self._values[ago - 1]

    def __len__(self):
        return len(self._values)


class _DateSeries(_Series):
    __slots__ = ()

    def date(self, ago=0):
        return self._view.num2date(self[ago]).date()

    def datetime(self, ago=0):
        return self._view.num2date(self[ago])


class ContractView:
    """One contract of a chain, as the broker sees a data feed.

    It has a bar on each day its contract is quoted in the chain; on a day
    it is not, it keeps its last prices and has no new bar, so no order
    fills on it. ``open``, ``high``, ``low`` and ``close`` are all the
    chain's mark (an end-of-day chain has one price a day); ``bid`` and
    ``ask`` are the quote.
    """

    _compensate = None
    MODEL = False

    def __init__(self, chain, contract, key):
        self._chain = chain
        self.contract = contract
        self._key = key
        und = chain.underlying
        self.p = und.p
        self._tz = und._tz
        self._timeframe = und._timeframe
        self._compression = getattr(und, "_compression", 1)
        self._name = (
            f"{contract.underlying} {contract.expiry} "
            f"{contract.strike:g}{contract.right}"
            + (" (model)" if chain.source.MODEL else "")
        )
        self.datetime = _DateSeries(self)
        self.close = _Series(self)
        self.bid = _Series(self)
        self.ask = _Series(self)
        self.lines = self  # quote fills read lines.bid / lines.ask
        self._bars = 0

    # open, high and low are the close: one price a day
    open = high = low = property(lambda self: self.close)

    def __len__(self):
        self._chain._sync()
        return self._bars

    def __repr__(self):
        return f"<ContractView {self._name}>"

    def num2date(self, dt=None, tz=None, naive=True):
        return num2date(self.datetime[0] if dt is None else dt, tz or self._tz, naive)

    def date2num(self, dt):
        if self._tz is not None:
            return date2num(self._tz.localize(dt))
        return date2num(dt)

    def mid(self, ago=0):
        bid, ask = self.bid[ago], self.ask[ago]
        if math.isfinite(bid) and math.isfinite(ask):
            return 0.5 * (bid + ask)
        return self.close[ago]

    def _push(self, dtnum, mark, bid, ask):
        # plain floats: numpy scalars would leak into orders and trades
        self.datetime._values.append(float(dtnum))
        self.close._values.append(float(mark))
        self.bid._values.append(float(bid))
        self.ask._values.append(float(ask))
        self._bars += 1


class OptionChain:
    """One underlying's option chain, day by day, from ``source``.

    ``OptionChain(underlying, source)``: ``underlying`` is that underlying's
    data feed, added to cerebro under the name contracts refer to; add the
    chain with ``cerebro.addchain(chain)`` and reach it in a strategy with
    ``self.getchain(name)``.

    Each bar, the chain's snapshot is that day's chain, quoted at the close.
    ``select`` and ``contract`` return ``ContractView``s to trade like any
    data feed. An order sent today fills on the contract's next quoted bar.

    Params (keywords): ``multiplier`` (def: 100), ``settlement`` (def:
    ``"physical"``) and ``style`` (def: ``"american"``) for every contract,
    ``rate`` and ``dividend`` (def: 0) for selecting by delta.
    """

    def __init__(
        self,
        underlying,
        source,
        multiplier=100.0,
        settlement="physical",
        style="american",
        rate=0.0,
        dividend=0.0,
    ):
        self.underlying = underlying
        self.source = source
        self.multiplier = multiplier
        self.settlement = settlement
        self.style = style
        self.rate = rate
        self.dividend = dividend
        self.name = None
        self.comminfo = None
        self._cerebro = None
        self._views = {}  # key -> ContractView
        self._active = []
        self._synced = None
        self.snapshot = None

    # -- the day's chain ---------------------------------------------------

    def _sync(self):
        und = self.underlying
        if not len(und):
            return
        dtnum = und.datetime[0]
        if dtnum == self._synced:
            return
        self._synced = dtnum
        day = und.datetime.date(0)
        self.snapshot = snap = self.source.read(day, self)
        keep = []
        positions = self._cerebro.broker.positions if self._cerebro else {}
        for view in self._active:
            i = snap.find(view._key)
            if i >= 0:
                view._push(dtnum, snap.mark[i], snap.bid[i], snap.ask[i])
            expired = view.contract.expiry < day
            pos = positions.get(view) if view in positions else None
            if not expired or (pos is not None and pos.size):
                keep.append(view)
        self._active = keep

    def _view(self, ordinal, strike, iscall):
        key = _key(ordinal, strike, iscall)
        view = self._views.get(key)
        if view is None:
            contract = OptionContract(
                self.underlying._name,
                strike,
                datetime.date.fromordinal(int(ordinal)),
                "C" if iscall else "P",
                multiplier=self.multiplier,
                style=self.style,
                settlement=self.settlement,
            )
            view = self._views[key] = ContractView(self, contract, key)
            if self._cerebro is not None and self.comminfo is not None:
                self._cerebro.broker.addcommissioninfo(self.comminfo, name=view._name)
            i = self.snapshot.find(key) if self.snapshot is not None else -1
            if i >= 0:  # quoted today: today is its first bar
                s = self.snapshot
                view._push(self._synced, s.mark[i], s.bid[i], s.ask[i])
            self._active.append(view)
        return view

    def expiries(self):
        """Today's expiries, nearest first."""
        self._sync()
        np = _numpy()
        return [
            datetime.date.fromordinal(int(o)) for o in np.unique(self.snapshot.expiry)
        ]

    def strikes(self, expiry, right):
        """Today's strikes for ``expiry`` and ``right``, lowest first."""
        self._sync()
        s, iscall = self.snapshot, pricing.normalize_right(right) == pricing.CALL
        mask = (s.expiry == expiry.toordinal()) & (s.iscall == iscall)
        return [float(k) for k in s.strike[mask]]

    def contract(self, expiry, strike, right):
        """The view of one contract, or ``None`` if today's chain lacks it."""
        self._sync()
        iscall = pricing.normalize_right(right) == pricing.CALL
        key = _key(expiry.toordinal(), strike, iscall)
        if key not in self._views and self.snapshot.find(key) < 0:
            return None
        return self._view(expiry.toordinal(), strike, iscall)

    def select(self, right, dte=(20, 45), delta=None, moneyness=None):
        """The contract nearest a target, on the nearest expiry whose days to
        expiry fall within ``dte``: by ``delta`` (0.30 for a 30-delta call,
        -0.30 for a put) at each strike's implied volatility, or by
        ``moneyness`` (strike / underlying close). ``None`` if no expiry
        fits. Exactly one of ``delta`` and ``moneyness`` is given."""
        if (delta is None) == (moneyness is None):
            raise ValueError("select by delta or by moneyness: one of them")
        self._sync()
        s = self.snapshot
        day = self.underlying.datetime.date(0)
        iscall = pricing.normalize_right(right) == pricing.CALL
        lo, hi = dte
        today = day.toordinal()
        fits = sorted(o for o in set(int(x) for x in s.expiry) if lo <= o - today <= hi)
        if not fits:
            return None
        ordinal = fits[0]
        mask = (s.expiry == ordinal) & (s.iscall == iscall)
        strikes, marks = s.strike[mask], s.mark[mask]
        if not len(strikes):
            return None
        spot = self.underlying.close[0]
        if moneyness is not None:
            i = int(abs(strikes - spot * moneyness).argmin())
        else:
            T = (ordinal - today) / 365.0
            r, q = self.rate, self.dividend
            best, i = math.inf, -1
            for j, (k, m) in enumerate(zip(strikes, marks)):
                sig = pricing.implied_vol(float(m), right, spot, float(k), T, r, q)
                if sig != sig:
                    continue
                d = pricing.bsm(right, spot, float(k), T, r, sig, q).delta
                if abs(d - delta) < best:
                    best, i = abs(d - delta), j
            if i < 0:
                return None
        return self._view(ordinal, float(strikes[i]), iscall)


# -- sources ---------------------------------------------------------------


class PandasChainSource:
    """Daily chains from a pandas DataFrame, one row per contract per day.

    Columns (renamed with ``columns={"ours": "theirs"}``): ``date``,
    ``expiry``, ``strike``, ``right`` ("C"/"P"), ``bid``, ``ask`` and, if
    present, ``mark`` (else the mid). ``dte=(lo, hi)`` drops rows outside a
    days-to-expiry window once, up front: cutting a chain to what a strategy
    can trade is most of the speed.
    """

    MODEL = False

    def __init__(self, frame, columns=None, dte=None):
        np = _numpy()
        names = dict(
            date="date", expiry="expiry", strike="strike", right="right",
            bid="bid", ask="ask", mark="mark",
        ) | (columns or {})  # fmt: skip
        f = frame
        day = _ordinals(np, f[names["date"]])
        expiry = _ordinals(np, f[names["expiry"]])
        rights = f[names["right"]]
        if rights.dtype == bool:
            iscall = rights.to_numpy()
        else:  # a hash lookup: string methods cost a microsecond a row
            iscall = rights.isin(["C", "c", "CALL", "Call", "call"]).to_numpy()
        mark = f[names["mark"]] if names["mark"] in f else np.full(len(f), np.nan)
        cols = dict(
            day=day,
            expiry=expiry,
            strike=f[names["strike"]].to_numpy(dtype=float),
            iscall=iscall,
            bid=f[names["bid"]].to_numpy(dtype=float),
            ask=f[names["ask"]].to_numpy(dtype=float),
            mark=np.asarray(mark, dtype=float),
        )
        keep = np.ones(len(day), dtype=bool)
        if dte is not None:
            left = cols["expiry"] - day
            keep = (left >= dte[0]) & (left <= dte[1])
        cols = {k: v[keep] for k, v in cols.items()}
        cols["keys"] = _keys(np, cols["expiry"], cols["strike"], cols["iscall"])
        order = np.lexsort((cols["keys"], cols["day"]))  # by day, then contract
        self._cols = {k: v[order] for k, v in cols.items()}
        self._days = self._cols["day"]

    def read(self, day, chain):
        np = _numpy()
        o = day.toordinal()
        a = int(np.searchsorted(self._days, o, "left"))
        b = int(np.searchsorted(self._days, o, "right"))
        c = self._cols
        return Snapshot(
            day,
            *(c[k][a:b] for k in Snapshot.FIELDS),
            keys=c["keys"][a:b],
        )


class PartitionedChainSource:
    """Daily chains loaded one period at a time: ``load(period)`` returns
    the DataFrame for that period (a year, or a ``(year, month)``), and the
    previous period's is dropped when the next is loaded.

    Ten years of full chains for hundreds of underlyings do not fit in
    memory at once; a year or a month of one underlying does. ``load``
    typically reads one file per underlying and period. Other keywords are
    ``PandasChainSource``'s.
    """

    MODEL = False

    def __init__(self, load, period="year", **kwargs):
        if period not in ("year", "month"):
            raise ValueError(f"period is 'year' or 'month', not {period!r}")
        self.load = load
        self.period = period
        self.kwargs = kwargs
        self._key = None
        self._source = None

    def read(self, day, chain):
        key = day.year if self.period == "year" else (day.year, day.month)
        if key != self._key:
            self._key = key
            self._source = None  # drop the last period before loading the next
            frame = self.load(key)
            if frame is not None and len(frame):
                self._source = PandasChainSource(frame, **self.kwargs)
        if self._source is None:
            np = _numpy()
            empty = np.empty(0)
            return Snapshot(day, empty, empty, empty, empty, empty, empty)
        return self._source.read(day, chain)


_EPOCH_ORDINAL = datetime.date(1970, 1, 1).toordinal()


_PER_DAY = dict(D=1, h=24, m=1440, s=86400, ms=86_400_000, us=86_400_000_000)
_PER_DAY["ns"] = 86_400_000_000_000


def _ordinals(np, column):
    """Proleptic ordinals of a column of dates, without a Python loop: a
    chain has millions of rows. Integer division of the raw datetimes is
    ~20 times faster than numpy's unit conversion."""
    values = column.to_numpy()
    if not np.issubdtype(values.dtype, np.datetime64):
        import pandas

        values = pandas.to_datetime(column).to_numpy()
    unit, count = np.datetime_data(values.dtype)
    days = values.view(np.int64) // (_PER_DAY[unit] // count)
    return days + _EPOCH_ORDINAL


class CSVChainSource:
    """Daily chains from a CSV file sorted by date, streamed row by row with
    the standard library. Same columns as ``PandasChainSource``, ISO dates.
    Easy to start with and slow: for big chains, use pandas."""

    MODEL = False

    def __init__(self, path, columns=None, dte=None):
        self.path = path
        self.names = dict(
            date="date", expiry="expiry", strike="strike", right="right",
            bid="bid", ask="ask", mark="mark",
        ) | (columns or {})  # fmt: skip
        self.dte = dte
        self._rows = None
        self._next = None

    def _open(self):
        self._file = open(self.path, newline="")
        self._rows = csv.DictReader(self._file)
        self._next = next(self._rows, None)

    def read(self, day, chain):
        if self._rows is None:
            self._open()
        n, iso = self.names, day.isoformat()
        cols = {k: [] for k in Snapshot.FIELDS}
        while self._next is not None and self._next[n["date"]][:10] <= iso:
            row, self._next = self._next, next(self._rows, None)
            if self._next is None:
                self._file.close()  # read to the end
            if row[n["date"]][:10] < iso:
                continue  # a day the underlying did not trade
            expiry = datetime.date.fromisoformat(row[n["expiry"]][:10])
            if self.dte is not None:
                left = (expiry - day).days
                if not self.dte[0] <= left <= self.dte[1]:
                    continue
            cols["expiry"].append(expiry.toordinal())
            cols["strike"].append(float(row[n["strike"]]))
            cols["iscall"].append(row[n["right"]].strip().upper().startswith("C"))
            cols["bid"].append(float(row[n["bid"]] or "nan"))
            cols["ask"].append(float(row[n["ask"]] or "nan"))
            cols["mark"].append(float(row.get(n["mark"]) or "nan"))
        return Snapshot(day, *(cols[k] for k in Snapshot.FIELDS))


class ModelChainSource:
    """A chain priced by a model from the underlying, for research without
    option data: strikes every ``strikestep`` within ``width`` (a fraction)
    of the previous close, on the next ``months`` monthly expiries (third
    Fridays), at the underlying's realised volatility up to the previous
    close (or a constant ``vol``), with bid/ask ``spread`` (a fraction of
    the price) around the model price. Contracts a strategy holds stay
    priced after the market moves away from them."""

    MODEL = True

    def __init__(
        self,
        strikestep=5.0,
        width=0.20,
        months=3,
        vol="realized",
        volwindow=21,
        vol0=0.20,
        rate=0.0,
        dividend=0.0,
        spread=0.0,
    ):
        self.strikestep = strikestep
        self.width = width
        self.months = months
        self.vol = vol
        self.volwindow = volwindow
        self.vol0 = vol0
        self.rate = rate
        self.dividend = dividend
        self.spread = spread

    def _sigma(self, und):
        if self.vol != "realized":
            return float(self.vol)
        n = min(len(und) - 1, self.volwindow + 1)  # closes before today
        if n <= 5:
            return self.vol0
        closes = [und.close[-k] for k in range(n, 0, -1)]
        rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
        mean = sum(rets) / len(rets)
        var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
        return math.sqrt(var * 252)

    def read(self, day, chain):
        np = _numpy()
        und = chain.underlying
        spot = und.close[0]
        ref = und.close[-1] if len(und) > 1 else spot
        sigma = self._sigma(und)

        expiries, y, m = [], day.year, day.month
        while len(expiries) < self.months:
            tf = third_friday(y, m)
            if tf >= day:
                expiries.append(tf.toordinal())
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)

        step = self.strikestep
        lo = math.ceil(ref * (1 - self.width) / step) * step
        hi = math.floor(ref * (1 + self.width) / step) * step
        grid = np.arange(lo, hi + step / 2, step)
        e, k, c = np.meshgrid(
            np.array(expiries), grid, np.array([False, True]), indexing="ij"
        )
        exp, strike, iscall = e.ravel(), k.ravel(), c.ravel()
        # contracts still held or watched keep a price off the grid
        today = day.toordinal()
        extra = [
            v.contract for v in chain._active if v.contract.expiry.toordinal() >= today
        ]
        if extra:
            exp = np.concatenate([exp, [x.expiry.toordinal() for x in extra]])
            strike = np.concatenate([strike, [x.strike for x in extra]])
            iscall = np.concatenate([iscall, [x.iscall for x in extra]])

        price = _bsm_prices(
            np,
            spot,
            strike,
            (exp - today) / 365.0,
            iscall,
            sigma,
            self.rate,
            self.dividend,
        )
        half = 0.5 * self.spread * price
        snap = Snapshot(
            day, exp, strike, iscall, np.maximum(price - half, 0.0), price + half, price
        )
        _, first = np.unique(snap.keys, return_index=True)  # drop repeats
        if len(first) < len(snap):
            for name in ("keys",) + Snapshot.FIELDS:
                setattr(snap, name, getattr(snap, name)[first])
        return snap


def _bsm_prices(np, S, K, T, iscall, sigma, r, q):
    """Black-Scholes prices for arrays of strikes, times and rights."""
    erf = np.frompyfunc(math.erf, 1, 1)

    def cdf(x):
        return 0.5 * (1.0 + erf(x / _SQRT2).astype(float))

    phi = np.where(iscall, 1.0, -1.0)
    intrinsic = np.maximum(phi * (S - K), 0.0)
    live = T > 0
    Tl = np.where(live, T, 1.0)
    sq = sigma * np.sqrt(Tl)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * Tl) / sq
    d2 = d1 - sq
    value = phi * (
        S * np.exp(-q * Tl) * cdf(phi * d1) - K * np.exp(-r * Tl) * cdf(phi * d2)
    )
    return np.where(live, np.maximum(value, 0.0), intrinsic)
