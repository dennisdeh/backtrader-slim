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
"""Unit tests for backtrader.utils: date conversion, the dict helpers and
the numeric helpers in mathsupport.

These are leaf utilities with no engine dependencies, so they are tested
directly rather than through a Cerebro run.
"""

import datetime
import math

import pytest

import backtrader as bt
from backtrader.utils import AutoDict, AutoOrderedDict, OrderedDefaultdict
from backtrader.utils.date import date2num, num2date, num2time, time2num
from backtrader.utils.dateintern import TZLocal, tzparse
from backtrader import mathsupport


class TestDateConversion:
    def test_roundtrip_datetime(self):
        dt = datetime.datetime(2006, 5, 17, 14, 30, 15)
        assert num2date(date2num(dt)) == dt

    def test_roundtrip_keeps_sub_second_resolution(self):
        # dates are floats in days, so a microsecond is ~1.16e-11 of the
        # value; the round trip is exact to well under a millisecond
        dt = datetime.datetime(2006, 5, 17, 14, 30, 15, 123456)
        back = num2date(date2num(dt))
        assert abs((back - dt).total_seconds()) < 1e-4

    def test_ordering_is_monotonic(self):
        a = date2num(datetime.datetime(2006, 1, 1))
        b = date2num(datetime.datetime(2006, 1, 2))
        c = date2num(datetime.datetime(2006, 1, 2, 12))
        assert a < b < c

    def test_one_day_is_one_unit(self):
        a = date2num(datetime.datetime(2006, 1, 1))
        b = date2num(datetime.datetime(2006, 1, 2))
        assert b - a == pytest.approx(1.0)

    def test_time2num_is_the_fractional_part(self):
        assert time2num(datetime.time(12, 0)) == pytest.approx(0.5)
        assert time2num(datetime.time(0, 0)) == pytest.approx(0.0)

    def test_num2time_drops_the_date(self):
        num = date2num(datetime.datetime(2006, 5, 17, 6, 15))
        assert num2time(num) == datetime.time(6, 15)

    def test_tzparse_accepts_a_timezone_name(self):
        """Regression: tzparse('UTC') raised AttributeError when pytz was
        absent, because the fallback handed the *string* to Localizer, which
        assigns an attribute onto it. pytz is not a dependency of this fork,
        so the string form has to work off the standard library."""
        tz = tzparse("UTC")
        assert tz is not None
        dt = datetime.datetime(2006, 1, 1, 12, 0)
        assert tz.utcoffset(dt) == datetime.timedelta(0)

    def test_tzparse_localize_is_available(self):
        # backtrader calls .localize() on whatever tzparse returns
        tz = tzparse("Europe/Berlin")
        aware = tz.localize(datetime.datetime(2006, 1, 1, 12, 0))
        assert aware.tzinfo is not None

    def test_tzparse_passes_through_a_tzinfo(self):
        assert tzparse(None) is None

    def test_tzlocal_offset_is_a_timedelta(self):
        assert isinstance(
            TZLocal.utcoffset(datetime.datetime(2006, 1, 1)), datetime.timedelta
        )


class TestAutoDict:
    def test_missing_key_creates_a_nested_dict(self):
        d = AutoDict()
        d["a"]["b"]["c"] = 1
        assert d["a"]["b"]["c"] == 1

    def test_attribute_access_mirrors_item_access(self):
        d = AutoDict()
        d["x"] = 5
        assert d.x == 5

    def test_close_blocks_creation_of_missing_keys(self):
        """Regression: AutoDict.__setattr__ had its underscore branch disabled
        with `if False and ...`, so _close() stored a '_closed' *item* instead
        of setting the flag. The dict stayed open and gained a bogus key."""
        d = AutoDict()
        d["a"] = 1
        d._close()
        with pytest.raises(KeyError):
            d["nope"]["deeper"]
        assert dict(d) == {"a": 1}, "_close() must not add a '_closed' key"

    def test_open_reverses_close(self):
        d = AutoDict()
        d._close()
        d._open()
        d["fresh"]["nested"] = 1
        assert d["fresh"]["nested"] == 1


class TestAutoOrderedDict:
    def test_keeps_insertion_order(self):
        d = AutoOrderedDict()
        for k in "cab":
            d[k] = k
        assert list(d.keys()) == ["c", "a", "b"]

    def test_supports_in_place_numeric_update(self):
        d = AutoOrderedDict()
        d["n"] = 0
        d["n"] += 3
        assert d["n"] == 3


class TestOrderedDefaultdict:
    def test_default_factory_and_order(self):
        d = OrderedDefaultdict(list)
        d["b"].append(1)
        d["a"].append(2)
        assert list(d.keys()) == ["b", "a"]
        assert d["b"] == [1]


class TestMathSupport:
    values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]

    def test_average(self):
        assert mathsupport.average(self.values) == pytest.approx(5.0)

    def test_standarddev_population(self):
        # textbook example: population sigma of the values above is 2.0
        assert mathsupport.standarddev(self.values, bessel=False) == pytest.approx(2.0)

    def test_standarddev_bessel_is_larger(self):
        pop = mathsupport.standarddev(self.values, bessel=False)
        sample = mathsupport.standarddev(self.values, bessel=True)
        assert sample > pop

    def test_variance_is_stddev_squared(self):
        var = mathsupport.variance(self.values)
        assert math.sqrt(sum(var) / len(var)) == pytest.approx(
            mathsupport.standarddev(self.values, bessel=False)
        )

    def test_average_bessel_divides_by_n_minus_one(self):
        n = len(self.values)
        plain = mathsupport.average(self.values)
        bessel = mathsupport.average(self.values, bessel=True)
        assert bessel == pytest.approx(plain * n / (n - 1))


class TestTimeFrame:
    def test_name_and_value_round_trip(self):
        assert bt.TimeFrame.TFrame("Days") == bt.TimeFrame.Days
        assert bt.TimeFrame.TName(bt.TimeFrame.Days) == "Days"

    def test_getname_without_compression(self):
        """Regression: getname(tframe) with the documented default
        compression=None hit `None > 1` and raised TypeError."""
        assert bt.TimeFrame.getname(bt.TimeFrame.Days) == "Day"

    def test_getname_singular_and_plural(self):
        assert bt.TimeFrame.getname(bt.TimeFrame.Days, 1) == "Day"
        assert bt.TimeFrame.getname(bt.TimeFrame.Days, 5) == "Days"

    def test_getname_notimeframe_is_never_singularised(self):
        last = bt.TimeFrame.NoTimeFrame
        assert bt.TimeFrame.getname(last, 1) == bt.TimeFrame.Names[last]

    def test_ordering_is_coarse_upwards(self):
        assert bt.TimeFrame.Minutes < bt.TimeFrame.Days < bt.TimeFrame.Weeks
        assert bt.TimeFrame.Weeks < bt.TimeFrame.Months < bt.TimeFrame.Years
