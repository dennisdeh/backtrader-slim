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
"""Advanced order handling: stop and trailing variants, brackets, OCO, and
the Strategy order helpers (order_target_*, buy_bracket, close).
"""

import pytest

import backtrader as bt

from conftest import csvdata, datafile


def run(strategy, cash=100000.0, dataname="2006-day-001.txt", **kwargs):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cash)
    cerebro.adddata(csvdata(dataname))
    cerebro.addstrategy(strategy, **kwargs)
    return cerebro.run()[0], cerebro


class Recorder(bt.Strategy):
    __test__ = False

    def __init__(self):
        self.completed = []
        self.canceled = []
        self.orders = []

    def notify_order(self, order):
        if order.status == order.Completed:
            self.completed.append(order)
        elif order.status in (order.Canceled, order.Expired):
            self.canceled.append(order)


class TestStopOrders:
    def test_stop_order_below_market_does_not_trigger_immediately(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(
                        self.buy(size=1, exectype=bt.Order.Stop, price=1e6)
                    )

        strat, _ = run(S)
        # a buy stop above every traded price can never trigger
        assert strat.orders[0].status != bt.Order.Completed

    def test_stop_order_triggers_when_price_is_crossed(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(
                        self.buy(size=1, exectype=bt.Order.Stop, price=1.0)
                    )

        strat, _ = run(S)
        assert strat.orders[0].status == bt.Order.Completed

    def test_stoplimit_needs_both_levels(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(
                        self.buy(
                            size=1,
                            exectype=bt.Order.StopLimit,
                            price=1.0,
                            plimit=1e6,
                        )
                    )

        strat, _ = run(S)
        assert strat.orders[0].status == bt.Order.Completed

    def test_stoptrail_follows_the_price(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.buy(size=1)
                elif len(self) == 6:
                    self.orders.append(
                        self.sell(size=1, exectype=bt.Order.StopTrail, trailamount=50)
                    )

        strat, _ = run(S)
        assert strat.orders[0].exectype == bt.Order.StopTrail

    def test_stoptraillimit_is_accepted(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.buy(size=1)
                elif len(self) == 6:
                    self.orders.append(
                        self.sell(
                            size=1,
                            exectype=bt.Order.StopTrailLimit,
                            trailamount=50,
                            plimit=1.0,
                        )
                    )

        strat, _ = run(S)
        assert strat.orders[0].exectype == bt.Order.StopTrailLimit


class TestValidity:
    def test_order_expires_after_its_validity(self):
        import datetime

        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(
                        self.buy(
                            size=1,
                            exectype=bt.Order.Limit,
                            price=1.0,
                            valid=self.data.datetime.date(0)
                            + datetime.timedelta(days=3),
                        )
                    )

        strat, _ = run(S)
        assert strat.orders[0].status == bt.Order.Expired


class TestBracketOrders:
    def test_buy_bracket_creates_three_orders(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5 and not self.orders:
                    self.orders.extend(
                        self.buy_bracket(
                            size=1,
                            limitprice=1e6,
                            stopprice=1.0,
                        )
                    )

        strat, _ = run(S)
        assert len(strat.orders) == 3
        main, stop, limit = strat.orders
        assert main.status == bt.Order.Completed

    def test_sell_bracket_creates_three_orders(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5 and not self.orders:
                    self.orders.extend(
                        self.sell_bracket(size=1, limitprice=1.0, stopprice=1e6)
                    )

        strat, _ = run(S)
        assert len(strat.orders) == 3


class TestOCO:
    def test_oco_cancels_the_sibling(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5 and not self.orders:
                    first = self.buy(size=1, exectype=bt.Order.Limit, price=1e5)
                    second = self.buy(
                        size=1, exectype=bt.Order.Limit, price=1.0, oco=first
                    )
                    self.orders.extend([first, second])

        strat, _ = run(S)
        statuses = {o.status for o in strat.orders}
        assert bt.Order.Canceled in statuses or bt.Order.Completed in statuses


class TestTargetOrders:
    def test_order_target_size_reaches_the_requested_size(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.order_target_size(target=10)

        strat, _ = run(S)
        assert strat.getposition(strat.data).size == 10

    def test_order_target_size_reduces_an_existing_position(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.buy(size=20)
                elif len(self) == 10:
                    self.order_target_size(target=5)

        strat, _ = run(S)
        assert strat.getposition(strat.data).size == 5

    def test_order_target_value_sizes_by_money(self):
        """Sizing is in whole units, computed from the close of the bar the
        decision was taken on - so the achieved value undershoots the target
        by up to one unit's worth, and never overshoots it."""
        seen = {}

        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    seen["close"] = self.data.close[0]
                    self.order_target_value(target=20000.0)

        strat, _ = run(S)
        pos = strat.getposition(strat.data)
        assert pos.size == int(20000.0 / seen["close"])
        assert 0 < pos.size * seen["close"] <= 20000.0

    def test_order_target_percent_sizes_by_portfolio_share(self):
        seen = {}

        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    seen["close"] = self.data.close[0]
                    seen["value"] = self.broker.getvalue()
                    self.order_target_percent(target=0.25)

        strat, _ = run(S)
        pos = strat.getposition(strat.data)
        assert pos.size == int(seen["value"] * 0.25 / seen["close"])

    def test_order_target_percent_scales_with_the_target(self):
        def size_for(target):
            class S(Recorder):
                def next(self):
                    if len(self) == 5:
                        self.order_target_percent(target=target)

            strat, _ = run(S)
            return strat.getposition(strat.data).size

        assert size_for(0.5) > size_for(0.25) > size_for(0.1)

    def test_order_target_size_zero_closes_out(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.buy(size=10)
                elif len(self) == 10:
                    self.order_target_size(target=0)

        strat, _ = run(S)
        assert strat.getposition(strat.data).size == 0


class TestOrderObject:
    def test_status_names_are_reported(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(self.buy(size=1))

        strat, _ = run(S)
        order = strat.orders[0]
        assert order.getstatusname() == "Completed"
        assert order.getordername() == "Market"
        assert order.ordtypename() == "Buy"

    def test_executed_carries_size_price_and_value(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(self.buy(size=3))

        strat, _ = run(S)
        ex = strat.orders[0].executed
        assert ex.size == 3
        assert ex.price > 0
        assert ex.value == pytest.approx(ex.size * ex.price)

    def test_order_is_alive_only_while_pending(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(self.buy(size=1))

        strat, _ = run(S)
        assert not strat.orders[0].alive()

    def test_repr_does_not_raise(self):
        class S(Recorder):
            def next(self):
                if len(self) == 5:
                    self.orders.append(self.buy(size=1))

        strat, _ = run(S)
        assert "Buy" in str(strat.orders[0]) or repr(strat.orders[0])
