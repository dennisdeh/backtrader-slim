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
"""Looking at an options book as a whole: its greeks, and its structures."""

import collections

from ..analyzer import Analyzer
from ..observer import Observer
from . import pricing

__all__ = ["PortfolioGreeks", "StructureTrades"]


class PortfolioGreeks(Observer):
    """The greeks of everything the broker holds, summed every bar, in money.

    Each option position's greeks come from Black-Scholes at the volatility
    its own close implies; a position in an underlying counts as its delta.
    The lines are in currency, so positions on different underlyings add up:

      - ``delta``: exposure; a 1% move in every underlying changes the
        value by about ``delta / 100``
      - ``gamma``: how much ``delta`` changes on a 1% move
      - ``vega``: value change per volatility point (0.20 -> 0.21)
      - ``theta``: value change per calendar day

    Params: ``rate`` and ``dividend`` (continuous, def: ``0.0``).
    """

    lines = ("delta", "gamma", "vega", "theta")
    params = (("rate", 0.0), ("dividend", 0.0))
    plotinfo = dict(plot=True, subplot=True, plotname="Portfolio greeks")

    def next(self):
        strategy = self._owner
        byname = strategy.cerebro.datasbyname
        total = [0.0, 0.0, 0.0, 0.0]
        for data, pos in strategy.broker.positions.items():
            if not pos.size or not len(data):
                continue
            c = getattr(data, "contract", None)
            if c is None:
                total[0] += pos.size * data.close[0]
                continue
            und = byname.get(c.underlying)
            if und is None or not len(und):
                continue
            S, price = und.close[0], data.close[0]
            T = c.years_to_expiry(data.datetime.date(0))
            r, q = self.p.rate, self.p.dividend
            sigma = pricing.implied_vol(price, c.right, S, c.strike, T, r, q)
            if sigma != sigma:  # nothing to imply: price it on its intrinsic value
                sigma = 0.0
            g = pricing.bsm(c.right, S, c.strike, T, r, sigma, q)
            units = pos.size * c.multiplier
            total[0] += units * g.delta * S
            total[1] += units * g.gamma * S * S / 100.0
            total[2] += units * g.vega / 100.0
            total[3] += units * g.theta / 365.0
        for line, value in zip(self.lines, total):
            line[0] = value


class StructureTrades(Analyzer):
    """Profit and loss per structure: per combo order, not per leg.

    A structure starts with a ``combo`` order. Every later fill on one of
    its feeds belongs to it - a leg closed on its own, an expiry settlement,
    the underlying delivered by an exercise - until every leg is flat again.

    ``get_analysis()`` maps each combo's reference to a dict:

      - ``legs``: the feed names traded
      - ``opened``, ``closed`` (``None`` while open): dates
      - ``bars``: bars from opening to closing (or to the end)
      - ``pnl``: cash in less cash out, commissions included, plus the
        value of what is still held
      - ``worst``, ``best``: the lowest and highest marked-to-market
        ``pnl`` while it was open: how far it went against, and for, the
        strategy
    """

    def start(self):
        super().start()
        self._open = {}

    def _owner_of(self, data):
        for ref in reversed(self._open):
            if data in self._open[ref]["qty"]:
                return ref
        return None

    def _mark(self, s):
        broker = self.strategy.broker
        value = sum(
            broker.getcommissioninfo(d).getvaluesize(q, d.close[0])
            for d, q in s["qty"].items()
            if q
        )
        return s["cash"] + value

    def notify_order(self, order):
        if order.status != order.Completed:
            return
        ref = order.info.get("combo")
        if ref is None:
            data = order.data
            if order.info.get("settlement") == "delivery":
                data = self.strategy.getdatabyname(order.info.option)
            ref = self._owner_of(data)
            if ref is None:
                return  # not part of any structure
        s = self._open.get(ref)
        if s is None:
            s = self._open[ref] = dict(
                qty=collections.defaultdict(float),
                cash=0.0,
                opened=self.strategy.datetime.date(0),
                start=len(self.strategy),
                worst=0.0,
                best=0.0,
            )
        broker = self.strategy.broker
        ex = order.executed
        s["qty"][order.data] += ex.size
        s["cash"] -= broker.getcommissioninfo(order.data).getvaluesize(
            ex.size, ex.price
        )
        s["cash"] -= ex.comm
        if all(abs(q) < 1e-9 for q in s["qty"].values()):
            self._record(
                ref, self._open.pop(ref), closed=self.strategy.datetime.date(0)
            )

    def next(self):
        for s in self._open.values():
            mark = self._mark(s)
            s["worst"] = min(s["worst"], mark)
            s["best"] = max(s["best"], mark)

    def stop(self):
        for ref, s in list(self._open.items()):
            self._record(ref, s, closed=None)

    def _record(self, ref, s, closed):
        pnl = s["cash"] if closed is not None else self._mark(s)
        self.rets[ref] = dict(
            legs=[d._name for d in s["qty"]],
            opened=s["opened"],
            closed=closed,
            bars=len(self.strategy) - s["start"],
            pnl=pnl,
            worst=min(s["worst"], pnl),
            best=max(s["best"], pnl),
        )
