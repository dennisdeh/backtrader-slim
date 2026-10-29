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
"""Measuring a run: analyzers.

An analyzer watches the run and reports a summary at the end, read with
``get_analysis()`` from the strategy ``cerebro.run()`` returns. Shown here:
returns, Sharpe ratio, drawdown, the trade statistics, the system quality
number, and returns per year and per month.

Run it:  python examples/08_analyzers.py
"""

from pathlib import Path

import backtrader as bt

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"


class SmaCross(bt.Strategy):
    def __init__(self):
        self.cross = bt.ind.CrossOver(bt.ind.SMA(period=10), bt.ind.SMA(period=30))

    def next(self):
        if self.cross[0] > 0:
            self.order_target_percent(target=0.95)
        elif self.cross[0] < 0:
            self.order_target_percent(target=0.0)


def main(plot=False):
    cerebro = bt.Cerebro()
    cerebro.adddata(
        bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2005-2006-day-001.txt"))
    )
    cerebro.addstrategy(SmaCross)
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,
        annualize=True,
        riskfreerate=0.0,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual")
    cerebro.addanalyzer(
        bt.analyzers.TimeReturn, _name="monthly", timeframe=bt.TimeFrame.Months
    )

    strat = cerebro.run()[0]
    a = {name: strat.analyzers.getbyname(name).get_analysis() for name in (
        "returns", "sharpe", "drawdown", "trades", "sqn", "annual", "monthly"
    )}  # fmt: skip

    trades = a["trades"]
    print(f"total return      {a['returns']['rtot']:8.2%}")
    print(f"annualised return {a['returns']['rnorm']:8.2%}")
    print(f"Sharpe ratio      {a['sharpe']['sharperatio']:8.2f}")
    print(f"max drawdown      {a['drawdown'].max.drawdown / 100:8.2%}")
    print(f"trades            {trades.total.closed:8d}")
    print(f"  won / lost      {trades.won.total:4d} / {trades.lost.total:d}")
    print(f"  net profit      {trades.pnl.net.total:8.2f}")
    print(f"SQN               {a['sqn']['sqn']:8.2f}")
    for year, ret in a["annual"].items():
        print(f"year {year}         {ret:8.2%}")
    best = max(a["monthly"].items(), key=lambda kv: kv[1])
    print(f"best month        {best[0]:%Y-%m} {best[1]:+.2%}")


if __name__ == "__main__":
    main()
