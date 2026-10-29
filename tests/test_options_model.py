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
"""ModelOptionData: option bars priced by a model from the underlying's.

The expectations are recomputed here from the CSV file itself, with the
standard library's statistics module for the realised volatility, rather
than read back from the feed.
"""

import datetime
import itertools
import math
import statistics

import pytest

import backtrader as bt
from backtrader.options import ModelOptionData, OptionContract, OptionGreeks, pricing

from conftest import datafile

UNDERLYING = "2006-day-001.txt"
EXPIRY = datetime.date(2006, 3, 17)


def bars():
    with open(datafile(UNDERLYING)) as f:
        rows = [line.split(",") for line in f.read().splitlines()[1:]]
    return [
        (datetime.date.fromisoformat(r[0]), *(float(x) for x in r[1:5])) for r in rows
    ]


def realised(closes, window=21, vol0=0.20, volmin=5):
    """Volatility from the last ``window`` returns of ``closes``."""
    closes = closes[-(window + 1) :]
    if len(closes) <= volmin:
        return vol0
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    return statistics.stdev(rets) * math.sqrt(252)


class Record(bt.Strategy):
    params = (("greeks", False),)

    def __init__(self):
        self.opt = self.datas[1]
        self.rows = []
        if self.p.greeks:
            self.g = OptionGreeks(self.opt, self.datas[0], rate=0.03)

    def prenext(self):
        self.next()

    def next(self):
        o = self.opt
        if len(o) and o.datetime.date(0) == self.datas[0].datetime.date(0):
            row = [o.datetime.date(0), o.open[0], o.high[0], o.low[0], o.close[0]]
            row += [o.bid[0], o.ask[0], o.contract.strike]
            if self.p.greeks:
                row.append(self.g.iv[0])
            self.rows.append(tuple(row))


def run(right="C", strike=3700.0, cerebro_kw={}, greeks=False, **feed):
    cerebro = bt.Cerebro(stdstats=False, **cerebro_kw)
    und = bt.feeds.BacktraderCSVData(dataname=datafile(UNDERLYING))
    cerebro.adddata(und, name="idx")
    contract = OptionContract("idx", strike, EXPIRY, right, settlement="cash")
    feed = dict(rate=0.03) | feed
    cerebro.addoption(ModelOptionData(dataname=und, contract=contract, **feed))
    cerebro.addstrategy(Record, greeks=greeks)
    return cerebro, cerebro.run()[0]


def test_a_constant_volatility_prices_every_bar_by_black_scholes():
    _, strat = run(vol=0.25)
    data = {d: (o, h, l, c) for d, o, h, l, c in bars()}
    assert strat.rows[0][0] == datetime.date(2006, 1, 2)
    assert strat.rows[-1][0] == EXPIRY
    for day, o, h, l, c, *_ in strat.rows:
        T = (EXPIRY - day).days / 365
        expected = [pricing.bsm("C", s, 3700, T, 0.03, 0.25).price for s in data[day]]
        assert (o, c) == pytest.approx((expected[0], expected[3]))
        # a call rises with the underlying: its high is the underlying's high
        assert (h, l) == pytest.approx((expected[1], expected[2]))


def test_a_put_takes_its_high_from_the_underlyings_low():
    _, strat = run(right="P", vol=0.25)
    data = {d: (o, h, l, c) for d, o, h, l, c in bars()}
    day, _, high, low, *_ = strat.rows[10]
    T = (EXPIRY - day).days / 365
    assert high == pytest.approx(
        pricing.bsm("P", data[day][2], 3700, T, 0.03, 0.25).price
    )
    assert low == pytest.approx(
        pricing.bsm("P", data[day][1], 3700, T, 0.03, 0.25).price
    )


def test_realised_volatility_uses_only_closes_before_the_bar():
    _, strat = run(greeks=True)
    history = bars()
    closes = {d: i for i, (d, *_) in enumerate(history)}
    # the last days are left out: with almost no time value left, the price
    # pins the volatility down only loosely, so inverting it is imprecise
    for row in strat.rows[:-5]:
        day, iv = row[0], row[-1]
        before = [c for _, _, _, _, c in history[: closes[day]]]
        assert iv == pytest.approx(realised(before), abs=1e-7), day


def test_the_first_bars_use_vol0_until_enough_returns_exist():
    _, strat = run(greeks=True, vol0=0.33)
    # bar 6 has 5 closes before it: 4 returns, fewer than volmin (5)
    assert [round(r[-1], 6) for r in strat.rows[:6]] == [0.33] * 6
    assert round(strat.rows[6][-1], 6) != 0.33


def test_listing_starts_the_contract_and_expiry_ends_it():
    _, strat = run(listing="2006-02-01", vol=0.2)
    assert strat.rows[0][0] == datetime.date(2006, 2, 1)
    assert strat.rows[-1][0] == EXPIRY
    assert len(strat.rows) == 33


def test_moneyness_sets_the_strike_from_the_close_before_listing():
    _, strat = run(
        right="P", listing="2006-02-01", moneyness=0.95, strikestep=10, vol=0.2
    )
    # 2006-01-31 closed at 3691.41: 0.95 x 3691.41 = 3506.84, to 3510
    assert {row[7] for row in strat.rows} == {3510.0}


def test_bid_and_ask_straddle_the_close_by_the_spread():
    _, strat = run(vol=0.2, spread=0.04)
    for *_, close, bid, ask, _strike in [r[:8] for r in strat.rows[:-1]]:
        assert (bid, ask) == pytest.approx((close * 0.98, close * 1.02))


def test_the_tree_prices_an_american_put_above_the_european_one():
    _, euro = run(right="P", strike=3900.0, vol=0.2, rate=0.08)
    _, amer = run(right="P", strike=3900.0, vol=0.2, rate=0.08, model="binomial")
    assert amer.rows[0][4] > euro.rows[0][4]


@pytest.mark.parametrize(
    "runonce,preload,exactbars",
    list(itertools.product((True, False), (True, False), (-2, -1, False))),
)
def test_every_mode_gives_the_same_bars(runonce, preload, exactbars):
    kw = dict(runonce=runonce, preload=preload, exactbars=exactbars)
    _, strat = run(cerebro_kw=kw, listing="2006-02-01", moneyness=0.95, strikestep=10)
    _, base = run(listing="2006-02-01", moneyness=0.95, strikestep=10)
    assert strat.rows == base.rows


def test_a_model_contract_settles_at_expiry():
    class Buy(Record):
        settled = []

        def next(self):
            super().next()
            if len(self.opt) == 1:
                self.buy(data=self.opt)

        def notify_order(self, order):
            if order.status == order.Completed and order.info.get("settlement"):
                self.settled.append((order.info.settlement, order.executed.price))

    cerebro = bt.Cerebro(stdstats=False)
    und = bt.feeds.BacktraderCSVData(dataname=datafile(UNDERLYING))
    cerebro.adddata(und, name="idx")
    contract = OptionContract("idx", 3600, EXPIRY, "C", settlement="cash")
    cerebro.addoption(ModelOptionData(dataname=und, contract=contract, vol=0.2))
    cerebro.addstrategy(Buy)
    cerebro.broker.setcash(100_000.0)  # one contract costs about 12,000
    strat = cerebro.run()[0]
    # 2006-03-17 closed at 3832.43: the 3600 call settles for 232.43 per unit
    assert strat.settled == [("exercise", pytest.approx(232.43))]
    opt = cerebro.datas[1]
    assert not cerebro.broker.getposition(opt)
    assert opt._name == "idx 2006-03-17 3600C (model)"


def test_the_underlying_must_be_the_contracts_and_come_first():
    cerebro = bt.Cerebro()
    und = bt.feeds.BacktraderCSVData(dataname=datafile(UNDERLYING))
    contract = OptionContract("idx", 3700, EXPIRY, "C")
    cerebro.addoption(ModelOptionData(dataname=und, contract=contract), name="opt")
    cerebro.adddata(und, name="idx")
    with pytest.raises(ValueError, match="before its model option"):
        cerebro.run()

    cerebro = bt.Cerebro()
    und = bt.feeds.BacktraderCSVData(dataname=datafile(UNDERLYING))
    cerebro.adddata(und, name="other")
    cerebro.addoption(ModelOptionData(dataname=und, contract=contract))
    with pytest.raises(ValueError, match="follows 'other'"):
        cerebro.run()


@pytest.mark.parametrize(
    "kw,match",
    [
        (dict(vol=-0.1), "vol"),
        (dict(vol="implied"), "vol"),
        (dict(model="sabr"), "model"),
    ],
)
def test_impossible_settings_are_refused(kw, match):
    und = bt.feeds.BacktraderCSVData(dataname=datafile(UNDERLYING))
    contract = OptionContract("idx", 3700, EXPIRY, "C")
    with pytest.raises(ValueError, match=match):
        ModelOptionData(dataname=und, contract=contract, **kw)
