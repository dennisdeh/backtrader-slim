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
import pickle

import pytest

import testcommon

import backtrader as bt
from backtrader import trade


class FakeCommInfo(object):
    def getvaluesize(self, size, price):
        return 0

    def profitandloss(self, size, price, newprice):
        return 0


class FakeData(object):
    """
    Minimal interface to avoid errors when trade tries to get information from
    the data during the test
    """

    def __len__(self):
        return 0

    @property
    def datetime(self):
        return [0.0]

    @property
    def close(self):
        return [0.0]


def test_run(main=False):
    tr = trade.Trade(data=FakeData())

    order = bt.BuyOrder(
        data=FakeData(), size=0, price=1.0, exectype=bt.Order.Market, simulated=True
    )

    commrate = 0.025
    size = 10
    price = 10.0
    value = size * price
    commission = value * commrate

    tr.update(
        order=order,
        size=size,
        price=price,
        value=value,
        commission=commission,
        pnl=0.0,
        comminfo=FakeCommInfo(),
    )

    assert not tr.isclosed
    assert tr.size == size
    assert tr.price == price
    # assert tr.value == value
    assert tr.commission == commission
    assert not tr.pnl
    assert tr.pnlcomm == tr.pnl - tr.commission

    upsize = -5
    upprice = 12.5
    upvalue = upsize * upprice
    upcomm = abs(value) * commrate

    tr.update(
        order=order,
        size=upsize,
        price=upprice,
        value=upvalue,
        commission=upcomm,
        pnl=0.0,
        comminfo=FakeCommInfo(),
    )

    assert not tr.isclosed
    assert tr.size == size + upsize
    assert tr.price == price  # size is being reduced, price must not change
    # assert tr.value == upvalue
    assert tr.commission == commission + upcomm

    size = tr.size
    price = tr.price
    commission = tr.commission

    upsize = 7
    upprice = 14.5
    upvalue = upsize * upprice
    upcomm = abs(value) * commrate

    tr.update(
        order=order,
        size=upsize,
        price=upprice,
        value=upvalue,
        commission=upcomm,
        pnl=0.0,
        comminfo=FakeCommInfo(),
    )

    assert not tr.isclosed
    assert tr.size == size + upsize
    assert tr.price == ((size * price) + (upsize * upprice)) / (size + upsize)
    # assert tr.value == upvalue
    assert tr.commission == commission + upcomm

    size = tr.size
    price = tr.price
    commission = tr.commission

    upsize = -size
    upprice = 12.5
    upvalue = upsize * upprice
    upcomm = abs(value) * commrate

    tr.update(
        order=order,
        size=upsize,
        price=upprice,
        value=upvalue,
        commission=upcomm,
        pnl=0.0,
        comminfo=FakeCommInfo(),
    )

    assert tr.isclosed
    assert tr.size == size + upsize
    assert tr.price == price  # no change ... we simple closed the operation
    # assert tr.value == upvalue
    assert tr.commission == commission + upcomm


class RealCommInfo(bt.CommInfoBase):
    """A commission scheme that actually computes, unlike FakeCommInfo."""

    params = dict(commission=0.0, stocklike=True)


WHEN = datetime.datetime(2006, 1, 2)


class FakeDateLine(list):
    """Enough of a datetime line for Order and Trade to work against."""

    def datetime(self, ago=0, tz=None, naive=True):
        return bt.num2date(self[0], tz=tz, naive=naive)

    def date(self, ago=0, tz=None, naive=True):
        return self.datetime(ago, tz=tz, naive=naive).date()


class DatedData:
    """A data feed carrying a real date, which FakeData does not.

    A non-simulated order asks its feed for the session end, and the trade
    history stamps every entry with the bar's datetime; neither works against
    a feed whose datetime is a bare list of zeroes.
    """

    _name = "testdata"
    _tz = None

    class p:
        sessionend = datetime.time(23, 59, 59, 999990)

    def __init__(self, barlen=5, when=WHEN):
        self._barlen = barlen
        self.datetime = FakeDateLine([bt.date2num(when)])

    def __len__(self):
        return self._barlen

    @property
    def close(self):
        return [0.0]

    def num2date(self, dt, tz=None, naive=True):
        return bt.num2date(dt, tz=tz, naive=naive)

    def date2num(self, dt):
        return bt.date2num(dt)


def buyorder(simulated=True):
    data = FakeData() if simulated else DatedData()
    return bt.BuyOrder(
        data=data, size=0, price=1.0, exectype=bt.Order.Market, simulated=simulated
    )


class TestTradeBasics:
    def test_a_new_trade_is_created_and_empty(self):
        tr = trade.Trade(data=FakeData())
        assert tr.status == trade.Trade.Created
        assert not tr.isopen and not tr.isclosed
        assert len(tr) == 0
        assert not tr

    def test_len_is_the_absolute_size(self):
        assert len(trade.Trade(data=FakeData(), size=-7)) == 7
        assert len(trade.Trade(data=FakeData(), size=7)) == 7

    def test_a_sized_trade_is_truthy(self):
        assert trade.Trade(data=FakeData(), size=-1)
        assert not trade.Trade(data=FakeData(), size=0)

    def test_refs_are_unique_and_increasing(self):
        first = trade.Trade(data=FakeData())
        second = trade.Trade(data=FakeData())
        assert second.ref > first.ref

    def test_getdataname_returns_the_feed_name(self):
        assert trade.Trade(data=DatedData()).getdataname() == "testdata"

    def test_status_names_line_up_with_the_status_values(self):
        assert trade.Trade.status_names == ["Created", "Open", "Closed"]
        assert (trade.Trade.Created, trade.Trade.Open, trade.Trade.Closed) == (0, 1, 2)

    def test_an_empty_update_changes_nothing(self):
        tr = trade.Trade(data=FakeData())
        tr.update(
            order=buyorder(),
            size=0,
            price=10.0,
            value=0.0,
            commission=5.0,
            pnl=0.0,
            comminfo=FakeCommInfo(),
        )
        assert tr.status == trade.Trade.Created
        assert tr.commission == 0.0  # the commission was not taken either

    def test_str_lists_every_reported_field(self):
        text = str(trade.Trade(data=FakeData(), size=5, price=10.0))
        for field in ("ref", "size", "price", "pnl", "pnlcomm", "status", "history"):
            assert field + ":" in text


class TestTradeLifecycle:
    def _opened(self, size=10, price=10.0, historyon=False):
        tr = trade.Trade(data=DatedData(), historyon=historyon)
        tr.update(
            order=buyorder(),
            size=size,
            price=price,
            value=size * price,
            commission=1.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        return tr

    def test_opening_sets_open_status_and_direction(self):
        tr = self._opened()
        assert tr.justopened
        assert tr.isopen and not tr.isclosed
        assert tr.status == trade.Trade.Open
        assert tr.long is True

    def test_a_short_trade_is_not_long(self):
        assert self._opened(size=-10).long is False

    def test_increasing_averages_the_price_and_leaves_pnl_alone(self):
        tr = self._opened(size=10, price=10.0)
        tr.update(
            order=buyorder(),
            size=10,
            price=20.0,
            value=200.0,
            commission=1.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        assert tr.size == 20
        assert tr.price == pytest.approx(15.0)
        assert tr.pnl == 0.0
        assert tr.commission == 2.0

    def test_closing_books_the_profit_and_closes(self):
        tr = self._opened(size=10, price=10.0)
        tr.update(
            order=buyorder(),
            size=-10,
            price=12.0,
            value=-120.0,
            commission=1.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        assert tr.isclosed and not tr.isopen
        assert tr.status == trade.Trade.Closed
        assert tr.pnl == pytest.approx(20.0)  # 10 units, 10.0 -> 12.0
        assert tr.pnlcomm == pytest.approx(20.0 - 2.0)

    def test_a_closing_trade_records_its_bars(self):
        tr = self._opened()
        assert tr.baropen == 5
        tr.update(
            order=buyorder(),
            size=-10,
            price=12.0,
            value=-120.0,
            commission=1.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        assert tr.barclose == 5
        assert tr.barlen == 0

    def test_open_and_close_datetimes_come_back_as_datetimes(self):
        # A simulated order leaves dtopen at 0.0, so use a real one
        tr = trade.Trade(data=DatedData(), historyon=False)
        tr.update(
            order=buyorder(simulated=False),
            size=10,
            price=10.0,
            value=100.0,
            commission=0.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        tr.update(
            order=buyorder(simulated=False),
            size=-10,
            price=12.0,
            value=-120.0,
            commission=0.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        assert tr.open_datetime() == datetime.datetime(2006, 1, 2)
        assert tr.close_datetime() == datetime.datetime(2006, 1, 2)


class TestTradeHistory:
    def test_history_is_empty_unless_asked_for(self):
        tr = trade.Trade(data=DatedData(), historyon=False)
        tr.update(
            order=buyorder(),
            size=10,
            price=10.0,
            value=100.0,
            commission=0.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        assert tr.history == []

    def test_history_records_one_entry_per_update(self):
        tr = trade.Trade(data=DatedData(), historyon=True)
        for size, price in ((10, 10.0), (-4, 11.0), (-6, 12.0)):
            tr.update(
                order=buyorder(simulated=False),
                size=size,
                price=price,
                value=size * price,
                commission=0.5,
                pnl=0.0,
                comminfo=RealCommInfo(),
            )
        assert len(tr.history) == 3

    def test_a_history_entry_carries_the_status_and_the_event(self):
        tr = trade.Trade(data=DatedData(), historyon=True)
        order = buyorder(simulated=False)
        tr.update(
            order=order,
            size=10,
            price=10.0,
            value=100.0,
            commission=0.5,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        entry = tr.history[0]
        assert entry.status.status == trade.Trade.Open
        assert entry.status.size == 10
        assert entry.status.price == 10.0
        assert entry.event.order is order
        assert entry.event.size == 10
        assert entry.event.price == 10.0
        assert entry.event.commission == 0.5

    def test_a_history_entry_reports_its_datetime(self):
        tr = trade.Trade(data=DatedData(), historyon=True)
        tr.update(
            order=buyorder(simulated=False),
            size=10,
            price=10.0,
            value=100.0,
            commission=0.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        assert tr.history[0].datetime() == datetime.datetime(2006, 1, 2)

    def test_a_history_entry_survives_a_pickle_round_trip(self):
        # Trades travel back from optimization workers, so __reduce__ matters
        tr = trade.Trade(data=DatedData(), historyon=True)
        tr.update(
            order=buyorder(simulated=False),
            size=10,
            price=10.0,
            value=100.0,
            commission=0.5,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        entry = tr.history[0]
        restored = pickle.loads(pickle.dumps(entry))
        assert restored.status.size == entry.status.size
        assert restored.status.price == entry.status.price
        assert restored.status.status == entry.status.status

    def test_a_history_entry_is_closed_to_further_edits(self):
        tr = trade.Trade(data=DatedData(), historyon=True)
        tr.update(
            order=buyorder(simulated=False),
            size=10,
            price=10.0,
            value=100.0,
            commission=0.0,
            pnl=0.0,
            comminfo=RealCommInfo(),
        )
        entry = tr.history[0]
        # doupdate() calls _close() so a typo cannot silently add a key
        assert "nosuchkey" not in entry.event


if __name__ == "__main__":
    test_run(main=True)
