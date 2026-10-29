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
"""Several stocks at once: a momentum rotation rebalanced by a timer.

Each data feed is one stock; ``self.datas`` holds them all and each has its
own position. At the start of the first session of every month a timer
fires ``notify_timer``, which ranks the stocks by their 3-month momentum and puts
the portfolio equally into the top two, through ``order_target_percent``
per stock. Sells are sent before buys so that their cash is there for the
purchases.

Run it:  python examples/11_portfolio_rotation.py
"""

from pathlib import Path

import backtrader as bt

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"
STOCKS = ("nvda", "orcl", "yhoo")


class Rotation(bt.Strategy):
    params = (("lookback", 63), ("top", 2))

    def __init__(self):
        self.momentum = {
            d: bt.ind.RateOfChange(d.close, period=self.p.lookback) for d in self.datas
        }
        self.add_timer(when=bt.timer.SESSION_START, monthdays=[1], monthcarry=True)

    def notify_timer(self, timer, when, *args, **kwargs):
        if len(self) <= self.p.lookback:
            return  # momentum not ready yet
        ranked = sorted(self.datas, key=lambda d: self.momentum[d][0], reverse=True)
        chosen = ranked[: self.p.top]
        weight = 0.95 / self.p.top

        for d in self.datas:  # sell first, so the cash is there for the buys
            if d not in chosen and self.getposition(d):
                self.order_target_percent(data=d, target=0.0)
        for d in chosen:
            self.order_target_percent(data=d, target=weight)

        # ``when`` is the session the timer fired for; the strategy's clock
        # still shows the previous bar, whose close the ranking used
        names = ", ".join(f"{d._name} {self.momentum[d][0]:+.1%}" for d in ranked)
        held = ", ".join(d._name for d in chosen)
        print(f"{when:%Y-%m-%d} momentum: {names} -> hold {held}")


def main(plot=False):
    cerebro = bt.Cerebro()
    for name in STOCKS:
        data = bt.feeds.YahooFinanceCSVData(dataname=str(DATAS / f"{name}-2014.txt"))
        cerebro.adddata(data, name=name)
    cerebro.addstrategy(Rotation)
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.0005)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    strat = cerebro.run()[0]
    print(f"return over 2014: {strat.analyzers.returns.get_analysis()['rtot']:.2%}")
    for d in strat.datas:
        print(f"  {d._name}: holding {strat.getposition(d).size:.0f}")
    if plot:
        cerebro.plot()


if __name__ == "__main__":
    main()
