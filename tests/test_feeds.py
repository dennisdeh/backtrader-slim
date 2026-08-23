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
"""Data feeds: the CSV family, PandasData, and the composite feeds
(Chainer, RollOver) that had no coverage at all.
"""

import datetime

import pytest

import backtrader as bt

from conftest import FROMDATE, TODATE, csvdata, datafile


def collect(data, **cerebro_kwargs):
    """Runs a feed through a Cerebro and returns the bars it produced."""
    bars = []

    class Collector(bt.Strategy):
        __test__ = False

        def next(self):
            bars.append(
                (
                    self.data.datetime.datetime(0),
                    self.data.open[0],
                    self.data.high[0],
                    self.data.low[0],
                    self.data.close[0],
                    self.data.volume[0],
                )
            )

    cerebro = bt.Cerebro(stdstats=False, **cerebro_kwargs)
    cerebro.adddata(data)
    cerebro.addstrategy(Collector)
    cerebro.run()
    return bars


class TestBacktraderCSVData:
    def test_reads_every_session_in_range(self):
        bars = collect(csvdata())
        assert len(bars) == 255  # trading sessions in 2006

    def test_first_and_last_dates_respect_the_range(self):
        bars = collect(csvdata())
        assert bars[0][0].date() == datetime.date(2006, 1, 2)
        assert bars[-1][0].date() == datetime.date(2006, 12, 29)

    def test_ohlc_ordering_holds_on_every_bar(self):
        for _, o, h, l, c, _v in collect(csvdata()):
            assert l <= o <= h
            assert l <= c <= h

    def test_fromdate_and_todate_narrow_the_feed(self):
        data = csvdata(
            fromdate=datetime.datetime(2006, 6, 1),
            todate=datetime.datetime(2006, 6, 30),
        )
        bars = collect(data)
        assert all(b[0].month == 6 for b in bars)
        assert 0 < len(bars) <= 22

    def test_todate_excludes_a_bar_stamped_at_the_session_end(self):
        """A daily bar carries 23:59:59.999 as its time, so `todate` set to
        that date's midnight excludes it. This trips up every attempt to
        split a feed on a date boundary."""
        upto = collect(csvdata(todate=datetime.datetime(2006, 6, 30)))
        assert upto[-1][0].date() == datetime.date(2006, 6, 29)

    def test_weekly_file_has_weekly_bars(self):
        bars = collect(csvdata("2006-week-001.txt"))
        assert 50 <= len(bars) <= 53


class TestGenericCSVData:
    def test_reads_the_same_file_with_an_explicit_column_map(self):
        data = bt.feeds.GenericCSVData(
            dataname=datafile("2006-day-001.txt"),
            fromdate=FROMDATE,
            todate=TODATE,
            dtformat="%Y-%m-%d",
            datetime=0,
            open=1,
            high=2,
            low=3,
            close=4,
            volume=5,
            openinterest=6,
            headers=True,
        )
        generic = collect(data)
        native = collect(csvdata())
        assert len(generic) == len(native)
        assert generic[0] == native[0]
        assert generic[-1] == native[-1]

    def test_missing_column_is_reported_as_nan(self):
        data = bt.feeds.GenericCSVData(
            dataname=datafile("2006-day-001.txt"),
            fromdate=FROMDATE,
            todate=TODATE,
            dtformat="%Y-%m-%d",
            datetime=0,
            open=1,
            high=2,
            low=3,
            close=4,
            volume=-1,  # not present
            openinterest=-1,
            headers=True,
        )
        bars = collect(data)
        assert bars[0][5] == 0.0 or bars[0][5] != bars[0][5]  # 0.0 or NaN


class TestPandasData:
    def test_matches_the_csv_feed_bar_for_bar(self):
        pd = pytest.importorskip("pandas")
        df = pd.read_csv(
            datafile("2006-day-001.txt"),
            parse_dates=["Date"],
            index_col="Date",
        )
        data = bt.feeds.PandasData(dataname=df, fromdate=FROMDATE, todate=TODATE)
        frompandas = collect(data)
        fromcsv = collect(csvdata())
        assert len(frompandas) == len(fromcsv)
        # OHLCV agree bar for bar
        assert [b[1:] for b in frompandas] == [b[1:] for b in fromcsv]

    def test_pandas_bars_are_stamped_at_midnight_not_session_end(self):
        """The CSV feeds stamp a daily bar at the session end (23:59:59.999),
        PandasData takes the index verbatim - so the same day carries a
        different timestamp depending on which feed loaded it. Mixing the two
        in one Cerebro misaligns them; see reports/OPEN_ITEMS.md."""
        pd = pytest.importorskip("pandas")
        df = pd.read_csv(
            datafile("2006-day-001.txt"), parse_dates=["Date"], index_col="Date"
        )
        data = bt.feeds.PandasData(dataname=df, fromdate=FROMDATE, todate=TODATE)
        frompandas = collect(data)
        fromcsv = collect(csvdata())
        assert frompandas[0][0] == datetime.datetime(2006, 1, 2, 0, 0)
        assert fromcsv[0][0].hour == 23

    def test_accepts_a_dataframe_without_volume(self):
        pd = pytest.importorskip("pandas")
        df = pd.read_csv(
            datafile("2006-day-001.txt"),
            parse_dates=["Date"],
            index_col="Date",
        ).drop(columns=["Volume", "OpenInterest"])
        data = bt.feeds.PandasData(
            dataname=df,
            fromdate=FROMDATE,
            todate=TODATE,
            volume=None,
            openinterest=None,
        )
        assert len(collect(data)) == 255


class TestChainer:
    def test_concatenates_two_feeds_end_to_end(self):
        first = csvdata(
            "2006-day-001.txt",
            fromdate=datetime.datetime(2006, 1, 1),
            todate=datetime.datetime(2006, 6, 30),
        )
        second = csvdata(
            "2006-day-001.txt",
            fromdate=datetime.datetime(2006, 7, 1),
            todate=datetime.datetime(2006, 12, 31),
        )
        chained = bt.feeds.Chainer(dataname="chained", *[first, second])
        bars = collect(chained)
        # 126 + 128: `todate` is exclusive of a daily bar stamped at the
        # session end, so 2006-06-30 belongs to neither half
        assert len(bars) == 254
        dates = [b[0] for b in bars]
        assert dates == sorted(dates)
        assert dates[0].date() == datetime.date(2006, 1, 2)
        assert dates[-1].date() == datetime.date(2006, 12, 29)

    def test_seam_is_continuous(self):
        first = csvdata(
            "2006-day-001.txt",
            todate=datetime.datetime(2006, 6, 30),
        )
        second = csvdata(
            "2006-day-001.txt",
            fromdate=datetime.datetime(2006, 7, 1),
        )
        dates = [
            b[0].date()
            for b in collect(bt.feeds.Chainer(dataname="c", *[first, second]))
        ]
        i = dates.index(datetime.date(2006, 7, 3))
        assert dates[i - 1] == datetime.date(2006, 6, 29)


class TestRollOver:
    def test_rolls_from_the_first_feed_to_the_second(self):
        first = csvdata(
            "2006-day-001.txt",
            fromdate=datetime.datetime(2006, 1, 1),
            todate=datetime.datetime(2006, 6, 30),
        )
        second = csvdata(
            "2006-day-001.txt",
            fromdate=datetime.datetime(2006, 7, 1),
            todate=datetime.datetime(2006, 12, 31),
        )
        rolled = bt.feeds.RollOver(dataname="rolled", *[first, second])
        bars = collect(rolled)
        dates = [b[0] for b in bars]
        assert dates == sorted(dates)
        # the roll consumes the first bar of the incoming feed as the switch
        # point, so the result is one bar shorter than a plain chain (254)
        assert len(bars) == 253
        assert dates[0].date() == datetime.date(2006, 1, 2)
        assert dates[-1].date() == datetime.date(2006, 12, 29)


class TestCSVSubclasses:
    def test_sierrachart_and_mt4_are_generic_csv_feeds(self):
        assert issubclass(bt.feeds.SierraChartCSVData, bt.feeds.GenericCSVData)
        assert issubclass(bt.feeds.MT4CSVData, bt.feeds.GenericCSVData)

    def test_yahoo_csv_feed_reads_a_tracked_file(self):
        data = bt.feeds.YahooFinanceCSVData(
            dataname=datafile("yhoo-2014.txt"),
            fromdate=datetime.datetime(2014, 1, 1),
            todate=datetime.datetime(2014, 12, 31),
        )
        bars = collect(data)
        assert len(bars) > 200
        assert all(b[3] <= b[1] for b in bars)  # low <= high
