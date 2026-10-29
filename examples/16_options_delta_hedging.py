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
"""Greeks in a strategy: a long call, delta-hedged when delta drifts.

``OptionGreeks(option, underlying)`` gives the implied volatility and the
greeks on every bar. The strategy buys 10 calls and keeps the position
delta-neutral by selling the underlying: 10 contracts x 100 units x delta.
It does not re-hedge every day: only when the position's delta has drifted
more than ``band`` units from neutral, which saves trading costs at the
price of carrying some risk in between.

What is left is a bet on volatility: the hedged call earns when the
underlying moves more than its implied volatility priced in (gamma), and
pays the time decay (theta) for that.

Run it:  python examples/16_options_delta_hedging.py
"""

from pathlib import Path

import backtrader as bt
from backtrader.options import OptionContract, OptionCSVData, OptionGreeks

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"


class DeltaHedged(bt.Strategy):
    params = (("contracts", 10), ("band", 50))

    def __init__(self):
        self.stock = self.getdatabyname("index")
        self.call = self.getdatabyname("call")
        self.greeks = OptionGreeks(self.call, self.stock, rate=0.03)
        self.hedges = 0

    def next(self):
        if len(self) == 1:
            self.buy(data=self.call, size=self.p.contracts)
            return
        held = self.getposition(self.call).size
        if not held:  # the option has settled: drop the hedge
            if self.getposition(self.stock):
                self.close(data=self.stock)
            return
        delta = self.greeks.delta[0]
        if delta != delta:  # NaN: expiry day, nothing left to imply
            return
        mult = self.call.contract.multiplier
        target = -round(held * mult * delta)  # the stock position that is neutral
        if self.p.band is None:
            return  # unhedged, for comparison
        if abs(target - self.getposition(self.stock).size) > self.p.band:
            self.order_target_size(data=self.stock, target=target)
            self.hedges += 1

    def notify_order(self, order):
        leg = order.info.get("settlement")
        if order.status == order.Completed and leg:
            print(
                f"{order.data.datetime.date(0)} {leg} of {order.data._name}: "
                f"{order.executed.size:+.0f} at {order.executed.price:.2f}"
            )

    def stop(self):
        band = "never" if self.p.band is None else f"{self.p.band} units"
        print(f"hedge band {band:9s}: re-hedged {self.hedges:3d} times", end="")


def run(band, plot=False):
    cerebro = bt.Cerebro()
    cerebro.adddata(
        bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt")),
        name="index",
    )
    contract = OptionContract(
        "index", strike=4000, expiry="2006-12-15", right="C", settlement="cash"
    )
    cerebro.addoption(
        OptionCSVData(
            dataname=str(DATAS / "2006-day-001-c4000.txt"),
            dtformat="%Y-%m-%d",
            contract=contract,
        ),
        name="call",
    )
    cerebro.addstrategy(DeltaHedged, band=band)
    cerebro.broker.setcash(1_000_000.0)
    cerebro.run()
    print(f", profit {cerebro.broker.getvalue() - 1_000_000:10,.2f}")
    if plot:
        cerebro.plot()


def main(plot=False):
    # The call was bought at 20% implied volatility, but the index only moved
    # at 14.7% (annualised) in 2006. A hedged long call pays for volatility
    # that never came: it loses most of its time value, about 179,000 for a
    # daily close-to-close hedge. Unhedged, the same call lost only 29,650,
    # because the 2006 rally paid for it - market risk, not a volatility
    # edge. The hedge removes that exposure and leaves the volatility bet.
    for band in (None, 400, 100, 25):
        run(band, plot=plot and band == 25)


if __name__ == "__main__":
    main()
