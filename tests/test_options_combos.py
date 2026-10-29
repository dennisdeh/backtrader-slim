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
"""Stage 4 of the options work: margin, combo orders, and the book's view.

The feeds are the in-memory ones of test_options_settlement: an underlying
at 100 rising to 105 on expiry day (2006-03-17), and options whose premiums
each test sets. Every expectation is worked out in the comment beside it.
"""

import math

import pytest

import backtrader as bt
from backtrader.options import (
    CashCovered,
    OptionContract,
    PortfolioGreeks,
    StructureTrades,
    pricing,
)

from test_options_settlement import DAYS, EXPIRY, UND_UP, option, underlying


def contract(right="C", strike=100.0, settlement="cash", expiry=EXPIRY):
    return OptionContract("und", strike, expiry, right, settlement=settlement)


class Plan(bt.Strategy):
    """Runs ``plan(self)`` on bar 1 and records what happens."""

    params = (("plan", None), ("withdraw", 0.0))

    def start(self):
        self.done = []
        self.calls = []

    def notify_order(self, order):
        if order.status in (order.Completed, order.Margin, order.Canceled):
            self.done.append(
                (
                    order.data._name,
                    order.getstatusname(),
                    order.executed.size,
                    order.executed.price,
                    order.info.get("combo"),
                )
            )

    def notify_margin(self, call):
        self.calls.append(call)

    def next(self):
        if len(self) == 1:
            self.p.plan(self)
        if len(self) == 3 and self.p.withdraw:
            self.broker.add_cash(-self.p.withdraw)


def run(plan, options, cash=20000.0, model=True, withdraw=0.0, und=UND_UP, **extra):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(underlying(und), name="und")
    for name, (premiums, ctr) in options.items():
        cerebro.addoption(option(premiums, ctr), name=name)
    cerebro.broker.setcash(cash)
    if model:
        cerebro.broker.set_margin_model(CashCovered())
    for cls, kw in extra.get("observers", ()):
        cerebro.addobserver(cls, **kw)
    for cls, kw in extra.get("analyzers", ()):
        cerebro.addanalyzer(cls, **kw)
    cerebro.addstrategy(Plan, plan=plan, withdraw=withdraw)
    return cerebro, cerebro.run()[0]


def sell(name, size=1):
    return lambda s: s.sell(data=s.getdatabyname(name), size=size)


CALL = {"c100": ([5.0] * 5, contract())}
PUT = {"p100": ([4.0] * 5, contract("P"))}


# --- the margin model on its own -------------------------------------------


class _Feed:
    """Just enough of a feed for CashCovered: a name or a contract."""

    def __init__(self, name=None, contract=None):
        self._name = name
        self.contract = contract


def requirement(positions):
    return CashCovered().requirement(None, positions)


STOCK = _Feed("und")


def opt(right, strike, expiry=EXPIRY):
    return _Feed(contract=contract(right, strike, expiry=expiry))


def test_a_naked_short_call_is_not_allowed():
    assert requirement({opt("C", 100): -1}) == math.inf


def test_a_call_covered_by_stock_anywhere_reserves_nothing():
    assert requirement({STOCK: 100, opt("C", 100): -1}) == 0.0
    # 150 units cover one contract, not two
    assert requirement({STOCK: 150, opt("C", 100): -2}) == math.inf


def test_a_call_covered_by_a_long_call_reserves_the_gap_above_its_strike():
    # long 100 / short 110: a debit spread, no extra risk
    assert requirement({opt("C", 100): 1, opt("C", 110): -1}) == 0.0
    # long 110 / short 100: at worst it loses 10 x 100
    assert requirement({opt("C", 110): 1, opt("C", 100): -1}) == 1000.0


def test_a_long_call_expiring_first_does_not_cover():
    early = opt("C", 90, expiry=DAYS[2])
    assert requirement({early: 1, opt("C", 100): -1}) == math.inf


def test_a_short_put_is_cash_secured_or_reserves_the_spread():
    assert requirement({opt("P", 100): -2}) == 2 * 100 * 100
    # short 100 / long 90: at worst 10 x 100
    assert requirement({opt("P", 100): -1, opt("P", 90): 1}) == 1000.0


def test_long_positions_reserve_nothing():
    assert requirement({STOCK: 100, opt("C", 100): 3, opt("P", 90): 2}) == 0.0


# --- the broker with a margin model ----------------------------------------


def test_without_a_model_a_naked_call_is_sold_as_before():
    _, strat = run(sell("c100"), CALL, model=False)
    assert strat.done[0][:3] == ("c100", "Completed", -1)


def test_with_cashcovered_a_naked_call_is_refused():
    _, strat = run(sell("c100"), CALL)
    assert strat.done == [("c100", "Margin", 0, 0.0, None)]


def test_stock_bought_in_the_same_bar_covers_the_call():
    def plan(s):
        s.buy(data=s.getdatabyname("und"), size=100)
        s.sell(data=s.getdatabyname("c100"), size=1)

    _, strat = run(plan, CALL)
    assert [d[:2] for d in strat.done[:2]] == [
        ("und", "Completed"),
        ("c100", "Completed"),
    ]


def test_a_put_is_sold_only_while_cash_secures_its_strike():
    # one put reserves 100 x 100 = 10,000; three would reserve 30,000
    _, one = run(sell("p100"), PUT, cash=20000.0)
    _, three = run(sell("p100", 3), PUT, cash=20000.0)
    assert one.done[0][:2] == ("p100", "Completed")
    assert three.done == [("p100", "Margin", 0, 0.0, None)]


def test_a_refused_order_leaves_nothing_behind_for_the_next():
    # the naked call is refused; the put after it must be judged without it
    def plan(s):
        s.sell(data=s.getdatabyname("c100"), size=1)
        s.sell(data=s.getdatabyname("p100"), size=1)

    _, strat = run(plan, CALL | PUT)
    assert [d[:2] for d in strat.done[:2]] == [
        ("c100", "Margin"),
        ("p100", "Completed"),
    ]


def test_a_shortfall_after_a_bar_is_reported_not_acted_on():
    # a put reserves 10,000; 12,000 + 400 premium, less 5,000 withdrawn on
    # bar 3, leaves 7,400: 2,600 short
    _, strat = run(sell("p100"), PUT, cash=12000.0, withdraw=5000.0)
    assert strat.calls, "notify_margin was never called"
    call = strat.calls[0]
    assert (call.requirement, call.cash, call.shortfall) == (10000.0, 7400.0, 2600.0)
    assert strat.done[0][:2] == ("p100", "Completed")  # nothing was closed


# --- combo orders ---------------------------------------------------------

SPREAD = {"c100": ([5.0] * 5, contract()), "c105": ([3.0] * 5, contract("C", 105.0))}


def bull_spread(s):
    s.combo([("c100", 1), ("c105", -1)])


def test_a_spread_too_dear_leg_by_leg_fills_as_a_combo():
    # 300 of cash: buying the 100 call alone (500) is refused, as the
    # report's experiment E5 showed; as one combo the net debit is 200
    _, legs = run(
        lambda s: s.buy(data=s.getdatabyname("c100")), SPREAD, cash=300.0, model=False
    )
    assert legs.done[0][:2] == ("c100", "Margin")

    _, combo = run(bull_spread, SPREAD, cash=300.0, model=False)
    filled = [d for d in combo.done if d[1] == "Completed" and d[4] is not None]
    assert [(d[0], d[2], d[3]) for d in filled] == [("c100", 1, 5.0), ("c105", -1, 3.0)]
    assert filled[0][4] == filled[1][4]  # one combo reference


def test_a_combo_cash_cannot_cover_fills_no_leg():
    _, strat = run(bull_spread, SPREAD, cash=100.0, model=False)
    assert [(d[0], d[1]) for d in strat.done] == [
        ("c100", "Margin"),
        ("c105", "Margin"),
    ]


def test_a_combo_is_judged_by_the_margin_model_as_a_whole():
    # a short 100 call covered by a long 105 call reserves the 5-point gap
    def plan(s):
        s.combo([("c105", 1), ("c100", -1)])

    _, enough = run(plan, SPREAD, cash=1000.0)
    # 250 - 300 for the long call + 500 for the short one = 450 < 500
    _, short = run(plan, SPREAD, cash=250.0)
    assert [d[1] for d in enough.done[:2]] == ["Completed", "Completed"]
    assert [d[1] for d in short.done] == ["Margin", "Margin"]


def test_a_combo_leg_needs_a_size():
    with pytest.raises(ValueError, match="size"):
        run(lambda s: s.combo([("c100", 0)]), CALL)


# --- the book's view ------------------------------------------------------


def test_structure_trades_reports_a_spread_through_its_settlement():
    cerebro, strat = run(
        bull_spread, SPREAD, model=False, analyzers=[(StructureTrades, {})]
    )
    ((ref, s),) = strat.analyzers[0].get_analysis().items()
    # paid 500, received 300; at 105 the 100 call settles for 500 and the
    # 105 call for nothing: 500 - 500 + 300 - 0 = +300
    assert s["pnl"] == pytest.approx(300.0)
    assert sorted(s["legs"]) == ["c100", "c105"]
    assert s["opened"] == DAYS[1] and s["closed"] == EXPIRY
    assert s["worst"] <= 0.0 <= s["pnl"] <= s["best"]
    assert cerebro.broker.getvalue() == pytest.approx(20000.0 + 300.0)


def test_structure_trades_follows_a_delivery_into_the_stock():
    # a covered call assigned physically: the 100 units go away at 105
    def plan(s):
        s.combo([("und", 100), ("c100", -1)])

    options = {"c100": ([5.0] * 5, contract(settlement="physical"))}
    _, strat = run(plan, options, analyzers=[(StructureTrades, {})])
    ((ref, s),) = strat.analyzers[0].get_analysis().items()
    # 100 units bought at bar 2's open (101), the call sold for 500; then
    # assigned: the call bought back at 5 (500), the units delivered at 105
    assert s["closed"] == EXPIRY
    assert s["pnl"] == pytest.approx(-100 * 101 + 500 - 500 + 100 * 105)


def test_portfolio_greeks_add_up_the_book_in_money():
    def plan(s):
        s.buy(data=s.getdatabyname("und"), size=100)
        s.buy(data=s.getdatabyname("c100"), size=2)

    premiums = [3.0, 3.2, 3.6, 4.1, 5.0]
    cerebro, strat = run(
        plan,
        {"c100": (premiums, contract())},
        model=False,
        observers=[(PortfolioGreeks, dict(rate=0.03))],
    )
    obs = [o for o in strat.getobservers() if isinstance(o, PortfolioGreeks)][0]
    # bar 3 (2006-03-15): underlying 102, the call at 3.6, 2 days to expiry
    i = 2
    S, P, T = 102.0, 3.6, 2 / 365
    iv = pricing.implied_vol(P, "C", S, 100.0, T, 0.03)
    g = pricing.bsm("C", S, 100.0, T, 0.03, iv)
    units = 2 * 100
    assert obs.delta.array[i] == pytest.approx(100 * S + units * g.delta * S)
    assert obs.gamma.array[i] == pytest.approx(units * g.gamma * S * S / 100)
    assert obs.vega.array[i] == pytest.approx(units * g.vega / 100)
    assert obs.theta.array[i] == pytest.approx(units * g.theta / 365)


def test_structure_trades_waits_for_the_delivery_after_an_exercise():
    # a lone call exercised physically: the option is flat after the
    # exercise leg, but the delivery that follows makes the structure
    # 100 units long - it is not closed
    def plan(s):
        s.combo([("c100", 1)])

    options = {"c100": ([5.0] * 5, contract(settlement="physical"))}
    _, strat = run(plan, options, analyzers=[(StructureTrades, {})])
    ((ref, s),) = strat.analyzers[0].get_analysis().items()
    assert s["closed"] is None
    assert sorted(s["legs"]) == ["c100", "und"]
