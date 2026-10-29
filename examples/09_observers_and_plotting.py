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
"""Watching a run: observers, and plotting it.

Observers record something every bar and are drawn on the chart. Cerebro
adds three by default (``stdstats=True``): cash and value, the buy/sell
markers, and each trade's result. More can be added, such as the drawdown
or a benchmark.

``cerebro.plot()`` draws every data feed, indicator and observer. It shows
the chart in a window when run as a script, inline in a notebook, and
nothing on a machine without a display. ``iplot=False`` only returns the
figures, to save them.

Run it:  python examples/09_observers_and_plotting.py [--show]
         writes examples/output/09_chart.png either way
"""

import sys
from pathlib import Path

import backtrader as bt

REQUIRES = ("matplotlib",)
HERE = Path(__file__).resolve().parent
DATAS = HERE.parent / "datas"


class SmaCross(bt.Strategy):
    def __init__(self):
        sma = bt.ind.SMA(period=20)
        self.cross = bt.ind.CrossOver(self.data.close, sma, plot=False)
        bt.ind.RSI(period=14)  # drawn in its own panel

    def next(self):
        if self.cross[0] > 0:
            self.buy(size=20)
        elif self.cross[0] < 0 and self.position:
            self.close()


def main(plot=False, out=HERE / "output" / "09_chart.png"):
    cerebro = bt.Cerebro()  # stdstats=True: Broker, BuySell and Trades
    data = bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt"))
    cerebro.adddata(data)
    cerebro.addstrategy(SmaCross)
    cerebro.broker.setcash(100_000.0)
    cerebro.addobserver(bt.observers.DrawDown)
    cerebro.addobserver(bt.observers.Benchmark, data=data)  # buy and hold
    cerebro.run()

    figure = cerebro.plot(iplot=plot, volume=False)[0][0]
    figure.set_size_inches(16, 9)
    out = Path(out)
    out.parent.mkdir(exist_ok=True)
    figure.savefig(out, dpi=100)
    print(f"chart written to {out}")


if __name__ == "__main__":
    main(plot="--show" in sys.argv)
