#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
# Copyright (C) 2026 Dennis Hansen
#
# This file is part of slim-backtrader, a modified version of backtrader.
# Modified in 2026 by Dennis Hansen. See changelog.txt for the changes.
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

import datetime

import pytest
import testcommon

import backtrader as bt
from backtrader import CommissionInfo, Position


def check_stocks():
    commission = 0.5
    comm = bt.CommissionInfo(commission=commission)

    price = 10.0
    cash = 10000.0
    size = 100.0

    opcost = comm.getoperationcost(size=size, price=price)
    assert opcost == size * price

    pos = Position(size=size, price=price)
    value = comm.getvalue(pos, price)
    assert value == size * price

    commcost = comm.getcommission(size, price)
    assert commcost == size * price * commission

    newprice = 5.0
    pnl = comm.profitandloss(pos.size, pos.price, newprice)
    assert pnl == pos.size * (newprice - price)

    ca = comm.cashadjust(size, price, newprice)
    assert not ca


def check_futures():
    commission = 0.5
    margin = 10.0
    mult = 10.0
    comm = bt.CommissionInfo(commission=commission, mult=mult, margin=margin)

    price = 10.0
    cash = 10000.0
    size = 100.0

    opcost = comm.getoperationcost(size=size, price=price)
    assert opcost == size * margin

    pos = Position(size=size, price=price)
    value = comm.getvalue(pos, price)
    assert value == size * margin

    commcost = comm.getcommission(size, price)
    assert commcost == size * commission

    newprice = 5.0
    pnl = comm.profitandloss(pos.size, pos.price, newprice)
    assert pnl == pos.size * (newprice - price) * mult

    ca = comm.cashadjust(size, price, newprice)
    assert ca == size * (newprice - price) * mult


def check_stocklike_mult():
    # mult applies to cost, value and sizing on the stock-like branch too,
    # not only to profitandloss - see reports/OPEN_ITEMS.md
    mult = 100.0
    comm = bt.CommInfoBase(
        commission=0.65,
        mult=mult,
        stocklike=True,
        commtype=bt.CommInfoBase.COMM_FIXED,
    )

    price, size = 2.0, 3

    assert comm.getoperationcost(size=size, price=price) == size * price * mult
    assert comm.getvaluesize(size, price) == size * price * mult
    assert comm.getvaluesize(-size, price) == -size * price * mult
    assert comm.getsize(price, 1000.0) == 5  # 1000 // (2.0 * 100)

    long = Position(size=size, price=price)
    assert comm.getvalue(long, 4.0) == size * 4.0 * mult

    # a short entered at 2.0 is worth more as the price falls to 1.0
    short = Position(size=-size, price=price)
    assert comm.getvalue(short, 1.0) == (-size * price + (price - 1.0) * -size) * mult

    # unchanged: P&L already applied mult, the fixed commission is per unit
    assert comm.profitandloss(size, price, 4.0) == size * 2.0 * mult
    assert comm.getcommission(size, price) == size * 0.65
    assert not comm.cashadjust(size, price, 4.0)


def test_run(main=False):
    check_stocks()
    check_futures()
    check_stocklike_mult()


class _Bars(bt.feed.DataBase):
    params = (("closes", ()),)

    def start(self):
        super().start()
        self._it = iter(enumerate(self.p.closes))

    def _load(self):
        try:
            i, c = next(self._it)
        except StopIteration:
            return False
        self.lines.datetime[0] = bt.date2num(
            datetime.datetime(2026, 1, 5) + datetime.timedelta(days=i)
        )
        for line in (self.lines.open, self.lines.high, self.lines.low):
            line[0] = c
        self.lines.close[0] = c
        self.lines.volume[0] = 1000.0
        self.lines.openinterest[0] = 0.0
        return True


class _BuyHoldClose(bt.Strategy):
    def start(self):
        self.values = []

    def next(self):
        if len(self) == 1:
            self.buy(size=1)
        elif len(self) == 4:
            self.close()
        self.values.append(self.broker.getvalue())


def test_stocklike_mult_is_valued_while_the_position_is_open():
    # One x100 unit bought at 2.00 (bar 2 open) and sold at 4.00 (bar 5
    # open). The broker used to mark it at x1 while open - 10001, 10002 -
    # and jump to 10200 only once the position closed.
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(_Bars(closes=(2.0, 2.0, 3.0, 4.0, 4.0, 4.0)))
    cerebro.broker.setcash(10000.0)
    cerebro.broker.setcommission(
        mult=100.0, stocklike=True, commtype=bt.CommInfoBase.COMM_FIXED
    )
    cerebro.addstrategy(_BuyHoldClose)
    strat = cerebro.run()[0]

    assert strat.values == [10000.0, 10000.0, 10100.0, 10200.0, 10200.0, 10200.0]


if __name__ == "__main__":
    test_run(main=True)


class _SellHoldClose(_BuyHoldClose):
    def next(self):
        if len(self) == 1:
            self.sell(size=1)
        elif len(self) == 4:
            self.close()
        self.values.append(self.broker.getvalue())


@pytest.mark.parametrize("shortcash", [True, False])
def test_stocklike_mult_values_a_short_while_open(shortcash):
    # One x100 unit sold at 2.00 and bought back at 1.00: +100 either way,
    # whether the short's proceeds are credited to cash or not
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(_Bars(closes=(2.0, 2.0, 1.5, 1.0, 1.0, 1.0)))
    cerebro.broker.setcash(10000.0)
    cerebro.broker.set_shortcash(shortcash)
    cerebro.broker.setcommission(
        mult=100.0, stocklike=True, commtype=bt.CommInfoBase.COMM_FIXED
    )
    cerebro.addstrategy(_SellHoldClose)
    strat = cerebro.run()[0]

    assert strat.values == [10000.0, 10000.0, 10050.0, 10100.0, 10100.0, 10100.0]
