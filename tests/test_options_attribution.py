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
"""GreeksAttribution: the book's profit and loss split by the greeks."""

import datetime

import pytest

import backtrader as bt
from backtrader.options import GreeksAttribution, ModelOptionData, OptionContract

from test_options_settlement import underlying

DAYS = [datetime.date(2006, 1, 2) + datetime.timedelta(days=i) for i in range(60)]
DAYS = [d for d in DAYS if d.weekday() < 5][:30]
EXPIRY = DAYS[-1]
PARTS = ("delta", "gamma", "vega", "theta", "residual", "other")


class Hold(bt.Strategy):
    params = (("legs", ()),)

    def prenext(self):
        self.next()

    def next(self):
        if len(self) == 1:
            for name, size in self.p.legs:
                self.buy(data=self.getdatabyname(name), size=size)


def run(closes, legs, vol=0.2):
    cerebro = bt.Cerebro(stdstats=False)
    und = underlying(closes, DAYS)
    cerebro.adddata(und, name="und")
    contract = OptionContract("und", 100, EXPIRY, "C", settlement="cash")
    cerebro.addoption(
        ModelOptionData(dataname=und, contract=contract, vol=vol), name="call"
    )
    cerebro.broker.setcash(100_000.0)
    cerebro.addanalyzer(GreeksAttribution)
    cerebro.addstrategy(Hold, legs=legs)
    strat = cerebro.run()[0]
    return cerebro, strat.analyzers[0].get_analysis()


def test_the_parts_add_up_to_the_whole_gain():
    closes = [100 + 3 * ((i * 7) % 5 - 2) + i * 0.2 for i in range(len(DAYS))]
    cerebro, a = run(closes, [("call", 2), ("und", -100)], vol=0.25)
    total = sum(a[part] for part in PARTS)
    assert total == pytest.approx(cerebro.broker.getvalue() - 100_000.0)
    per_bar = sum(sum(bar.values()) for bar in a["bars"].values())
    assert per_bar == pytest.approx(total)


def test_a_held_call_on_a_flat_market_loses_theta():
    # no move, constant volatility: no delta, gamma or vega to speak of; the
    # call's value decays, and theta explains nearly all of it
    cerebro, a = run([100.0] * len(DAYS), [("call", 1)])
    held = sum(a[part] for part in ("delta", "gamma", "vega", "theta", "residual"))
    assert held < 0
    assert abs(a["delta"]) + abs(a["gamma"]) + abs(a["vega"]) < 1e-6
    # theta in steps of a day or a weekend misses the decay's curvature,
    # most of all in the last days before expiry
    assert a["theta"] == pytest.approx(held, rel=0.15)


def test_a_stock_position_is_all_delta():
    closes = [100.0 + i for i in range(len(DAYS))]
    _, a = run(closes, [("und", 10)])
    # bought at bar 2's open, which is also its close here (101), and held
    # to the last close (129)
    assert a["delta"] == pytest.approx(10 * (129 - 101))
    assert a["gamma"] == a["vega"] == a["theta"] == a["residual"] == 0.0


def test_delta_explains_most_of_a_trending_move():
    closes = [100.0 + 0.5 * i for i in range(len(DAYS))]
    _, a = run(closes, [("call", 1)])
    explained = a["delta"] + a["gamma"] + a["theta"] + a["vega"]
    assert abs(a["residual"]) < 0.1 * abs(explained)
    assert a["delta"] > 0 and a["gamma"] > 0 and a["theta"] < 0
