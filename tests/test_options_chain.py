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
"""Chain-native options: OptionChain, ContractView and the chain sources.

The hand-written chain below has three contracts on the 2006-03-17 expiry,
quoted for the five days the underlying of test_options_settlement rises
from 100 to 105. Every expected price is read off it.
"""

import datetime
import itertools
import math

import pytest

np = pytest.importorskip("numpy")

import backtrader as bt  # noqa: E402
from backtrader.options import (  # noqa: E402
    CashCovered,
    CSVChainSource,
    ModelChainSource,
    OptionChain,
    PandasChainSource,
    PartitionedChainSource,
    StructureTrades,
    pricing,
)
from backtrader.options.chain import third_friday  # noqa: E402

from conftest import csvdata  # noqa: E402
from test_options_settlement import DAYS, EXPIRY, UND_UP, underlying  # noqa: E402

# (day index, strike, right, bid, ask): C105 is not quoted on day 3
QUOTES = [
    (i, k, r, b + i * 0.5, b + i * 0.5 + 0.2)
    for i in range(5)
    for k, r, b in ((100, "C", 3.0), (100, "P", 2.0), (105, "C", 1.0))
    if not (k == 105 and i == 2)
]


def rows():
    return [
        dict(date=DAYS[i], expiry=EXPIRY, strike=float(k), right=r, bid=b, ask=a)
        for i, k, r, b, a in QUOTES
    ]


def pandas_source(**kw):
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(rows())
    frame["date"] = pd.to_datetime(frame["date"])
    frame["expiry"] = pd.to_datetime(frame["expiry"])
    return PandasChainSource(frame, **kw)


def csv_source(tmp_path):
    path = tmp_path / "chain.csv"
    with open(path, "w") as f:
        f.write("date,expiry,strike,right,bid,ask\n")
        for r in rows():
            f.write(
                f"{r['date']},{r['expiry']},{r['strike']},{r['right']},{r['bid']},{r['ask']}\n"
            )
    return CSVChainSource(str(path))


class Watch(bt.Strategy):
    """Records chosen contracts' bars; runs ``plan(self, chain)`` on bar 1."""

    params = (("plan", None), ("watch", ()))

    def start(self):
        self.seen = []
        self.done = []
        self.views = []

    def next(self):
        chain = self.getchain("und")
        if len(self) == 1:
            self.views = [chain.contract(EXPIRY, k, r) for k, r in self.p.watch]
            if self.p.plan:
                self.p.plan(self, chain)
        self.seen.append(tuple((len(v), v.close[0]) for v in self.views))

    def notify_order(self, order):
        if order.status in (order.Completed, order.Margin):
            self.done.append(
                (
                    order.data._name,
                    order.getstatusname(),
                    order.executed.size,
                    round(order.executed.price, 4),
                    order.info.get("settlement"),
                )
            )


def run(source, plan=None, watch=(), settlement="cash", cash=100_000.0, **kw):
    cerebro = bt.Cerebro(stdstats=False, **kw.pop("cerebro", {}))
    und = underlying(UND_UP)
    cerebro.adddata(und, name="und")
    cerebro.addchain(OptionChain(und, source, settlement=settlement))
    cerebro.broker.setcash(cash)
    for name, value in kw.items():
        getattr(cerebro.broker, name)(value)
    cerebro.addstrategy(Watch, plan=plan, watch=watch)
    return cerebro, cerebro.run()[0]


def test_a_view_follows_its_contracts_quotes():
    _, s = run(pandas_source(), watch=[(100, "C")])
    # mark = mid: 3.1, 3.6, 4.1, 4.6, 5.1 over the five quoted days
    assert [v[0] for v in s.seen[:5]] == [
        (1, pytest.approx(3.1)),
        (2, pytest.approx(3.6)),
        (3, pytest.approx(4.1)),
        (4, pytest.approx(4.6)),
        (5, pytest.approx(5.1)),
    ]


def test_a_day_without_a_quote_is_no_bar():
    _, s = run(pandas_source(), watch=[(105, "C")])
    # unquoted on day 3: the bar count stalls, the last price stays
    assert [v[0][0] for v in s.seen[:5]] == [1, 2, 2, 3, 4]
    assert s.seen[2][0][1] == pytest.approx(s.seen[1][0][1])


def test_an_order_waits_for_the_contracts_next_quoted_bar():
    class Late(Watch):
        def next(self):
            super().next()
            if len(self) == 2:
                self.buy(data=self.views[0])

    cerebro = bt.Cerebro(stdstats=False)
    und = underlying(UND_UP)
    cerebro.adddata(und, name="und")
    cerebro.addchain(OptionChain(und, pandas_source(), settlement="cash"))
    cerebro.broker.setcash(100_000.0)
    cerebro.addstrategy(Late, watch=[(105, "C")])
    s = cerebro.run()[0]
    # sent on day 2; day 3 has no quote; filled on day 4 at its mark (2.6)
    assert s.done[0][:4] == ("und 2006-03-17 105C", "Completed", 1, 2.6)


def test_a_bought_call_settles_at_expiry():
    def plan(strat, chain):
        strat.buy(data=chain.contract(EXPIRY, 100, "C"), size=2)

    cerebro, s = run(pandas_source(), plan=plan)
    # bought on day 2 at 3.6; the underlying closes at 105 on expiry: 5.0
    assert s.done == [
        ("und 2006-03-17 100C", "Completed", 2, 3.6, None),
        ("und 2006-03-17 100C", "Completed", -2, 5.0, "exercise"),
    ]
    assert cerebro.broker.getvalue() == pytest.approx(100_000 + 2 * 100 * (5.0 - 3.6))


def test_a_csv_chain_gives_the_same_as_a_pandas_one(tmp_path):
    def plan(strat, chain):
        strat.buy(data=chain.contract(EXPIRY, 105, "C"))

    _, a = run(pandas_source(), plan=plan, watch=[(100, "P")])
    _, b = run(csv_source(tmp_path), plan=plan, watch=[(100, "P")])
    assert (a.seen, a.done) == (b.seen, b.done)


def test_a_dte_window_drops_contracts_up_front():
    # on day 1 the expiry is 4 days away: dte=(10, 60) leaves nothing
    _, s = run(
        pandas_source(dte=(10, 60)),
        plan=lambda st, ch: st.done.append(ch.contract(EXPIRY, 100, "C")),
    )
    assert s.done == [None]


def test_a_partitioned_source_loads_one_period_at_a_time():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(rows())
    frame["date"] = pd.to_datetime(frame["date"])
    loads = []

    def load(period):
        loads.append(period)
        months = frame["date"].dt.month
        return frame[months == period[1]]

    _, s = run(PartitionedChainSource(load, period="month"), watch=[(100, "C")])
    assert loads == [(2006, 3)]
    assert s.seen[4][0][1] == pytest.approx(5.1)


def test_structure_trades_follows_a_delivery_from_a_chain_contract():
    # the contract is a ContractView, not a cerebro feed: the analyzer must
    # find it by the orders it saw, not by cerebro's feed names
    def plan(strat, chain):
        strat.combo([(chain.contract(EXPIRY, 100, "C"), 1)])

    cerebro = bt.Cerebro(stdstats=False)
    und = underlying(UND_UP)
    cerebro.adddata(und, name="und")
    cerebro.addchain(OptionChain(und, pandas_source(), settlement="physical"))
    cerebro.broker.setcash(100_000.0)
    cerebro.addanalyzer(StructureTrades)
    cerebro.addstrategy(Watch, plan=plan)
    s = cerebro.run()[0]
    ((_, result),) = s.analyzers[0].get_analysis().items()
    # bought at 3.6, exercised: 100 units delivered at 105, still held
    assert result["closed"] is None
    assert sorted(result["legs"]) == ["und", "und 2006-03-17 100C"]


def test_quote_fills_and_margin_apply_to_chain_contracts():
    def plan(strat, chain):
        strat.sell(data=chain.contract(EXPIRY, 100, "C"))  # naked: refused
        strat.buy(data=chain.contract(EXPIRY, 105, "C"))

    _, s = run(
        pandas_source(),
        plan=plan,
        set_margin_model=CashCovered(),
        set_quotefill=1.0,
    )
    assert s.done[0][:2] == ("und 2006-03-17 100C", "Margin")
    # the 105 call fills on day 2, quoted 1.5 / 1.7: crossing, at the ask
    assert s.done[1][:4] == ("und 2006-03-17 105C", "Completed", 1, 1.7)


# --- the model chain and selection -------------------------------------


def model_run(plan=None, **kw):
    cerebro = bt.Cerebro(stdstats=False, **kw)
    und = csvdata()
    cerebro.adddata(und, name="und")
    source = ModelChainSource(strikestep=10, rate=0.03, months=3)
    cerebro.addchain(OptionChain(und, source, settlement="cash", rate=0.03))
    cerebro.broker.setcash(1e6)

    class Model(bt.Strategy):
        def start(self):
            self.out = []

        def next(self):
            if len(self) == 30:
                self.out.append(plan(self, self.getchain("und")))

    cerebro.addstrategy(Model)
    return cerebro.run()[0].out[0]


def test_the_model_chain_lists_monthly_expiries_and_a_strike_grid():
    def look(strat, chain):
        return (
            chain.expiries(),
            chain.strikes(chain.expiries()[0], "P"),
            strat.data.close[-1],
        )

    expiries, strikes, prev = model_run(look)
    # 2006-02-13 is bar 30: the third Fridays of February, March, April
    assert expiries == [third_friday(2006, m) for m in (2, 3, 4)]
    assert min(strikes) >= prev * 0.8 - 10 and max(strikes) <= prev * 1.2 + 10
    assert all(k % 10 == 0 for k in strikes)


def test_model_chain_prices_are_black_scholes_at_realised_volatility():
    def look(strat, chain):
        e = chain.expiries()[1]
        v = chain.contract(e, chain.strikes(e, "C")[10], "C")
        closes = [strat.data.close[-k] for k in range(22, 0, -1)]
        rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
        mean = sum(rets) / len(rets)
        sigma = math.sqrt(sum((x - mean) ** 2 for x in rets) / (len(rets) - 1) * 252)
        T = (e - strat.data.datetime.date(0)).days / 365
        want = pricing.bsm("C", strat.data.close[0], v.contract.strike, T, 0.03, sigma)
        return v.close[0], want.price

    got, want = model_run(look)
    assert got == pytest.approx(want, rel=1e-9)


def test_select_by_moneyness_and_by_delta():
    def look(strat, chain):
        spot = strat.data.close[0]
        by_m = chain.select("P", dte=(20, 60), moneyness=0.95)
        by_d = chain.select("P", dte=(20, 60), delta=-0.25)
        e = by_d.contract.expiry
        T = (e - strat.data.datetime.date(0)).days / 365
        deltas = {}
        for k in chain.strikes(e, "P"):
            m = chain.contract(e, k, "P").close[0]
            iv = pricing.implied_vol(m, "P", spot, k, T, 0.03)
            if iv == iv:
                deltas[k] = pricing.bsm("P", spot, k, T, 0.03, iv).delta
        nearest = min(deltas, key=lambda k: abs(deltas[k] + 0.25))
        return (
            by_m.contract.strike,
            round(spot * 0.95, -1),
            by_d.contract.strike,
            nearest,
        )

    m_strike, m_want, d_strike, d_want = model_run(look)
    assert abs(m_strike - m_want) <= 10
    assert d_strike == d_want


@pytest.mark.parametrize(
    "runonce,preload", list(itertools.product((True, False), repeat=2))
)
def test_every_mode_selects_and_prices_alike(runonce, preload):
    def look(strat, chain):
        v = chain.select("C", dte=(20, 60), delta=0.30)
        return v._name, round(v.close[0], 6), len(chain.snapshot)

    assert model_run(look, runonce=runonce, preload=preload) == model_run(look)


def test_select_takes_one_target():
    with pytest.raises(ValueError, match="one of them"):
        model_run(lambda s, c: c.select("C", delta=0.3, moneyness=1.0))


def test_addchain_refuses_another_multiplier():
    from backtrader.options import OptionCommInfo

    und = underlying(UND_UP)
    with pytest.raises(ValueError, match="multiplier"):
        bt.Cerebro().addchain(
            OptionChain(und, ModelChainSource()), comminfo=OptionCommInfo(mult=10)
        )
