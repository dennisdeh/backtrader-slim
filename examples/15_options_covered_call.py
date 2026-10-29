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
"""Stock and options together: a covered call, assigned at expiry.

The strategy holds 100 units of the underlying and sells one call against
them (one contract covers 100 units). The call - strike 4000, expiring
2006-12-15 - comes from ``datas/2006-day-001-c4000.txt``, a contract priced
by Black-Scholes on the 2006 daily data.

The underlying closes at 4140.66 on expiry day, above the strike, so the
call is assigned: the broker buys the call back at its intrinsic value and
delivers the 100 units at the close. ``notify_order`` sees each leg, marked
in ``order.info.settlement``. The result is what a covered call promises:
the premium plus the rise up to the strike, and nothing above it.

Run it:  python examples/15_options_covered_call.py
"""

from pathlib import Path

import backtrader as bt
from backtrader.options import OptionCommInfo, OptionContract, OptionCSVData

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"


class CoveredCall(bt.Strategy):
    def __init__(self):
        self.stock = self.getdatabyname("index")
        self.call = self.getdatabyname("call")

    def next(self):
        if len(self) == 1:
            self.buy(data=self.stock, size=100)
            self.sell(data=self.call, size=1)  # one contract: 100 units

    def notify_order(self, order):
        if order.status != order.Completed:
            return
        leg = order.info.get("settlement") or "trade"
        print(
            f"{order.data.datetime.date(0)} {leg:10s} {order.data._name:5s} "
            f"{order.executed.size:+6.0f} at {order.executed.price:8.2f}"
        )

    def notify_trade(self, trade):
        if trade.isclosed:
            print(f"  {trade.data._name} trade closed: {trade.pnlcomm:+.2f}")


def main(plot=False):
    cerebro = bt.Cerebro()
    cerebro.adddata(
        bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt")),
        name="index",
    )
    contract = OptionContract("index", strike=4000, expiry="2006-12-15", right="C")
    call = OptionCSVData(
        dataname=str(DATAS / "2006-day-001-c4000.txt"),
        dtformat="%Y-%m-%d",
        bid=7,
        ask=8,
        contract=contract,
    )
    cerebro.addoption(call, name="call", comminfo=OptionCommInfo(commission=0.65))
    cerebro.addstrategy(CoveredCall)
    cerebro.broker.setcash(1_000_000.0)

    cerebro.run()
    print(f"final value {cerebro.broker.getvalue():,.2f} from 1,000,000.00")
    if plot:
        cerebro.plot()


if __name__ == "__main__":
    main()
