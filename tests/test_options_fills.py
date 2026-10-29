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
"""Fills at the quote: mid +/- a fraction of the spread (broker quotefill).

The option feed below quotes 4.00 bid / 5.00 ask on every bar after the
first, with OHLC at 4.40: so mid is 4.50 and half the spread 0.50, and each
expected price is mid +/- fraction x 0.50.
"""

import datetime
import io

import pytest

import backtrader as bt
from backtrader.options import OptionContract, OptionCSVData

from test_options_settlement import DAYS, EXPIRY, UND_UP, underlying


def quoted_option(quotes, contract):
    text = "datetime,open,high,low,close,volume,openinterest,bid,ask\n" + "".join(
        f"{d:%Y-%m-%d},4.4,4.4,4.4,4.4,0,0,{bid},{ask}\n"
        for d, (bid, ask) in zip(DAYS, quotes)
    )
    return OptionCSVData(
        dataname=io.StringIO(text),
        dtformat="%Y-%m-%d",
        headers=True,
        name="csv",
        bid=7,
        ask=8,
        contract=contract,
    )


QUOTES = [(3.0, 3.2)] + [(4.0, 5.0)] * 4
NAN = float("nan")


class Trade(bt.Strategy):
    params = (("side", "buy"), ("exectype", bt.Order.Market))

    def start(self):
        self.fills = []

    def notify_order(self, order):
        if order.status == order.Completed and not order.info.get("settlement"):
            self.fills.append((order.data._name, order.executed.price))

    def next(self):
        if len(self) == 1:
            getattr(self, self.p.side)(data=self.datas[1], exectype=self.p.exectype)


def fills(fraction, quotes=QUOTES, coc=False, **kw):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(UND_UP), name="und")
    contract = OptionContract("und", 100, EXPIRY, "C", settlement="cash")
    cerebro.addoption(quoted_option(quotes, contract), name="opt")
    if fraction is not None:
        cerebro.broker.set_quotefill(fraction)
    cerebro.broker.set_coc(coc)
    cerebro.addstrategy(Trade, **kw)
    return cerebro.run()[0].fills


@pytest.mark.parametrize(
    "fraction,side,expected",
    [
        (0.0, "buy", 4.50),  # mid
        (0.0, "sell", 4.50),
        (0.5, "buy", 4.75),  # 4.50 + 0.5 x 0.50
        (0.5, "sell", 4.25),
        (1.0, "buy", 5.00),  # crossing: the ask
        (1.0, "sell", 4.00),  # the bid
    ],
)
def test_a_market_order_fills_at_the_execution_bars_quote(fraction, side, expected):
    assert fills(fraction, side=side) == [("opt", pytest.approx(expected))]


def test_without_quotefill_it_fills_at_the_open_as_before():
    assert fills(None) == [("opt", 4.4)]


def test_a_bar_without_both_quotes_fills_at_the_open():
    quotes = [(3.0, 3.2), (NAN, 5.0)] + [(4.0, 5.0)] * 3
    assert fills(0.5, quotes=quotes) == [("opt", 4.4)]


def test_cheat_on_close_fills_at_the_creation_bars_quote():
    # sent on bar 1, whose quote is 3.00 / 3.20: mid 3.10 + 0.5 x 0.10
    assert fills(0.5, coc=True) == [("opt", pytest.approx(3.15))]


def test_a_close_order_fills_at_its_bars_quote():
    assert fills(1.0, exectype=bt.Order.Close) == [("opt", pytest.approx(5.0))]


def test_a_feed_without_quotes_is_not_affected():
    class Stock(Trade):
        def next(self):
            if len(self) == 1:
                self.buy(data=self.datas[0])

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(UND_UP), name="und")
    cerebro.broker.set_quotefill(1.0)
    cerebro.addstrategy(Stock)
    assert cerebro.run()[0].fills == [("und", 101.0)]  # bar 2's open


def test_combo_legs_fill_at_their_quotes():
    class Combo(Trade):
        def next(self):
            if len(self) == 1:
                self.combo([(self.datas[1], 1), (self.datas[2], -1)])

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(UND_UP), name="und")
    for name, strike in (("c100", 100), ("c105", 105)):
        contract = OptionContract("und", strike, EXPIRY, "C", settlement="cash")
        cerebro.addoption(quoted_option(QUOTES, contract), name=name)
    cerebro.broker.set_quotefill(1.0)
    cerebro.broker.setcash(100_000.0)
    cerebro.addstrategy(Combo)
    assert cerebro.run()[0].fills == [("c100", 5.0), ("c105", 4.0)]


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_a_fraction_outside_0_to_1_is_refused(bad):
    with pytest.raises(ValueError, match="fraction"):
        bt.Cerebro().broker.set_quotefill(bad)
