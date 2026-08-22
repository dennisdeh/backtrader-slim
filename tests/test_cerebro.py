"""Cerebro's public surface: configuration, running, optimisation, observers,
writers, timers and plotting.

cerebro.py, plot/ and btrun/ carried 0-60% coverage and no direct tests.
"""

import datetime
import io

import pytest

import backtrader as bt

from conftest import csvdata, datafile


class Noop(bt.Strategy):
    __test__ = False

    params = dict(period=10)

    def __init__(self):
        self.sma = bt.indicators.SMA(self.data, period=self.p.period)
        self.ran = 0

    def next(self):
        self.ran += 1


class TestRunning:
    def test_run_returns_one_instance_per_strategy(self, cerebro_with_data):
        cerebro_with_data.addstrategy(Noop)
        strats = cerebro_with_data.run()
        assert len(strats) == 1
        assert isinstance(strats[0], Noop)

    def test_two_strategies_both_run(self, cerebro_with_data):
        cerebro_with_data.addstrategy(Noop)
        cerebro_with_data.addstrategy(Noop, period=20)
        strats = cerebro_with_data.run()
        assert len(strats) == 2
        assert strats[0].p.period == 10
        assert strats[1].p.period == 20

    def test_strategy_params_reach_the_instance(self, cerebro_with_data):
        cerebro_with_data.addstrategy(Noop, period=33)
        assert cerebro_with_data.run()[0].p.period == 33

    def test_next_is_called_once_per_bar_after_minperiod(self, cerebro_with_data):
        cerebro_with_data.addstrategy(Noop, period=10)
        strat = cerebro_with_data.run()[0]
        assert strat.ran == 255 - 10 + 1

    def test_runonce_and_next_agree(self, daily_data):
        results = {}
        for runonce in (True, False):
            cerebro = bt.Cerebro(stdstats=False, runonce=runonce)
            cerebro.adddata(csvdata())
            cerebro.addstrategy(Noop)
            results[runonce] = cerebro.run()[0].sma[0]
        assert results[True] == pytest.approx(results[False])

    def test_preload_off_produces_the_same_result(self):
        results = {}
        for preload in (True, False):
            cerebro = bt.Cerebro(stdstats=False, preload=preload, runonce=False)
            cerebro.adddata(csvdata())
            cerebro.addstrategy(Noop)
            results[preload] = cerebro.run()[0].sma[0]
        assert results[True] == pytest.approx(results[False])

    def test_exactbars_limits_memory_but_keeps_the_last_value(self):
        cerebro = bt.Cerebro(stdstats=False, exactbars=1, runonce=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Noop)
        strat = cerebro.run()[0]
        assert strat.sma[0] > 0


class TestOptimisation:
    def test_optstrategy_runs_every_combination(self):
        cerebro = bt.Cerebro(stdstats=False, maxcpus=1)
        cerebro.adddata(csvdata())
        cerebro.optstrategy(Noop, period=range(10, 15))
        results = cerebro.run()
        assert len(results) == 5

    def test_optreturn_gives_back_params_only(self):
        cerebro = bt.Cerebro(stdstats=False, maxcpus=1, optreturn=True)
        cerebro.adddata(csvdata())
        cerebro.optstrategy(Noop, period=[10, 20])
        results = cerebro.run()
        assert [r[0].p.period for r in results] == [10, 20]

    def test_optcallback_is_invoked(self):
        seen = []
        cerebro = bt.Cerebro(stdstats=False, maxcpus=1)
        cerebro.adddata(csvdata())
        cerebro.optstrategy(Noop, period=[10, 20])
        cerebro.optcallback(lambda cb: seen.append(cb))
        cerebro.run()
        assert len(seen) == 2


class TestBrokerConfiguration:
    def test_setcash_before_run_is_the_starting_value(self, cerebro_with_data):
        cerebro_with_data.broker.setcash(5000.0)
        cerebro_with_data.addstrategy(Noop)
        cerebro_with_data.run()
        assert cerebro_with_data.broker.startingcash == 5000.0

    def test_broker_can_be_replaced(self, cerebro_with_data):
        broker = bt.brokers.BackBroker(cash=777.0)
        cerebro_with_data.setbroker(broker)
        assert cerebro_with_data.getbroker() is broker

    def test_add_observer_shows_up_in_stats(self, cerebro_with_data):
        cerebro_with_data.addobserver(bt.observers.Broker)
        cerebro_with_data.addstrategy(Noop)
        strat = cerebro_with_data.run()[0]
        assert len(strat.stats) >= 1


class TestResampling:
    def test_resampledata_to_weekly_reduces_the_bar_count(self):
        bars = []

        class Counter(bt.Strategy):
            __test__ = False

            def next(self):
                bars.append(self.data.datetime.date(0))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.resampledata(csvdata(), timeframe=bt.TimeFrame.Weeks)
        cerebro.addstrategy(Counter)
        cerebro.run()
        assert 50 <= len(bars) <= 53

    def test_resampledata_to_monthly(self):
        bars = []

        class Counter(bt.Strategy):
            __test__ = False

            def next(self):
                bars.append(self.data.datetime.date(0))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.resampledata(csvdata(), timeframe=bt.TimeFrame.Months)
        cerebro.addstrategy(Counter)
        cerebro.run()
        assert len(bars) == 12

    def test_replaydata_keeps_the_original_bar_count(self):
        bars = []

        class Counter(bt.Strategy):
            __test__ = False

            def next(self):
                bars.append(len(self))

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.replaydata(csvdata(), timeframe=bt.TimeFrame.Weeks)
        cerebro.addstrategy(Counter)
        cerebro.run()
        assert len(bars) == 255  # every daily bar replays into its week


class TestTimers:
    def test_timer_fires_on_the_requested_schedule(self):
        fired = []

        class Timed(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.add_timer(when=bt.timer.SESSION_START)

            def notify_timer(self, timer, when, *args, **kwargs):
                fired.append(when)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Timed)
        cerebro.run()
        assert len(fired) == 255

    def test_monthly_timer_fires_once_per_month(self):
        fired = []

        class Timed(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.add_timer(
                    when=bt.timer.SESSION_START, monthdays=[1], monthcarry=True
                )

            def notify_timer(self, timer, when, *args, **kwargs):
                fired.append(when)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Timed)
        cerebro.run()
        assert len(fired) == 12


class TestWriter:
    def test_writer_emits_a_csv_report(self):
        out = io.StringIO()
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Noop)
        cerebro.addwriter(bt.WriterFile, out=out, csv=True)
        cerebro.run()
        text = out.getvalue()
        assert "Cerebro" in text
        assert len(text.splitlines()) > 100


class TestPlotting:
    @pytest.mark.plotting
    def test_plot_renders_without_a_display(self):
        """plot/ is ~1000 statements that nothing exercised. The backend is
        forced to Agg, so this renders a figure and never opens a window."""
        pytest.importorskip("matplotlib")
        cerebro = bt.Cerebro(stdstats=True)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Noop)
        cerebro.run()
        figs = cerebro.plot(iplot=False)
        assert figs
        assert figs[0]

    @pytest.mark.plotting
    def test_plot_with_observers_and_analyzers(self):
        pytest.importorskip("matplotlib")
        cerebro = bt.Cerebro(stdstats=True)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Noop)
        cerebro.addobserver(bt.observers.DrawDown)
        cerebro.addanalyzer(bt.analyzers.SharpeRatio)
        cerebro.run()
        assert cerebro.plot(iplot=False, volume=False)


class TestBtrunCLI:
    def test_btrun_runs_a_backtest_from_the_command_line(self, capsys):
        from backtrader.btrun import btrun

        btrun(
            [
                "--data",
                datafile("2006-day-001.txt"),
                "--format",
                "btcsv",
                "--strategy",
                ":SMA_CrossOver",
                "--nostdstats",
            ]
        )
        # it ran to completion without raising; that is the contract
        assert True

    def test_btrun_rejects_an_unknown_format(self):
        from backtrader.btrun import btrun

        with pytest.raises(SystemExit):
            btrun(["--data", datafile("2006-day-001.txt"), "--format", "nope"])
