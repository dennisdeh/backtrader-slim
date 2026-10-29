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
"""Option contracts trading through cerebro: valuation, commission, expiry.

Every expected number below is worked out by hand in the comment beside it,
from the premium, the strike, the underlying's close and the multiplier.
"""

import datetime
import io

import pytest

import backtrader as bt
from backtrader.options import OptionCommInfo, OptionContract, OptionCSVData

# Mon 2006-03-13 .. Wed 2006-03-22; the contract expires Fri 2006-03-17
DAYS = [datetime.date(2006, 3, d) for d in (13, 14, 15, 16, 17, 20, 21, 22)]
EXPIRY = DAYS[4]


def _csv(rows, intraday=False):
    fmt = "%Y-%m-%d %H:%M:%S" if intraday else "%Y-%m-%d"
    text = "datetime,open,high,low,close,volume,openinterest\n" + "".join(
        f"{d.strftime(fmt)},{o},{max(o, c)},{min(o, c)},{c},1000,0\n"
        for d, o, c in rows
    )
    return dict(dataname=io.StringIO(text), dtformat=fmt, headers=True)


def underlying(closes, days=DAYS, **kw):
    rows = [(d, c, c) for d, c in zip(days, closes)]
    return bt.feeds.GenericCSVData(**_csv(rows, **kw), **kw_timeframe(kw))


def kw_timeframe(kw):
    if kw.get("intraday"):
        return dict(timeframe=bt.TimeFrame.Minutes)
    return {}


def option(premiums, contract, days=DAYS, **kw):
    rows = [(d, p, p) for d, p in zip(days, premiums)]
    return OptionCSVData(**_csv(rows, **kw), contract=contract, **kw_timeframe(kw))


def contract(right="C", settlement="physical", strike=100.0):
    return OptionContract("und", strike, EXPIRY, right, settlement=settlement)


class Trader(bt.Strategy):
    """Trades ``size`` contracts on bar 1 (filled at bar 2's open) and,
    with ``close_on``, closes them on that bar (filled at the next open)."""

    params = (("size", 1), ("close_on", None))

    def start(self):
        self.legs = []
        self.trades = []

    def notify_order(self, order):
        if order.status == order.Completed:
            self.legs.append(
                (
                    order.data._name,
                    order.info.get("settlement"),
                    order.executed.size,
                    order.executed.price,
                    round(order.executed.comm, 2),
                )
            )

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trades.append((trade.data._name, round(trade.pnl, 2)))

    def next(self):
        opt = self.getdatabyname("opt")
        if len(self) == 1:
            if self.p.size > 0:
                self.buy(data=opt, size=self.p.size)
            else:
                self.sell(data=opt, size=-self.p.size)
        if self.p.close_on is not None and len(self) == self.p.close_on:
            self.close(data=opt)


def run(und_closes, premiums, ctr, size=1, cash=20000.0, comminfo=None, **stkw):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(und_closes), name="und")
    cerebro.addoption(option(premiums, ctr), name="opt", comminfo=comminfo)
    cerebro.broker.setcash(cash)
    cerebro.addstrategy(Trader, size=size, **stkw)
    strat = cerebro.run()[0]
    broker = cerebro.broker
    pos = {
        name: broker.getposition(cerebro.datasbyname[name]) for name in ("und", "opt")
    }
    return strat, broker, pos


UND_UP = [100, 101, 102, 103, 105, 105, 105, 105]  # 105 at expiry
UND_DOWN = [100, 99, 98, 97, 95, 95, 95, 95]  # 95 at expiry
PREM = [3.0, 3.0, 3.5, 4.0, 5.0]  # bought at bar 2's open: 3.0


def test_a_long_option_is_valued_at_close_times_the_multiplier():
    strat, broker, pos = run(UND_UP, PREM, contract(settlement="cash"), close_on=3)
    # bought at 3.00, sold at bar 4's open (4.00): +100 with no commission
    assert strat.trades == [("opt", 100.0)]
    assert broker.getvalue() == pytest.approx(20100.0)


def test_closing_on_expiry_morning_leaves_nothing_to_settle():
    strat, _, pos = run(UND_UP, PREM, contract(), close_on=4)
    # the close fills at expiry day's open (5.00), before settlement runs
    assert [leg[1] for leg in strat.legs] == [None, None]
    assert not pos["opt"] and not pos["und"]


def test_a_cash_settled_call_in_the_money_pays_its_intrinsic_value():
    strat, broker, pos = run(UND_UP, PREM, contract(settlement="cash"))
    # paid 300; settles at 105 - 100 = 5 per unit, 500 per contract
    assert strat.legs[-1] == ("opt", "exercise", -1, 5.0, 0.0)
    assert strat.trades == [("opt", 200.0)]
    assert not pos["opt"] and not pos["und"]
    assert broker.getcash() == pytest.approx(20000 - 300 + 500)


def test_a_physical_call_in_the_money_delivers_the_stock():
    strat, broker, pos = run(UND_UP, PREM, contract())
    assert strat.legs[1:] == [
        ("opt", "exercise", -1, 5.0, 0.0),
        ("und", "delivery", 100, 105.0, 0.0),
    ]
    assert pos["opt"].size == 0
    assert (pos["und"].size, pos["und"].price) == (100, 105.0)
    # 20000 - 300 premium + 500 intrinsic - 10500 for the shares = 9700
    assert broker.getcash() == pytest.approx(9700.0)
    assert broker.getvalue() == pytest.approx(9700 + 100 * 105)


def test_a_put_out_of_the_money_expires_worthless():
    strat, broker, pos = run(UND_UP, PREM, contract("P"))
    assert strat.legs[-1] == ("opt", "expiry", -1, 0.0, 0.0)
    assert strat.trades == [("opt", -300.0)]
    assert not pos["opt"] and not pos["und"]
    assert broker.getvalue() == pytest.approx(19700.0)


def test_a_short_put_in_the_money_is_assigned_the_stock():
    strat, broker, pos = run(UND_DOWN, [4.0] * 5, contract("P"), size=-1)
    # sold for 400; assigned at 100 with the stock at 95: bought back at
    # intrinsic 5 (500) and 100 shares bought at 95 (9500)
    assert strat.legs[1:] == [
        ("opt", "assignment", 1, 5.0, 0.0),
        ("und", "delivery", 100, 95.0, 0.0),
    ]
    assert (pos["und"].size, pos["und"].price) == (100, 95.0)
    assert broker.getcash() == pytest.approx(20000 + 400 - 500 - 9500)
    assert broker.getvalue() == pytest.approx(19900.0)


def test_a_short_call_assigned_without_the_stock_leaves_a_short_position():
    strat, _, pos = run(UND_UP, PREM, contract(), size=-2)
    assert strat.legs[-1] == ("und", "delivery", -200, 105.0, 0.0)
    assert pos["und"].size == -200


def test_settlement_happens_even_when_cash_cannot_pay_for_delivery():
    # 1000 of cash cannot buy 100 shares at 105, but exercise is not an order
    # the broker may refuse
    _, broker, pos = run(UND_UP, PREM, contract(), cash=1000.0)
    assert pos["und"].size == 100
    assert broker.getcash() == pytest.approx(1000 - 300 + 500 - 10500)


def test_commission_and_exercise_fee():
    ci = OptionCommInfo(commission=0.65, exercise_fee=1.5)
    strat, broker, _ = run(UND_UP, PREM, contract(), size=2, comminfo=ci)
    # 2 contracts: 1.30 to buy, 3.00 to exercise, the delivery leg is free
    assert [leg[4] for leg in strat.legs] == [1.3, 3.0, 0.0]
    assert broker.getcash() == pytest.approx(20000 - 600 - 1.3 + 1000 - 3.0 - 21000)


def test_a_worthless_expiry_charges_no_exercise_fee():
    ci = OptionCommInfo(commission=0.65, exercise_fee=1.5)
    strat, _, _ = run(UND_UP, PREM, contract("P"), comminfo=ci)
    assert strat.legs[-1][1:] == ("expiry", -1, 0.0, 0.0)


def test_min_and_max_commission_per_execution():
    ci = OptionCommInfo(commission=0.65, min_commission=1.0, max_commission=5.0)
    assert ci.getcommission(1, 2.0) == 1.0  # 0.65 lifted to the minimum
    assert ci.getcommission(4, 2.0) == pytest.approx(2.6)
    assert ci.getcommission(20, 2.0) == 5.0  # 13.00 capped


def test_an_intraday_contract_settles_on_the_first_bar_after_expiry():
    t = datetime.time
    stamps = [
        datetime.datetime.combine(d, tm)
        for d in (EXPIRY, DAYS[5])
        for tm in (t(10), t(12), t(16))
    ]
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(
        underlying([100, 102, 105, 106, 106, 106], stamps, intraday=True), name="und"
    )
    cerebro.addoption(
        option([3.0, 3.0, 5.0], contract(settlement="cash"), stamps[:3], intraday=True),
        name="opt",
    )
    cerebro.addstrategy(Trader)
    strat = cerebro.run()[0]
    # settled against expiry day's last close (105), not Monday's 106
    assert strat.legs[-1] == ("opt", "exercise", -1, 5.0, 0.0)


def test_an_underlying_that_was_never_added_is_an_error():
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(UND_UP), name="other")
    cerebro.addoption(option(PREM, contract()), name="opt")
    cerebro.addstrategy(Trader)
    with pytest.raises(ValueError, match="'und', which was not added"):
        cerebro.run()


def test_addoption_names_the_feed_after_the_contract():
    cerebro = bt.Cerebro()
    data = cerebro.addoption(option(PREM, contract("P")))
    assert data._name == "und 2006-03-17 100P"
    assert cerebro.broker.getcommissioninfo(data).p.mult == 100.0


def test_addoption_refuses_a_comminfo_with_another_multiplier():
    with pytest.raises(ValueError, match="multiplier"):
        bt.Cerebro().addoption(
            option(PREM, contract()), comminfo=OptionCommInfo(mult=10)
        )


def test_an_option_feed_needs_a_contract():
    cerebro = bt.Cerebro()
    with pytest.raises(ValueError, match="contract"):
        cerebro.addoption(OptionCSVData(**_csv([(DAYS[0], 1.0, 1.0)])))


@pytest.mark.parametrize(
    "kw,match",
    [
        (dict(strike=0), "positive"),
        (dict(right="straddle"), "call or a put"),
        (dict(style="bermudan"), "style"),
        (dict(settlement="barter"), "settlement"),
    ],
)
def test_a_contract_refuses_impossible_terms(kw, match):
    terms = dict(underlying="und", strike=100, expiry="2006-03-17", right="C") | kw
    with pytest.raises(ValueError, match=match):
        OptionContract(**terms)


def test_contract_terms():
    c = OptionContract("und", 100, "2006-03-17", "put", multiplier=10)
    assert c.isput and c.expiry == EXPIRY
    assert (c.intrinsic(90), c.intrinsic(110)) == (10.0, 0.0)
    assert c.years_to_expiry(datetime.date(2006, 3, 7)) == pytest.approx(10 / 365)
    assert c.years_to_expiry(datetime.date(2006, 4, 1)) == 0.0


def test_bid_and_ask_are_lines_and_mid_falls_back_to_close():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(
        {"open": [2.0, 2.1], "high": [2.2, 2.3], "low": [1.9, 2.0],
         "close": [2.1, 2.2], "bid": [2.0, float("nan")], "ask": [2.2, 2.3]},
        index=pd.to_datetime(["2006-03-13", "2006-03-14"]),
    )  # fmt: skip
    seen = []

    class Look(bt.Strategy):
        def next(self):
            opt = self.datas[1]
            seen.append((opt.bid[0], opt.ask[0], opt.mid()))

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(UND_UP), name="und")
    cerebro.addoption(bt.options.OptionPandasData(dataname=frame, contract=contract()))
    cerebro.addstrategy(Look)
    cerebro.run()
    assert seen[0] == (2.0, 2.2, pytest.approx(2.1))
    assert seen[1][2] == 2.2  # bid missing: the close


@pytest.mark.parametrize("runonce", [True, False])
@pytest.mark.parametrize("exactbars", [-2, -1, False, 1])
def test_settlement_is_the_same_in_every_mode(runonce, exactbars):
    cerebro = bt.Cerebro(stdstats=False, runonce=runonce, exactbars=exactbars)
    cerebro.adddata(underlying(UND_UP), name="und")
    cerebro.addoption(option(PREM, contract()), name="opt")
    cerebro.addstrategy(Trader)
    strat = cerebro.run()[0]
    assert strat.legs[1:] == [
        ("opt", "exercise", -1, 5.0, 0.0),
        ("und", "delivery", 100, 105.0, 0.0),
    ]
    # default cash 10000: paid 300, exercised for 500 of intrinsic value
    assert cerebro.broker.getvalue() == pytest.approx(10000 - 300 + 500)
