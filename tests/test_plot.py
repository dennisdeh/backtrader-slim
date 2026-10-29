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
"""The plot's date axis, its backend and when it shows.

Bars are drawn at their index, so ticks and labels translate between indices
and dates. Until 2026-10-29 that translation mixed backtrader's date numbers
(counted from year 1) with matplotlib's (counted from 1970) and labelled 2006
as 3975, and the labels were hidden on every axis anyway.
"""

import datetime
import warnings
from collections import defaultdict

import pytest

import backtrader as bt

from conftest import csvdata, datafile

mpl = pytest.importorskip("matplotlib")
pytestmark = pytest.mark.plotting


class _WithRsi(bt.Strategy):
    def __init__(self):
        bt.indicators.RSI()  # a second axis below the data


def _figure(data, strategy=bt.Strategy, **plotkw):
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data)
    cerebro.addstrategy(strategy)
    cerebro.run()
    fig = cerebro.plot(iplot=False, volume=False, **plotkw)[0][0]
    fig.canvas.draw()
    return fig


def _labels(ax):
    return [t.get_text() for t in ax.get_xticklabels() if t.get_visible()]


def _first_sessions_from_february():
    with open(datafile("2006-day-001.txt")) as f:
        dates = [line.split(",")[0] for line in f.readlines()[1:]]
    first = defaultdict(list)
    for i, d in enumerate(dates):
        first[d[:7]].append((i, d))
    return [first[m][0] for m in sorted(first)][1:]  # January opens the chart


def test_dates_are_shown_under_the_lowest_axis_only():
    fig = _figure(csvdata(), _WithRsi)
    *upper, lowest = fig.axes
    assert _labels(lowest)
    assert all(not _labels(ax) for ax in upper)


def test_concise_labels_name_the_months_and_the_year():
    lowest = _figure(csvdata()).axes[-1]
    assert _labels(lowest) == [
        "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]  # fmt: skip
    assert lowest.xaxis.get_offset_text().get_text() == "2006"


def test_month_ticks_sit_on_the_first_session_of_each_month():
    lowest = _figure(csvdata(), fmt_x_ticks="%Y-%m-%d").axes[-1]
    expected = _first_sessions_from_february()
    assert list(lowest.get_xticks()) == [i for i, _ in expected]
    assert _labels(lowest) == [d for _, d in expected]


def test_cursor_readout_is_in_the_feeds_timezone():
    # 09:05 in the file, read as UTC and shown in New York: 04:05
    data = csvdata(
        "2006-min-005.txt",
        timeframe=bt.TimeFrame.Minutes,
        compression=5,
        todate=datetime.datetime(2006, 1, 4),
        tzinput="UTC",
        tz="America/New_York",
    )
    ax = _figure(data).axes[-1]
    assert ax.format_xdata(0) == "2006-01-02 04:05"


def test_a_tick_in_a_weekend_gap_is_labelled_with_its_bars_date():
    from backtrader.plot.locator import DateIndexLocator, bars_to_mpl

    # Fri 2006-01-06 and Mon 2006-01-09: daily ticks for Sat and Sun both land
    # on Monday's bar, which must not be labelled as a weekend day
    days = [datetime.datetime(2006, 1, d, 23, 59, 59) for d in (4, 5, 6, 9, 10, 11)]
    xs = bars_to_mpl([bt.date2num(d) for d in days], floor_to_day=True)
    loc = DateIndexLocator(xs)
    ticks = loc.tick_values(0, len(days) - 1)
    labelled = [mpl.dates.num2date(loc.num(i)).date() for i in ticks]
    assert labelled == [d.date() for d in days]


class TestShowing:
    @pytest.fixture
    def shown(self, monkeypatch):
        import matplotlib.pyplot

        calls = []
        monkeypatch.setattr(matplotlib.pyplot, "show", lambda: calls.append(1))
        return calls

    def _plot(self, **kwargs):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(bt.Strategy)
        cerebro.run()
        return cerebro.plot(**kwargs)

    def test_figures_are_shown_on_a_display_backend(self, shown, monkeypatch):
        monkeypatch.setattr(mpl, "get_backend", lambda: "QtAgg")
        assert self._plot()
        assert shown == [1]

    def test_nothing_is_shown_and_nothing_warns_on_agg(self, shown):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert self._plot()
        assert shown == []

    def test_iplot_false_only_returns_the_figures(self, shown, monkeypatch):
        monkeypatch.setattr(mpl, "get_backend", lambda: "QtAgg")
        assert self._plot(iplot=False)
        assert shown == []

    def test_use_switches_the_backend(self):
        import matplotlib.pyplot

        try:
            self._plot(iplot=False, use="svg")
            assert mpl.get_backend() == "svg"
        finally:
            matplotlib.pyplot.switch_backend("Agg")


def test_plotting_again_starts_a_fresh_figure():
    # pyplot.figure(num) hands back the existing figure of that number, so a
    # second cerebro.plot() used to stack its axes on top of the first chart
    first = _figure(csvdata(), _WithRsi)
    naxes = len(first.axes)
    second = _figure(csvdata(), _WithRsi)
    assert len(second.axes) == naxes
