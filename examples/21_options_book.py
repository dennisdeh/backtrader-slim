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
"""A whole options book: combo orders, margin, portfolio greeks, structures.

Each month the strategy sells an iron condor: a put spread below the market
and a call spread above it, four legs sent as one ``combo`` order. The
broker checks and fills the four together, or none of them.

The broker runs the ``CashCovered`` margin model: every short option must
be backed by cash, stock or a long option. A condor's short legs are each
covered by the long leg beyond them, so it reserves only the width of each
spread. In January the strategy first tries a naked strangle (the short
legs without the long ones). The model refuses it, because no amount of
cash covers a naked short call.

``PortfolioGreeks`` records the book's delta, gamma, vega and theta in money
every bar, and ``StructureTrades`` reports each condor's profit as one
result rather than four.

The contracts are model-priced (``ModelOptionData``), quoted with a
spread of 6% of the price, and the broker fills every order halfway
from mid to the far side of the quote (``set_quotefill(0.5)``): buying
pays half the spread over mid, selling receives half of it under. Model
prices still flatter selling options: there is no skew.

Run it:  python examples/21_options_book.py [--plot]
"""

import datetime
import sys
from pathlib import Path

import backtrader as bt
from backtrader.options import (
    CashCovered,
    ModelOptionData,
    OptionCommInfo,
    OptionContract,
    PortfolioGreeks,
    StructureTrades,
)

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"
WINGS = {("P", 0.90): +1, ("P", 0.95): -1, ("C", 1.05): -1, ("C", 1.10): +1}


def third_friday(year, month):
    day = datetime.date(year, month, 15)
    return day + datetime.timedelta(days=(4 - day.weekday()) % 7)


class IronCondor(bt.Strategy):
    def __init__(self):
        self.index = self.getdatabyname("index")
        self.months = {}  # expiry -> {(right, moneyness): feed}
        for d in self.datas:
            if d is not self.index:
                key = (d.contract.right, d.p.moneyness)
                self.months.setdefault(d.contract.expiry, {})[key] = d
        self.tried_naked = False

    def prenext(self):
        self.next()

    def next(self):
        today = self.index.datetime.date(0)
        for expiry, legs in self.months.items():
            first = legs[("P", 0.95)]
            if len(first) != 1 or first.datetime.date(0) != today:
                continue
            if not self.tried_naked:
                self.tried_naked = True
                self.combo([(legs[("P", 0.95)], -1), (legs[("C", 1.05)], -1)])
            self.combo([(legs[key], size) for key, size in WINGS.items()])

    def notify_order(self, order):
        if order.status == order.Margin:
            print(
                f"{self.index.datetime.date(0)} refused by the margin model: "
                f"{order.data._name}"
            )

    def notify_margin(self, call):
        print(f"{call.dt:%Y-%m-%d} margin call: {call.shortfall:,.2f} short")


def main(plot=False):
    cerebro = bt.Cerebro(stdstats=False)
    index = bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt"))
    cerebro.adddata(index, name="index")
    for month in range(1, 13):
        expiry = third_friday(2006, month)
        for right, moneyness in WINGS:
            contract = OptionContract("index", 1, expiry, right, settlement="cash")
            cerebro.addoption(
                ModelOptionData(
                    dataname=index,
                    contract=contract,
                    listing=datetime.date(2006, month, 1),
                    moneyness=moneyness,
                    strikestep=10,
                    rate=0.03,
                    spread=0.06,
                ),
                comminfo=OptionCommInfo(commission=0.65),
            )
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.set_margin_model(CashCovered())
    cerebro.broker.set_quotefill(0.5)
    cerebro.addobserver(PortfolioGreeks, rate=0.03)
    cerebro.addanalyzer(StructureTrades, _name="condors")
    cerebro.addstrategy(IronCondor)
    strat = cerebro.run()[0]

    print("condor              opened      closed       profit      worst")
    for ref, s in strat.analyzers.condors.get_analysis().items():
        print(
            f"#{ref:<3d} {s['legs'][0][6:16]}  {s['opened']}  {s['closed']}  "
            f"{s['pnl']:+10,.2f} {s['worst']:+10,.2f}"
        )
    # the observer's lines run with the strategy's bars: find a day mid-way
    # through the June condor
    greeks = [o for o in strat.getobservers() if isinstance(o, PortfolioGreeks)][0]
    days = [bt.num2date(x).date() for x in strat.data0.datetime.array]
    i = days.index(datetime.date(2006, 6, 9))
    print(
        f"the book on 2006-06-09: delta {greeks.delta.array[i]:,.0f}, "
        f"gamma {greeks.gamma.array[i]:,.0f} per 1%, "
        f"vega {greeks.vega.array[i]:,.0f} per vol point, "
        f"theta {greeks.theta.array[i]:+,.0f} per day"
    )
    print(f"final value {cerebro.broker.getvalue():,.2f} from 100,000.00")
    if plot:
        cerebro.plot()


if __name__ == "__main__":
    main(plot="--plot" in sys.argv)
