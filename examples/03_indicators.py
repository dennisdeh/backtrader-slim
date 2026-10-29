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
"""Indicators: the built-in ones, arithmetic on lines, and writing your own.

- There are over 120 built-in indicators in ``bt.indicators`` (alias
  ``bt.ind``), each under several names (``SMA`` is
  ``SimpleMovingAverage``).
- Lines combine with ordinary operators, and the result is itself a line:
  ``self.data.close - sma`` is computed for every bar, not once.
- A custom indicator declares its ``lines`` and ``params`` and fills them in
  ``next()``. Optionally, ``once()`` computes all bars at once, which is what
  runs by default (``runonce=True``) and is faster.
- No indicator says when it becomes valid: the engine works it out (the
  "minimum period") from what it uses.

Run it:  python examples/03_indicators.py [--plot]
"""

import sys
from pathlib import Path

import backtrader as bt

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"


class DistanceFromMean(bt.Indicator):
    """How far the close is from its moving average, in standard deviations
    (a z-score)."""

    lines = ("zscore",)
    params = (("period", 20),)
    plotinfo = dict(subplot=True)
    plotlines = dict(zscore=dict(_plotskip=False))

    def __init__(self):
        # Built from other lines: no next() needed, and the minimum period
        # (20 bars) follows from the two indicators it uses.
        mean = bt.ind.SMA(self.data.close, period=self.p.period)
        std = bt.ind.StdDev(self.data.close, period=self.p.period)
        self.lines.zscore = (self.data.close - mean) / std


class UpDays(bt.Indicator):
    """Up days among the last ``period`` bars, written bar by bar."""

    lines = ("updays",)
    params = (("period", 10),)

    def __init__(self):
        # next() looks one bar back, so it needs period + 1 bars
        self.addminperiod(self.p.period + 1)

    def next(self):
        closes = self.data.close.get(size=self.p.period + 1)
        self.lines.updays[0] = sum(b > a for a, b in zip(closes, closes[1:]))

    def once(self, start, end):
        # the same computation over the whole array at once
        close, out, n = self.data.close.array, self.lines.updays.array, self.p.period
        for i in range(start, end):
            window = close[i - n : i + 1]
            out[i] = sum(b > a for a, b in zip(window, window[1:]))


class Show(bt.Strategy):
    def __init__(self):
        self.rsi = bt.ind.RSI(period=14)
        self.macd = bt.ind.MACD()
        self.boll = bt.ind.BollingerBands(period=20, devfactor=2.0)
        self.z = DistanceFromMean()
        self.up = UpDays()
        # arithmetic and comparisons produce lines too
        self.above_band = self.data.close > self.boll.lines.top

    def nextstart(self):
        print(f"first bar with every indicator ready: bar {len(self)}")
        self.next()

    def stop(self):
        print(
            f"last bar {self.data.datetime.date(0)}: "
            f"RSI {self.rsi[0]:.1f}, MACD {self.macd.macd[0]:.2f}, "
            f"z-score {self.z[0]:.2f}, up days {self.up[0]:.0f}/10, "
            f"above the upper band: {bool(self.above_band[0])}"
        )


def main(plot=False):
    for runonce in (True, False):
        cerebro = bt.Cerebro(runonce=runonce, stdstats=False)
        cerebro.adddata(
            bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt"))
        )
        cerebro.addstrategy(Show)
        print(f"runonce={runonce}:")
        cerebro.run()
    if plot:
        cerebro.plot()


if __name__ == "__main__":
    main(plot="--plot" in sys.argv)
