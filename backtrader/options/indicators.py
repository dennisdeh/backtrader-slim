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
"""Implied volatility and greeks of an option, bar by bar."""

import bisect
import math

from ..indicator import Indicator
from ..utils import num2date
from . import pricing

__all__ = ["OptionGreeks"]

_NAN = float("nan")


class OptionGreeks(Indicator):
    """Implied volatility and greeks of an option feed against its underlying.

    ``OptionGreeks(option, underlying)``: the option feed (one carrying a
    ``contract``) first, the underlying's feed second. Each bar the option's
    price is inverted into an implied volatility, and the greeks follow from
    that volatility.

    Lines, in the units a broker screen uses:

      - ``iv``: implied volatility, as a fraction (0.20)
      - ``delta``, ``gamma``: per unit of the underlying
      - ``vega``: price change per volatility point (0.20 -> 0.21)
      - ``theta``: price change per calendar day

    Every line is per unit of the underlying; multiply by the contract's
    multiplier for a contract. A price no volatility can produce (below
    intrinsic value, for instance) gives NaN on every line, and so does
    expiry day, when no time value is left to imply anything from.

    Params:

      - ``rate`` (def: ``0.0``): continuously compounded risk-free rate
      - ``dividend`` (def: ``0.0``): continuous dividend yield
      - ``model`` (def: ``"bsm"``): ``"bsm"`` (European, also used for
        American options without early exercise) or ``"black76"`` (the
        underlying is a futures price)
      - ``price`` (def: ``"close"``): ``"close"`` or ``"mid"`` (bid/ask
        midpoint, the close where either is missing)
    """

    lines = ("iv", "delta", "gamma", "vega", "theta")
    params = (
        ("rate", 0.0),
        ("dividend", 0.0),
        ("model", "bsm"),
        ("price", "close"),
    )
    plotinfo = dict(subplot=True)
    plotlines = dict(iv=dict(_name="IV"))

    def __init__(self):
        if getattr(self.data0, "contract", None) is None:
            raise ValueError("OptionGreeks needs the option feed first")
        if self.p.model not in ("bsm", "black76"):
            raise ValueError(f"model is 'bsm' or 'black76', not {self.p.model!r}")
        if self.p.price not in ("close", "mid"):
            raise ValueError(f"price is 'close' or 'mid', not {self.p.price!r}")

    def _greeks(self, dtnum, S, P):
        c = (
            self.data0.contract
        )  # read each bar: a model feed sets its strike at listing
        T = c.years_to_expiry(num2date(dtnum))
        r, q = self.p.rate, self.p.dividend
        if self.p.model == "black76":
            iv = pricing.implied_vol(P, c.right, S, c.strike, T, r, model="black76")
            if iv != iv:
                return (_NAN,) * 5
            g = pricing.black76(c.right, S, c.strike, T, r, iv)
        else:
            iv = pricing.implied_vol(P, c.right, S, c.strike, T, r, q)
            if iv != iv:
                return (_NAN,) * 5
            g = pricing.bsm(c.right, S, c.strike, T, r, iv, q)
        return iv, g.delta, g.gamma, g.vega / 100.0, g.theta / 365.0

    @staticmethod
    def _mid(bid, ask, close):
        if math.isfinite(bid) and math.isfinite(ask):
            return 0.5 * (bid + ask)
        return close

    def _price(self, i=None):
        d = self.data0
        if i is None:  # next(): the current bar
            if self.p.price == "mid":
                return self._mid(d.bid[0], d.ask[0], d.close[0])
            return d.close[0]
        if self.p.price == "mid":
            return self._mid(d.bid.array[i], d.ask.array[i], d.close.array[i])
        return d.close.array[i]

    def next(self):
        if not len(self.data1):
            values = (_NAN,) * 5
        else:
            values = self._greeks(
                self.data0.datetime[0], self.data1.close[0], self._price()
            )
        for line, value in zip(self.lines, values):
            line[0] = value

    def once(self, start, end):
        odt = self.data0.datetime.array
        udt = self.data1.datetime.array
        uclose = self.data1.close.array
        out = [line.array for line in self.lines]
        for i in range(start, end):
            # the underlying's last bar at or before this option bar: the
            # two feeds need not start on the same day
            j = bisect.bisect_right(udt, odt[i]) - 1
            if j < 0:
                values = (_NAN,) * 5
            else:
                values = self._greeks(odt[i], uclose[j], self._price(i))
            for arr, value in zip(out, values):
                arr[i] = value
