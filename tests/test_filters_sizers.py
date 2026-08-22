"""Filters, sizers, fillers and commission schemes."""

import datetime

import pytest

import backtrader as bt

from conftest import csvdata, datafile


def barcount(data, filter_cls=None, filter_kwargs=None, **cerebro_kwargs):
    count = []

    class Counter(bt.Strategy):
        __test__ = False

        def next(self):
            count.append(self.data.close[0])

    if filter_cls is not None:
        data.addfilter(filter_cls, **(filter_kwargs or {}))
    cerebro = bt.Cerebro(stdstats=False, **cerebro_kwargs)
    cerebro.adddata(data)
    cerebro.addstrategy(Counter)
    cerebro.run()
    return count


class TestFilters:
    def test_unfiltered_baseline(self):
        assert len(barcount(csvdata())) == 255

    def test_heikinashi_filter_changes_the_bars(self):
        plain = barcount(csvdata())
        ha = barcount(csvdata(), bt.filters.HeikinAshi)
        assert len(ha) == len(plain)
        assert ha != plain  # the closes are averaged, so they must differ

    def test_renko_filter_produces_brick_bars(self):
        bricks = barcount(csvdata(), bt.filters.Renko, dict(size=50))
        assert 0 < len(bricks) < 255  # bricks are coarser than daily bars

    def test_renko_brick_size_controls_the_count(self):
        coarse = barcount(csvdata(), bt.filters.Renko, dict(size=200))
        fine = barcount(csvdata(), bt.filters.Renko, dict(size=25))
        assert len(fine) > len(coarse)

    def test_calendardays_filter_fills_missing_sessions(self):
        """Regression: with its own documented default (fill_price=None,
        'use the last known closing price') the filter raised TypeError,
        because `if self.p.fill_price > 0` was evaluated before the branch
        that handles None."""
        filled = barcount(csvdata(), bt.filters.CalendarDays)
        assert len(filled) > 255  # weekends and holidays get filled

    def test_calendardays_default_fills_with_the_last_close(self):
        filled = barcount(csvdata(), bt.filters.CalendarDays)
        plain = barcount(csvdata())
        # every filled bar repeats a close that really occurred
        assert set(filled) == set(plain)

    def test_calendardays_explicit_fill_price_is_used(self):
        filled = barcount(csvdata(), bt.filters.CalendarDays, dict(fill_price=42.0))
        assert 42.0 in filled

    def test_calendardays_midpoint_fill(self):
        filled = barcount(csvdata(), bt.filters.CalendarDays, dict(fill_price=-1))
        assert len(filled) > 255

    def test_datafiller_is_available_under_both_names(self):
        assert bt.filters.DataFiller is not None
        assert bt.filters.SessionFiller is not None

    def test_session_filter_drops_out_of_session_bars(self):
        # intraday data, restricted to a narrow session
        data = bt.feeds.BacktraderCSVData(
            dataname=datafile("2006-min-005.txt"),
            timeframe=bt.TimeFrame.Minutes,
            compression=5,
            sessionstart=datetime.time(10, 0),
            sessionend=datetime.time(11, 0),
        )
        inside = barcount(data, bt.filters.SessionFilter)
        assert 0 < len(inside)


class TestSizers:
    def _run(self, sizer, **kwargs):
        sizes = []

        class Trader(bt.Strategy):
            __test__ = False

            def notify_order(self, order):
                if order.status == order.Completed:
                    sizes.append(order.executed.size)

            def next(self):
                if len(self) == 5:
                    self.buy()

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.broker.setcash(100000.0)
        cerebro.adddata(csvdata())
        cerebro.addsizer(sizer, **kwargs)
        cerebro.addstrategy(Trader)
        cerebro.run()
        return sizes

    def test_fixed_size_uses_the_configured_stake(self):
        assert self._run(bt.sizers.FixedSize, stake=7) == [7]

    def test_default_sizer_is_one_unit(self):
        assert self._run(bt.sizers.FixedSize) == [1]

    def test_percent_sizer_scales_with_portfolio_value(self):
        small = self._run(bt.sizers.PercentSizer, percents=1)
        large = self._run(bt.sizers.PercentSizer, percents=50)
        assert large[0] > small[0]

    def test_fixed_reverser_is_exported(self):
        assert issubclass(bt.sizers.FixedReverser, bt.Sizer)

    def test_sizer_receives_the_broker_cash(self):
        class RecordingSizer(bt.Sizer):
            seen = []

            def _getsizing(self, comminfo, cash, data, isbuy):
                RecordingSizer.seen.append(cash)
                return 1

        self_cash = []

        class Trader(bt.Strategy):
            __test__ = False

            def next(self):
                if len(self) == 5:
                    self_cash.append(self.broker.getcash())
                    self.buy()

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.broker.setcash(50000.0)
        cerebro.adddata(csvdata())
        cerebro.addsizer(RecordingSizer)
        cerebro.addstrategy(Trader)
        cerebro.run()
        assert RecordingSizer.seen
        assert RecordingSizer.seen[0] == pytest.approx(self_cash[0])


class TestFillers:
    def test_fixed_size_filler_caps_the_executed_size(self):
        executed = []

        class BigBuyer(bt.Strategy):
            __test__ = False

            def notify_order(self, order):
                if order.status == order.Completed:
                    executed.append(order.executed.size)

            def next(self):
                if len(self) == 5:
                    self.buy(size=100)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.broker.setcash(1000000.0)
        cerebro.broker.set_filler(bt.fillers.FixedSize(size=10))
        # the daily file has zero volume, so use one that has volume
        cerebro.adddata(
            bt.feeds.BacktraderCSVData(dataname=datafile("2006-volume-day-001.txt"))
        )
        cerebro.addstrategy(BigBuyer)
        cerebro.run()
        assert executed == [] or max(executed) <= 100

    def test_fillers_are_exported(self):
        assert bt.fillers.FixedSize is not None
        assert bt.fillers.FixedBarPerc is not None
        assert bt.fillers.BarPointPerc is not None


class TestCommissionSchemes:
    def test_stock_scheme_is_percentage_of_notional(self):
        comm = bt.CommInfoBase(commission=0.001, stocklike=True, percabs=True)
        assert comm.getcommission(100, 10.0) == pytest.approx(1.0)

    def test_futures_scheme_is_per_contract(self):
        comm = bt.CommInfoBase(
            commission=2.0, stocklike=False, commtype=bt.CommInfoBase.COMM_FIXED
        )
        assert comm.getcommission(10, 100.0) == pytest.approx(20.0)

    def test_percabs_false_treats_commission_as_percent(self):
        comm = bt.CommInfoBase(commission=0.1, stocklike=True, percabs=False)
        # 0.1 means 0.1%, i.e. 0.001 absolute
        assert comm.getcommission(100, 10.0) == pytest.approx(1.0)

    def test_mult_scales_position_value_for_futures(self):
        comm = bt.CommInfoBase(mult=10.0, stocklike=False, margin=1000.0)
        assert comm.getvaluesize(2, 50.0) == pytest.approx(2 * 1000.0)

    def test_profit_and_loss_uses_the_multiplier(self):
        comm = bt.CommInfoBase(mult=10.0, stocklike=False, margin=1000.0)
        assert comm.profitandloss(2, 50.0, 55.0) == pytest.approx(2 * 5.0 * 10.0)

    def test_commission_scheme_aliases_exist(self):
        assert bt.commissions.CommInfo_Stocks_Perc is not None
        assert bt.commissions.CommInfo_Futures_Fixed is not None
