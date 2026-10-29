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
"""Your first backtest: a data feed, a strategy, a broker, and a result.

Cerebro is the engine. It is given a data feed (one year of daily bars here),
a strategy class, and starting cash, and ``run()`` walks the bars one by one,
calling the strategy's ``next()`` on each. The strategy buys when a fast
moving average crosses above a slow one and sells on the opposite cross.

Run it:  python examples/01_first_backtest.py [--plot]
"""

import sys
from pathlib import Path

import backtrader as bt

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"


class SmaCross(bt.Strategy):
    # params become self.p.<name>; pass other values to addstrategy()
    params = (("fast", 10), ("slow", 30))

    def __init__(self):
        # Indicators are declared once, here. They are computed for every bar
        # and indexed relative to now: [0] is this bar, [-1] the previous one.
        fast = bt.ind.SMA(period=self.p.fast)
        slow = bt.ind.SMA(period=self.p.slow)
        self.crossover = bt.ind.CrossOver(fast, slow)  # +1 up, -1 down, else 0

    def next(self):
        # Called once per bar, from the first bar on which every indicator
        # has enough history (30 bars for the slow average).
        if not self.position and self.crossover[0] > 0:
            self.buy(size=10)  # a market order: fills at the next bar's open
        elif self.position and self.crossover[0] < 0:
            self.close()

    def notify_trade(self, trade):
        if trade.isclosed:
            when = self.data.datetime.date(0)
            print(f"{when} trade closed, profit {trade.pnl:9.2f}")


def main(plot=False):
    cerebro = bt.Cerebro()
    data = bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt"))
    cerebro.adddata(data)
    cerebro.addstrategy(SmaCross)
    cerebro.broker.setcash(100_000.0)

    start = cerebro.broker.getvalue()
    cerebro.run()
    end = cerebro.broker.getvalue()
    print(f"start {start:,.2f}  end {end:,.2f}  return {end / start - 1:.2%}")

    if plot:
        cerebro.plot()
    return end


if __name__ == "__main__":
    main(plot="--plot" in sys.argv)
