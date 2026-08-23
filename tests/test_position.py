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
from backtrader import position


def test_run(main=False):
    size = 10
    price = 10.0

    pos = position.Position(size=size, price=price)
    assert pos.size == size
    assert pos.price == price

    upsize = 5
    upprice = 12.5
    nsize, nprice, opened, closed = pos.update(size=upsize, price=upprice)

    if main:
        print("pos.size/price", pos.size, pos.price)
        print("nsize, nprice, opened, closed", nsize, nprice, opened, closed)

    assert pos.size == size + upsize
    assert pos.size == nsize
    assert pos.price == ((size * price) + (upsize * upprice)) / pos.size
    assert pos.price == nprice
    assert opened == upsize
    assert not closed

    size = pos.size
    price = pos.price
    upsize = -7
    upprice = 14.5

    nsize, nprice, opened, closed = pos.update(size=upsize, price=upprice)

    if main:
        print("pos.size/price", pos.size, pos.price)
        print("nsize, nprice, opened, closed", nsize, nprice, opened, closed)

    assert pos.size == size + upsize

    assert pos.size == nsize
    assert pos.price == price
    assert pos.price == nprice
    assert not opened
    assert closed == upsize  # the closed must have the sign of "update" size

    size = pos.size
    price = pos.price
    upsize = -15
    upprice = 17.5

    nsize, nprice, opened, closed = pos.update(size=upsize, price=upprice)

    if main:
        print("pos.size/price", pos.size, pos.price)
        print("nsize, nprice, opened, closed", nsize, nprice, opened, closed)

    assert pos.size == size + upsize
    assert pos.size == nsize
    assert pos.price == upprice
    assert pos.price == nprice
    assert opened == size + upsize
    assert closed == -size


class TestSizeAndTruth:
    """len() is the absolute size; truthiness is "holding anything at all"."""

    def test_len_is_absolute_size(self):
        assert len(position.Position(size=7, price=1.0)) == 7
        assert len(position.Position(size=-7, price=1.0)) == 7

    def test_flat_position_is_falsy(self):
        assert not position.Position()
        assert not position.Position(size=0, price=10.0)

    def test_any_open_position_is_truthy(self):
        assert position.Position(size=1, price=1.0)
        assert position.Position(size=-1, price=1.0)

    def test_a_flat_position_prices_at_zero(self):
        # set() nulls the price when the size is 0, whatever price was passed
        assert position.Position(size=0, price=99.0).price == 0.0


class TestClonePseudoUpdateAndFix:
    def test_clone_copies_size_and_price(self):
        pos = position.Position(size=10, price=10.0)
        clone = pos.clone()
        assert (clone.size, clone.price) == (10, 10.0)
        assert clone is not pos

    def test_clone_is_independent_of_the_original(self):
        pos = position.Position(size=10, price=10.0)
        clone = pos.clone()
        clone.update(size=5, price=20.0)
        assert pos.size == 10

    def test_pseudoupdate_leaves_the_original_alone(self):
        pos = position.Position(size=10, price=10.0)
        size, price, opened, closed = pos.pseudoupdate(size=5, price=20.0)
        assert (size, opened, closed) == (15, 5, 0)
        assert price == pytest.approx((10 * 10.0 + 5 * 20.0) / 15)
        assert (pos.size, pos.price) == (10, 10.0)  # untouched

    def test_fix_reports_whether_the_size_was_already_right(self):
        pos = position.Position(size=10, price=10.0)
        assert pos.fix(10, 12.0) is True  # size unchanged -> True
        assert pos.price == 12.0

    def test_fix_reports_a_changed_size(self):
        pos = position.Position(size=10, price=10.0)
        assert pos.fix(4, 12.0) is False
        assert (pos.size, pos.price) == (4, 12.0)


class TestSetOpenedAndClosed:
    """``set`` splits a new size into what it opens and what it closes."""

    def test_growing_a_long(self):
        pos = position.Position(size=5, price=10.0)
        _, _, opened, closed = pos.set(10, 11.0)
        assert (opened, closed) == (5, 0)

    def test_shrinking_a_long(self):
        pos = position.Position(size=10, price=10.0)
        _, _, opened, closed = pos.set(3, 11.0)
        assert (opened, closed) == (0, 7)

    def test_reversing_a_long_into_a_short(self):
        pos = position.Position(size=10, price=10.0)
        _, _, opened, closed = pos.set(-3, 11.0)
        assert (opened, closed) == (-3, 10)

    def test_growing_a_short(self):
        pos = position.Position(size=-5, price=10.0)
        _, _, opened, closed = pos.set(-10, 11.0)
        assert (opened, closed) == (-5, 0)

    def test_shrinking_a_short(self):
        pos = position.Position(size=-10, price=10.0)
        _, _, opened, closed = pos.set(-3, 11.0)
        assert (opened, closed) == (0, -7)

    def test_reversing_a_short_into_a_long(self):
        pos = position.Position(size=-10, price=10.0)
        _, _, opened, closed = pos.set(3, 11.0)
        assert (opened, closed) == (3, -10)

    def test_setting_from_flat_reports_nothing_opened(self):
        """Pins current behaviour, which looks wrong - see reports/OPEN_ITEMS.md.

        Every other branch of ``set`` reports what it opened, and ``update``
        reports ``opened == size`` when it opens from flat. This branch reads
        ``self.upopened = self.size`` - the *old* size, always 0 here - where
        its siblings would say ``size``. Nothing in the library reads
        ``upopened`` outside ``Position`` itself, so the oddity is inert; the
        assertion is here so that correcting it is a deliberate act with a
        changelog entry, not an accident.
        """
        pos = position.Position()
        _, _, opened, closed = pos.set(5, 11.0)
        assert (opened, closed) == (0, 0)


class TestUpdateFromShort:
    """The short-side branches of ``update``, mirroring the long-side ones."""

    def test_increasing_a_short_averages_the_price(self):
        pos = position.Position(size=-10, price=10.0)
        size, price, opened, closed = pos.update(size=-10, price=20.0)
        assert (size, opened, closed) == (-20, -10, 0)
        assert price == pytest.approx(15.0)

    def test_reducing_a_short_keeps_the_price(self):
        pos = position.Position(size=-10, price=10.0)
        size, price, opened, closed = pos.update(size=4, price=20.0)
        assert (size, price, opened, closed) == (-6, 10.0, 0, 4)

    def test_closing_a_short_nulls_the_price(self):
        pos = position.Position(size=-10, price=10.0)
        size, price, opened, closed = pos.update(size=10, price=20.0)
        assert (size, price, opened, closed) == (0, 0.0, 0, 10)

    def test_reversing_a_short_takes_the_new_price(self):
        pos = position.Position(size=-10, price=10.0)
        size, price, opened, closed = pos.update(size=15, price=20.0)
        assert (size, price, opened, closed) == (5, 20.0, 5, 10)

    def test_opening_a_short_from_flat(self):
        pos = position.Position()
        size, price, opened, closed = pos.update(size=-5, price=20.0)
        assert (size, price, opened, closed) == (-5, 20.0, -5, 0)

    def test_update_records_the_datetime_it_was_given(self):
        pos = position.Position(size=10, price=10.0)
        when = datetime.datetime(2006, 1, 2)
        pos.update(size=5, price=11.0, dt=when)
        assert pos.datetime == when


class TestPositionText:
    def test_str_reports_the_position_state(self):
        pos = position.Position(size=10, price=10.0)
        pos.update(size=-4, price=12.0)
        text = str(pos)
        assert "--- Position Begin" in text
        assert "--- Position End" in text
        assert "- Size: 6" in text
        assert "- Price: 10.0" in text
        assert "- Closed: -4" in text
        assert "- Opened: 0" in text


if __name__ == "__main__":
    test_run(main=True)
