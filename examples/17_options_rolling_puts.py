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
"""Options that roll: a monthly protective put, from a pricing model.

Real strategies trade a new contract every month. Each contract is its own
data feed, listed on its first day and gone after expiry. This example has
no option market data, so it makes its own. For every month of 2006 it
prices a put 5% below the market, expiring on the third Friday, with
Black-Scholes at 15% volatility. It writes each contract to a CSV file, and
the strategy buys it on its first day.

Three things to notice:

- A feed that has not started yet holds the strategy in ``prenext``. This
  strategy simply runs ``next`` there too.
- A contract still held at expiry is settled by the broker, in cash here:
  the put pays its intrinsic value if the market closed below the strike.
- Model prices are not market prices. Real puts carry a skew (out-of-the-
  money puts trade at higher implied volatility) and a bid/ask spread, so
  protection costs more than this shows.

Run it:  python examples/17_options_rolling_puts.py
"""

import datetime
import tempfile
from pathlib import Path

import backtrader as bt
from backtrader.options import OptionContract, OptionCSVData, pricing

REQUIRES = ()
DATAS = Path(__file__).resolve().parent.parent / "datas"
VOL, RATE, OTM = 0.15, 0.03, 0.95


def third_friday(year, month):
    day = datetime.date(year, month, 15)
    return day + datetime.timedelta(days=(4 - day.weekday()) % 7)


def write_contracts(folder):
    """One CSV per monthly put, priced from the underlying. Returns
    (contract, path) pairs."""
    rows = [
        line.split(",")
        for line in (DATAS / "2006-day-001.txt").read_text().splitlines()[1:]
    ]
    bars = [(datetime.date.fromisoformat(r[0]), float(r[4])) for r in rows]
    contracts = []
    for month in range(1, 13):
        expiry = third_friday(2006, month)
        life = [(d, s) for d, s in bars if d.month == month and d <= expiry]
        if len(life) < 2:
            continue
        strike = round(life[0][1] * OTM, -1)
        contract = OptionContract(
            "index", strike, expiry, "P", settlement="cash", multiplier=100
        )
        path = Path(folder) / f"put-{expiry}.csv"
        with open(path, "w") as f:
            f.write("Date,Open,High,Low,Close,Volume,OpenInterest\n")
            for d, s in life:
                T = (expiry - d).days / 365
                p = pricing.bsm("P", s, strike, T, RATE, VOL).price
                f.write(f"{d},{p:.4f},{p:.4f},{p:.4f},{p:.4f},0,0\n")
        contracts.append((contract, path))
    return contracts


class ProtectivePut(bt.Strategy):
    def __init__(self):
        self.index = self.getdatabyname("index")
        self.puts = [d for d in self.datas if d is not self.index]
        self.bought = set()
        self.cost = self.payout = 0.0

    def prenext(self):
        self.next()  # later contracts have no bars yet; trade anyway

    def next(self):
        if not self.getposition(self.index):
            self.buy(data=self.index, size=100)
        for put in self.puts:
            first_day = len(put) == 1 and put.datetime.date(
                0
            ) == self.index.datetime.date(0)
            if first_day and put not in self.bought:
                self.buy(data=put, size=1)
                self.bought.add(put)

    def notify_order(self, order):
        if order.status != order.Completed or order.data is self.index:
            return
        value = abs(order.executed.price) * order.data.contract.multiplier
        if order.info.get("settlement"):
            self.payout += value
            kind = order.info.settlement
            print(
                f"{order.data.datetime.date(0)} {order.data._name}: {kind}, pays {value:8.2f}"
            )
        else:
            self.cost += value


def main(plot=False):
    with tempfile.TemporaryDirectory() as folder:
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(
            bt.feeds.BacktraderCSVData(dataname=str(DATAS / "2006-day-001.txt")),
            name="index",
        )
        for contract, path in write_contracts(folder):
            feed = OptionCSVData(
                dataname=str(path), dtformat="%Y-%m-%d", contract=contract
            )
            cerebro.addoption(
                feed, name=f"put {contract.expiry:%b} {contract.strike:g}"
            )
        cerebro.addstrategy(ProtectivePut)
        cerebro.broker.setcash(1_000_000.0)
        strat = cerebro.run()[0]

    print(f"puts bought for {strat.cost:,.2f}, paid out {strat.payout:,.2f}")
    print(f"final value {cerebro.broker.getvalue():,.2f} from 1,000,000.00")


if __name__ == "__main__":
    main()
