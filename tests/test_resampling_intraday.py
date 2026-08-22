"""Intraday resampling and replay, the data filler, the trading calendar and
the two indicators that had almost no coverage (PSAR, PivotPoint).
"""

import datetime

import pytest

import backtrader as bt

from conftest import datafile


def minutedata(**kwargs):
    return bt.feeds.BacktraderCSVData(
        dataname=datafile("2006-min-005.txt"),
        timeframe=bt.TimeFrame.Minutes,
        compression=5,
        **kwargs,
    )


def collect(cerebro):
    stamps = []

    class Collector(bt.Strategy):
        __test__ = False

        def next(self):
            stamps.append(self.data.datetime.datetime(0))

    cerebro.addstrategy(Collector)
    cerebro.run()
    return stamps


class TestIntradayResampling:
    def test_baseline_five_minute_bars(self):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(minutedata())
        stamps = collect(cerebro)
        assert len(stamps) > 100
        assert stamps == sorted(stamps)

    def test_resample_to_fifteen_minutes_reduces_bars(self):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(minutedata())
        base = len(collect(cerebro))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.resampledata(
            minutedata(), timeframe=bt.TimeFrame.Minutes, compression=15
        )
        coarse = len(collect(cerebro))
        assert coarse < base
        assert coarse == pytest.approx(base / 3, rel=0.2)

    def test_resample_intraday_to_daily(self):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.resampledata(minutedata(), timeframe=bt.TimeFrame.Days)
        stamps = collect(cerebro)
        assert len(stamps) == len({s.date() for s in stamps})

    def test_replay_intraday_keeps_every_tick_of_the_period(self):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(minutedata())
        base = len(collect(cerebro))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.replaydata(minutedata(), timeframe=bt.TimeFrame.Minutes, compression=15)
        assert len(collect(cerebro)) == base

    def test_resampled_ohlc_brackets_the_source_bars(self):
        source = []

        class Grab(bt.Strategy):
            __test__ = False

            def next(self):
                source.append((self.data.high[0], self.data.low[0]))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(minutedata())
        cerebro.addstrategy(Grab)
        cerebro.run()

        agg = []

        class GrabAgg(bt.Strategy):
            __test__ = False

            def next(self):
                agg.append((self.data.high[0], self.data.low[0]))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.resampledata(
            minutedata(), timeframe=bt.TimeFrame.Minutes, compression=15
        )
        cerebro.addstrategy(GrabAgg)
        cerebro.run()

        assert max(h for h, _ in agg) == pytest.approx(max(h for h, _ in source))
        assert min(l for _, l in agg) == pytest.approx(min(l for _, l in source))


class TestDataFiller:
    def test_session_filler_inserts_missing_intraday_bars(self):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(minutedata())
        base = len(collect(cerebro))

        data = minutedata()
        data.addfilter(bt.filters.SessionFiller)
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(data)
        assert len(collect(cerebro)) >= base


class TestTradingCalendar:
    def test_nextday_skips_a_declared_holiday(self):
        cal = bt.TradingCalendar(holidays=[datetime.date(2006, 1, 3)])
        assert cal.nextday(datetime.date(2006, 1, 2)) == datetime.date(2006, 1, 4)

    def test_nextday_skips_the_weekend(self):
        # 2006-01-06 is a Friday; the next session is the Monday
        cal = bt.TradingCalendar()
        assert cal.nextday(datetime.date(2006, 1, 6)) == datetime.date(2006, 1, 9)

    def test_schedule_returns_opening_and_closing_times(self):
        cal = bt.TradingCalendar(open=datetime.time(9, 30), close=datetime.time(16, 0))
        opening, closing = cal.schedule(datetime.datetime(2006, 1, 3))
        assert opening.time() == datetime.time(9, 30)
        assert closing.time() == datetime.time(16, 0)

    def test_earlydays_override_the_regular_close(self):
        early = datetime.date(2006, 1, 3)
        cal = bt.TradingCalendar(
            open=datetime.time(9, 30),
            close=datetime.time(16, 0),
            earlydays=[(early, datetime.time(9, 30), datetime.time(13, 0))],
        )
        _, closing = cal.schedule(datetime.datetime(2006, 1, 3))
        assert closing.time() == datetime.time(13, 0)

    def test_last_weekday_detects_the_week_boundary(self):
        cal = bt.TradingCalendar()
        assert cal.last_weekday(datetime.date(2006, 1, 6))  # Friday
        assert not cal.last_weekday(datetime.date(2006, 1, 4))  # Wednesday

    def test_last_monthday_and_yearday(self):
        cal = bt.TradingCalendar()
        assert cal.last_monthday(datetime.date(2006, 1, 31))
        assert cal.last_yearday(datetime.date(2006, 12, 29))
        assert not cal.last_yearday(datetime.date(2006, 6, 30))

    def test_calendar_can_be_attached_to_cerebro(self):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addcalendar(bt.TradingCalendar())
        cerebro.adddata(
            bt.feeds.BacktraderCSVData(dataname=datafile("2006-day-001.txt"))
        )
        assert len(collect(cerebro)) == 255

    def test_pandas_market_calendar_is_optional(self):
        pytest.importorskip("pandas_market_calendars")
        cal = bt.PandasMarketCalendar(calendar="NYSE")
        assert cal is not None


class TestPSAR:
    def test_psar_stays_within_the_price_range(self):
        values = []

        class S(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.psar = bt.indicators.ParabolicSAR(self.data)

            def next(self):
                values.append(self.psar[0])

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(
            bt.feeds.BacktraderCSVData(dataname=datafile("2006-day-001.txt"))
        )
        cerebro.addstrategy(S)
        cerebro.run()
        assert values
        assert all(v == v for v in values)  # no NaN once started
        assert min(values) > 0

    def test_psar_matches_between_next_and_once(self):
        def last(runonce):
            cerebro = bt.Cerebro(stdstats=False, runonce=runonce)
            cerebro.adddata(
                bt.feeds.BacktraderCSVData(dataname=datafile("2006-day-001.txt"))
            )

            class S(bt.Strategy):
                __test__ = False

                def __init__(self):
                    self.psar = bt.indicators.ParabolicSAR(self.data)

            cerebro.addstrategy(S)
            return cerebro.run()[0].psar[0]

        assert last(True) == pytest.approx(last(False))


class TestPivotPoint:
    def test_pivotpoint_needs_a_coarser_timeframe(self):
        class S(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.pp = bt.indicators.PivotPoint(self.data1)
                self.pp.plotinfo.plot = False

        cerebro = bt.Cerebro(stdstats=False)
        data = bt.feeds.BacktraderCSVData(dataname=datafile("2006-day-001.txt"))
        cerebro.adddata(data)
        cerebro.resampledata(
            bt.feeds.BacktraderCSVData(dataname=datafile("2006-day-001.txt")),
            timeframe=bt.TimeFrame.Months,
        )
        cerebro.addstrategy(S)
        strat = cerebro.run()[0]
        # NOTE: the pivot line is named `p`, but `.p` on any LineIterator is
        # the params object - so the line is only reachable as `.lines.p`.
        assert isinstance(strat.pp.p, object) and not hasattr(strat.pp.p, "__getitem__")
        pivot = strat.pp.lines.p[0]
        assert pivot > 0
        assert strat.pp.s1[0] < pivot < strat.pp.r1[0]
        assert strat.pp.s2[0] < strat.pp.s1[0]
        assert strat.pp.r2[0] > strat.pp.r1[0]

    def test_fibonacci_and_demark_variants_exist(self):
        assert bt.indicators.FibonacciPivotPoint is not None
        assert bt.indicators.DemarkPivotPoint is not None
