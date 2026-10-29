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
"""Option prices from a pricing model, for research without option data."""

import collections
import dataclasses
import datetime
import math
import statistics

from ..feed import DataClone
from . import pricing
from .feeds import _OptionFeed

__all__ = ["ModelOptionData"]


class ModelOptionData(DataClone, _OptionFeed):
    """An option feed priced by a model from its underlying's bars.

    ``ModelOptionData(dataname=underlying, contract=...)`` follows the
    underlying's feed bar by bar, as resampling does, and turns each bar's
    open, high, low and close into the option's, with ``model`` at
    volatility ``vol``. Add the underlying to cerebro first, then this feed
    with ``cerebro.addoption``.

    The volatility a bar is priced at is known before that bar opens: a
    constant, or the realised volatility of the underlying's closes up to the
    previous bar. The bar's own move does not leak into its prices.

    Model prices are not market prices: no skew, no term structure, and a
    spread only as wide as ``spread`` says. Results are optimistic for
    strategies that sell options. The default name ``addoption`` gives this
    feed ends in "(model)" so that no report mistakes it for market data.

    Params:

      - ``contract``: the ``OptionContract``. Its ``underlying`` must be the
        name the ``dataname`` feed was added under.
      - ``vol`` (def: ``"realized"``): a constant volatility (0.20), or
        ``"realized"``.
      - ``volwindow`` (def: ``21``): returns in the realised estimate.
      - ``vol0`` (def: ``0.20``): the volatility used until ``volmin``
        returns exist.
      - ``volmin`` (def: ``5``): returns needed before the realised
        estimate is used.
      - ``annualize`` (def: ``252``): bars per year, for the realised
        estimate (252 for daily bars).
      - ``rate``, ``dividend`` (def: ``0.0``): continuously compounded.
      - ``model`` (def: ``"bsm"``): ``"bsm"``, ``"black76"`` (the underlying
        is a futures price) or ``"binomial"`` (an American option on a CRR
        tree of ``steps`` steps).
      - ``listing`` (def: ``None``): the first date the contract trades;
        ``None`` is the underlying's first bar.
      - ``moneyness`` (def: ``None``): if set, the strike is fixed at listing
        as the previous close times ``moneyness`` (0.95: 5% below),
        rounded to ``strikestep``. The contract's own strike is replaced.
      - ``spread`` (def: ``0.0``): bid/ask width as a fraction of the
        price; ``bid`` and ``ask`` sit half of it either side of the close.
    """

    MODEL = True

    lines = ("bid", "ask")
    params = (
        ("contract", None),
        ("vol", "realized"),
        ("volwindow", 21),
        ("vol0", 0.20),
        ("volmin", 5),
        ("annualize", 252),
        ("rate", 0.0),
        ("dividend", 0.0),
        ("model", "bsm"),
        ("steps", 100),
        ("listing", None),
        ("moneyness", None),
        ("strikestep", 1.0),
        ("spread", 0.0),
    )

    def __init__(self):
        super().__init__()  # DataClone: follow self.p.dataname
        self._checkcontract()
        vol = self.p.vol
        if vol != "realized" and not (isinstance(vol, (int, float)) and vol > 0):
            raise ValueError(f"vol is a positive number or 'realized', not {vol!r}")
        if self.p.model not in ("bsm", "black76", "binomial"):
            raise ValueError(
                f"model is 'bsm', 'black76' or 'binomial', not {self.p.model!r}"
            )
        listing = self.p.listing
        if isinstance(listing, str):
            listing = datetime.date.fromisoformat(listing)
        elif isinstance(listing, datetime.datetime):
            listing = listing.date()
        self._listing = listing
        self._contract0 = self.p.contract

    def start(self):
        super().start()
        env = getattr(self, "_env", None)
        if self.data._name != self._contract0.underlying:
            raise ValueError(
                f"the contract's underlying is {self._contract0.underlying!r}, "
                f"but this feed follows {self.data._name!r}"
            )
        if env is not None:
            # by identity: == between two feeds builds a comparison line
            order = [id(d) for d in env.datas]
            if order.index(id(self.data)) > order.index(id(self)):
                raise ValueError(
                    "add the underlying to cerebro before its model option"
                )
        self.p.contract = self._contract0
        self._closes = collections.deque(maxlen=self.p.volwindow + 1)
        self._listed = False

    def _volatility(self):
        """The volatility known before the current bar: from closes up to
        the previous one."""
        if self.p.vol != "realized":
            return float(self.p.vol)
        closes = self._closes
        if len(closes) <= self.p.volmin:
            return self.p.vol0
        rets = [math.log(b / a) for a, b in zip(closes, list(closes)[1:])]
        return statistics.stdev(rets) * math.sqrt(self.p.annualize)

    def _price(self, S, T, sigma):
        c, p = self.p.contract, self.p
        if p.model == "black76":
            return pricing.black76(c.right, S, c.strike, T, p.rate, sigma).price
        if p.model == "binomial":
            return pricing.binomial(
                c.right, S, c.strike, T, p.rate, sigma, p.dividend, steps=p.steps
            )
        return pricing.bsm(c.right, S, c.strike, T, p.rate, sigma, p.dividend).price

    def _list(self, prevclose, bar_open):
        if self.p.moneyness is not None:
            ref = prevclose if prevclose is not None else bar_open
            step = self.p.strikestep
            strike = round(ref * self.p.moneyness / step) * step
            self.p.contract = dataclasses.replace(self._contract0, strike=strike)
        self._listed = True

    def _load(self):
        while True:
            if self._preloading:
                self.data.advance()
                if len(self.data) > self.data.buflen():
                    return False
            else:
                if not (len(self.data) > self._dlen):
                    return False
                self._dlen += 1

            d = self.data
            day = d.datetime.date(0)
            sigma = self._volatility()
            prevclose = self._closes[-1] if self._closes else None
            self._closes.append(d.close[0])

            if self._listing is not None and day < self._listing:
                continue
            contract = self.p.contract
            if day > contract.expiry:
                return False
            if not self._listed:
                self._list(prevclose, d.open[0])

            T = self.p.contract.years_to_expiry(day)
            o, h, l, c = (
                self._price(x, T, sigma)
                for x in (d.open[0], d.high[0], d.low[0], d.close[0])
            )
            self.lines.datetime[0] = d.datetime[0]
            self.lines.open[0] = o
            self.lines.high[0] = max(o, h, l, c)
            self.lines.low[0] = min(o, h, l, c)
            self.lines.close[0] = c
            self.lines.volume[0] = 0.0
            self.lines.openinterest[0] = 0.0
            half = 0.5 * self.p.spread * c
            self.lines.bid[0] = max(c - half, 0.0)
            self.lines.ask[0] = c + half
            return True
