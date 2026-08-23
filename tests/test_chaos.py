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
"""Chaos: break things on purpose and check what the engine does about it.

Two rules are being tested, and they pull in opposite directions.

**Nothing raised by user code may be swallowed.** A strategy, indicator,
analyzer, observer, sizer or writer that raises has found a problem the caller
needs to see. A run that quietly completes after eating the exception has
computed the wrong answer and said nothing, which is worse than a crash.

**Broken input must be reported precisely.** A malformed row should name the
file and the line, and raise something a caller can reasonably catch — not a
bare ``StopIteration`` with no message, and never a silently fabricated value.

The one deliberate exception to the first rule is ``StrategySkipError``, which
exists to be swallowed.
"""

import pathlib
import re

import pytest

import backtrader as bt

from conftest import csvdata, datafile

BT_HEADER = "Date,Open,High,Low,Close,Volume,OpenInterest\n"
BT_ROW = "2006-01-02,3578.73,3605.95,3578.73,3604.33,0,0\n"

YAHOO_HEADER = "Date,Open,High,Low,Close,Adj Close,Volume\n"
YAHOO_ROW = "1996-04-12,1.052083,1.791667,1.020833,1.375000,1.375000,408720000\n"


class Boom(Exception):
    """Raised by the fakes below; never raised by backtrader itself."""


def write(tmp_path, body, name="chaos.csv"):
    path = tmp_path / name
    path.write_text(body)
    return str(path)


def bars_from(path, feedcls=bt.feeds.BacktraderCSVData, **feedkwargs):
    """Run a feed to completion and return the (close, volume) of each bar."""
    seen = []

    class Recorder(bt.Strategy):
        __test__ = False

        def next(self):
            seen.append((self.data.close[0], self.data.volume[0]))

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(feedcls(dataname=path, **feedkwargs))
    cerebro.addstrategy(Recorder)
    cerebro.run()
    return seen


def run_strategy(strategy, **cerebrokwargs):
    cerebro = bt.Cerebro(stdstats=False, **cerebrokwargs)
    cerebro.adddata(csvdata())
    cerebro.addstrategy(strategy)
    return cerebro.run()


class TestMalformedCSVIsReportedPrecisely:
    """A broken row names the file and the line, and raises a ValueError."""

    def bad(self, tmp_path, body):
        with pytest.raises(ValueError) as excinfo:
            bars_from(write(tmp_path, body))
        return str(excinfo.value)

    def test_a_truncated_row_is_a_value_error_not_a_stopiteration(self, tmp_path):
        # StopIteration is the iteration protocol's sentinel. Raising it from
        # a parser is both uninformative and hazardous: under PEP 479 any
        # caller that is a generator turns it into a RuntimeError.
        message = self.bad(tmp_path, BT_HEADER + "2006-01-02,1,2,3,4\n")
        assert "line 2" in message

    def test_a_row_with_only_a_date_is_reported(self, tmp_path):
        assert "line 2" in self.bad(tmp_path, BT_HEADER + "2006-01-02\n")

    def test_a_non_numeric_price_names_the_line(self, tmp_path):
        message = self.bad(tmp_path, BT_HEADER + "2006-01-02,abc,2,3,4,0,0\n")
        assert "line 2" in message

    def test_an_empty_price_field_names_the_line(self, tmp_path):
        assert "line 2" in self.bad(tmp_path, BT_HEADER + "2006-01-02,,2,3,4,0,0\n")

    def test_an_unparseable_date_names_the_line(self, tmp_path):
        assert "line 2" in self.bad(tmp_path, BT_HEADER + "nope,1,2,3,4,0,0\n")

    def test_an_impossible_date_names_the_line(self, tmp_path):
        assert "line 2" in self.bad(tmp_path, BT_HEADER + "2006-13-02,1,2,3,4,0,0\n")

    def test_a_blank_interior_line_names_the_line(self, tmp_path):
        assert "line 3" in self.bad(tmp_path, BT_HEADER + BT_ROW + "\n" + BT_ROW)

    def test_the_message_names_the_file(self, tmp_path):
        message = self.bad(tmp_path, BT_HEADER + "2006-01-02,abc,2,3,4,0,0\n")
        assert "chaos.csv" in message

    def test_the_line_number_counts_from_the_top_of_the_file(self, tmp_path):
        # three good rows, then a bad one: the header is line 1
        body = BT_HEADER + BT_ROW * 3 + "2006-01-06,x,2,3,4,0,0\n"
        assert "line 5" in self.bad(tmp_path, body)

    def test_the_original_error_is_kept_as_the_cause(self, tmp_path):
        with pytest.raises(ValueError) as excinfo:
            bars_from(write(tmp_path, BT_HEADER + "2006-01-02,abc,2,3,4,0,0\n"))
        assert excinfo.value.__cause__ is not None


class TestEmptyAndMissingInput:
    def test_an_empty_file_yields_no_bars(self, tmp_path):
        assert bars_from(write(tmp_path, "")) == []

    def test_a_header_only_file_yields_no_bars(self, tmp_path):
        assert bars_from(write(tmp_path, BT_HEADER)) == []

    def test_a_missing_file_raises_filenotfound(self):
        with pytest.raises(FileNotFoundError):
            bars_from("/nonexistent/nowhere.csv")

    def test_a_directory_instead_of_a_file_raises_oserror(self, tmp_path):
        with pytest.raises(OSError):
            bars_from(str(tmp_path))

    def test_a_feed_with_no_bars_still_runs_analyzers(self, tmp_path):
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(bt.feeds.BacktraderCSVData(dataname=write(tmp_path, BT_HEADER)))
        cerebro.addstrategy(bt.Strategy)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
        strat = cerebro.run()[0]
        assert strat.analyzers.tradeanalyzer.get_analysis() is not None


class TestYahooFeedDoesNotFabricateData:
    """The bare `except:` around the volume field used to invent a 0.0."""

    def yahoo(self, tmp_path, body):
        return bars_from(
            write(tmp_path, YAHOO_HEADER + body),
            feedcls=bt.feeds.YahooFinanceCSVData,
        )

    def test_a_well_formed_row_loads(self, tmp_path):
        # the feed rounds prices to 2 decimals by default (round/decimals)
        assert self.yahoo(tmp_path, YAHOO_ROW) == [(1.38, 408720000.0)]

    def test_a_row_missing_its_volume_column_raises(self, tmp_path):
        # Silently loading this as volume=0.0 corrupts every volume-based
        # indicator and sizer downstream, and says nothing.
        with pytest.raises(ValueError):
            self.yahoo(tmp_path, "1996-04-12,1.05,1.79,1.02,1.37,1.37\n")

    def test_a_row_with_a_garbage_volume_raises(self, tmp_path):
        with pytest.raises(ValueError):
            self.yahoo(tmp_path, "1996-04-12,1.05,1.79,1.02,1.37,1.37,banana\n")

    def test_a_row_containing_null_is_skipped(self, tmp_path):
        # Documented behaviour, handled by the null-scanning loop at the top
        # of _loadline - not by the volume handler below it.
        body = "1996-04-12,1.05,1.79,1.02,1.37,1.37,null\n" + YAHOO_ROW
        assert self.yahoo(tmp_path, body) == [(1.38, 408720000.0)]

    def test_the_tracked_yahoo_fixture_still_loads(self):
        # Guards the fix against being stricter than the real data
        assert (
            len(
                bars_from(
                    datafile("yhoo-1996-2014.txt"), feedcls=bt.feeds.YahooFinanceCSVData
                )
            )
            > 4000
        )


class TestUserExceptionsPropagate:
    """Nothing a user's own code raises may be eaten by the engine."""

    def strategy_raising_in(self, where):
        class Raiser(bt.Strategy):
            __test__ = False

            def __init__(self):
                if where == "__init__":
                    raise Boom()
                self.sma = bt.indicators.SMA(self.data, period=5)
                self.n = 0

            def start(self):
                if where == "start":
                    raise Boom()

            def prenext(self):
                if where == "prenext":
                    raise Boom()

            def next(self):
                if where == "next":
                    raise Boom()
                self.n += 1
                if self.n == 3:
                    self.buy(size=1)
                elif self.n == 6:
                    self.sell(size=1)

            def stop(self):
                if where == "stop":
                    raise Boom()

            def notify_order(self, order):
                if where == "notify_order":
                    raise Boom()

            def notify_trade(self, trade):
                if where == "notify_trade":
                    raise Boom()

            def notify_cashvalue(self, cash, value):
                if where == "notify_cashvalue":
                    raise Boom()

        return Raiser

    @pytest.mark.parametrize(
        "where",
        [
            "__init__",
            "start",
            "prenext",
            "next",
            "stop",
            "notify_order",
            "notify_trade",
            "notify_cashvalue",
        ],
    )
    def test_strategy_callbacks_propagate(self, where):
        with pytest.raises(Boom):
            run_strategy(self.strategy_raising_in(where))

    @pytest.mark.parametrize(
        "where", ["__init__", "start", "next", "stop", "notify_order"]
    )
    def test_analyzer_callbacks_propagate(self, where):
        class RaisingAnalyzer(bt.Analyzer):
            def __init__(self):
                if where == "__init__":
                    raise Boom()

            def start(self):
                if where == "start":
                    raise Boom()

            def next(self):
                if where == "next":
                    raise Boom()

            def stop(self):
                if where == "stop":
                    raise Boom()

            def notify_order(self, order):
                if where == "notify_order":
                    raise Boom()

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        # a trading strategy, so notify_order actually fires
        cerebro.addstrategy(self.strategy_raising_in("nowhere"))
        cerebro.addanalyzer(RaisingAnalyzer)
        with pytest.raises(Boom):
            cerebro.run()

    @pytest.mark.parametrize("where", ["start", "next"])
    def test_observer_callbacks_propagate(self, where):
        class RaisingObserver(bt.Observer):
            lines = ("x",)

            def start(self):
                if where == "start":
                    raise Boom()

            def next(self):
                if where == "next":
                    raise Boom()

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(bt.Strategy)
        cerebro.addobserver(RaisingObserver)
        with pytest.raises(Boom):
            cerebro.run()

    def test_sizer_propagates(self):
        class RaisingSizer(bt.Sizer):
            def _getsizing(self, comminfo, cash, data, isbuy):
                raise Boom()

        class Buyer(bt.Strategy):
            __test__ = False

            def next(self):
                self.buy()

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addsizer(RaisingSizer)
        cerebro.addstrategy(Buyer)
        with pytest.raises(Boom):
            cerebro.run()

    @pytest.mark.parametrize("runonce", [True, False])
    def test_indicator_propagates_in_both_execution_paths(self, runonce):
        class RaisingIndicator(bt.Indicator):
            lines = ("x",)

            def __init__(self):
                self.addminperiod(5)

            def next(self):
                raise Boom()

            def once(self, start, end):
                raise Boom()

        class Holder(bt.Strategy):
            __test__ = False

            def __init__(self):
                RaisingIndicator(self.data)

        with pytest.raises(Boom):
            run_strategy(Holder, runonce=runonce)

    def test_writer_propagates(self):
        class RaisingWriter(bt.WriterFile):
            def start(self):
                raise Boom()

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(bt.Strategy)
        cerebro.addwriter(RaisingWriter)
        with pytest.raises(Boom):
            cerebro.run()

    @pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit, MemoryError])
    def test_baseexception_is_never_swallowed(self, exc):
        """A bare `except:` would eat these; nothing may."""

        class Interrupted(bt.Strategy):
            __test__ = False

            def next(self):
                raise exc()

        with pytest.raises(exc):
            run_strategy(Interrupted)


class TestStrategySkipError:
    """The one exception the engine is supposed to swallow."""

    def test_a_skipping_strategy_is_dropped_from_the_run(self):
        class Skipper(bt.Strategy):
            __test__ = False

            def __init__(self):
                raise bt.errors.StrategySkipError()

        assert run_strategy(Skipper) == []

    def test_the_other_strategies_still_run(self):
        class Skipper(bt.Strategy):
            __test__ = False

            def __init__(self):
                raise bt.errors.StrategySkipError()

        class Keeper(bt.Strategy):
            __test__ = False

            def stop(self):
                self.myresult = len(self)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(Skipper)
        cerebro.addstrategy(Keeper)
        strats = cerebro.run()
        assert len(strats) == 1
        assert strats[0].myresult == 255

    def test_skip_error_is_a_backtrader_error(self):
        assert issubclass(bt.errors.StrategySkipError, bt.errors.BacktraderError)


class TestOptimizationSurfacesFailures:
    """A worker that dies must not leave the caller with a short result list."""

    @pytest.mark.parametrize("executor", ["process", "thread"])
    def test_a_raising_worker_reaches_the_caller(self, executor):
        cerebro = bt.Cerebro(stdstats=False, maxcpus=2, executor=executor)
        cerebro.adddata(csvdata())
        cerebro.optstrategy(OptBoom, period=[5, 10])
        with pytest.raises(Exception) as excinfo:
            cerebro.run()
        # the process pool cannot carry the class itself across, but it must
        # not swallow the failure either
        assert excinfo.type is not SystemExit

    def test_skipping_combinations_are_dropped_not_fatal(self):
        cerebro = bt.Cerebro(stdstats=False, maxcpus=1, optreturn=False)
        cerebro.adddata(csvdata())
        cerebro.optstrategy(OptSkipOdd, period=[5, 10, 15, 20])
        results = cerebro.run()
        # 10 and 20 survive; 5 and 15 skip themselves
        assert [r[0].p.period for r in results if r] == [10, 20]


class OptBoom(bt.Strategy):
    """Module level so a process pool can pickle it."""

    __test__ = False
    params = dict(period=10)

    def __init__(self):
        raise Boom()


class OptSkipOdd(bt.Strategy):
    __test__ = False
    params = dict(period=10)

    def __init__(self):
        if (self.p.period // 5) % 2:
            raise bt.errors.StrategySkipError()


class TestNonsenseOrdersAreRejectedAsNonsense:
    """An impossible order argument is refused as one, not as a margin call.

    A NaN size or price used to reach the broker intact and be turned into
    `Order.Margin` by the cash arithmetic - NaN compares false against
    everything, so `cash >= 0.0` fails - telling the strategy the account was
    short of money when it had asked for something meaningless.
    """

    def place(self, action):
        class Placer(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.n = 0
                self.result = "never ran"
                self.statuses = []

            def next(self):
                self.n += 1
                if self.n == 3:
                    self.result = action(self)

            def notify_order(self, order):
                self.statuses.append(order.getstatusname())

        return run_strategy(Placer)[0]

    def test_a_zero_size_order_is_not_placed_at_all(self):
        strat = self.place(lambda s: s.buy(size=0))
        assert strat.result is None
        assert strat.statuses == []

    def test_a_nan_size_is_refused_as_an_invalid_size(self):
        with pytest.raises(ValueError, match="size is NaN"):
            self.place(lambda s: s.buy(size=float("nan")))

    def test_an_infinite_size_is_refused_as_an_invalid_size(self):
        with pytest.raises(ValueError, match="size is infinite"):
            self.place(lambda s: s.buy(size=float("inf")))

    def test_a_nan_limit_price_is_refused_as_an_invalid_price(self):
        with pytest.raises(ValueError, match="price is NaN"):
            self.place(
                lambda s: s.buy(size=1, exectype=bt.Order.Limit, price=float("nan"))
            )

    def test_an_infinite_trailamount_is_refused(self):
        with pytest.raises(ValueError, match="trailamount is infinite"):
            self.place(
                lambda s: s.buy(
                    size=1, exectype=bt.Order.StopTrail, trailamount=float("inf")
                )
            )

    def test_a_negative_size_reaching_the_broker_directly_is_refused(self):
        # Strategy.buy() takes abs(size), so this is only reachable by calling
        # the broker itself - where a negative size would build a nonsense order
        with pytest.raises(ValueError, match="size is negative"):
            self.place(
                lambda s: s.broker.buy(s, s.data, size=-5, exectype=bt.Order.Market)
            )

    def test_a_sizeless_order_reaching_the_broker_directly_is_refused(self):
        with pytest.raises(ValueError, match="size is None"):
            self.place(
                lambda s: s.broker.buy(s, s.data, size=None, exectype=bt.Order.Market)
            )

    def test_strategy_buy_treats_size_as_a_magnitude(self):
        # documented behaviour: the direction comes from buy()/sell(), so a
        # negative size is normalised rather than rejected
        strat = self.place(lambda s: s.buy(size=-1))
        assert strat.result.size == 1
        assert "Completed" in strat.statuses

    def test_an_unaffordable_order_is_still_a_margin_rejection(self):
        # a genuine funding problem must keep saying so
        strat = self.place(lambda s: s.buy(size=10**18))
        assert "Margin" in strat.statuses

    def test_cancelling_nothing_does_not_raise(self):
        assert self.place(lambda s: s.cancel(None)).result is None

    def test_selling_without_a_position_opens_a_short(self):
        # Not an error: backtrader allows shorting by selling from flat
        strat = self.place(lambda s: s.sell(size=1))
        assert "Completed" in strat.statuses


class TestArithmeticGuards:
    """The narrow ZeroDivisionError handlers do what they promise."""

    def test_rsi_safediv_returns_infinity_at_the_boundary(self):
        class Holder(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.rsi = bt.indicators.RSI(self.data, safediv=True)

        strat = run_strategy(Holder)[0]
        # safehigh=100 makes (rsi - 100.0) exactly zero
        assert strat.rsi._rscalc(100.0) == float("inf")
        assert strat.rsi._rscalc(50.0) == pytest.approx(1.0)

    def test_sqn_reports_zero_rather_than_dividing_by_nothing(self):
        class OneTrade(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.n = 0

            def next(self):
                self.n += 1
                if self.n == 3:
                    self.buy(size=1)
                elif self.n == 6:
                    self.sell(size=1)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(csvdata())
        cerebro.addstrategy(OneTrade)
        cerebro.addanalyzer(bt.analyzers.SQN)
        strat = cerebro.run()[0]
        analysis = strat.analyzers.sqn.get_analysis()
        assert analysis["trades"] == 1
        assert analysis["sqn"] == 0  # a single trade has no deviation to divide by

    def test_an_indicator_over_a_constant_series_does_not_explode(self, tmp_path):
        # every bar identical: standard deviation is zero everywhere
        body = BT_HEADER + "".join(
            f"2006-01-{day:02d},10,10,10,10,100,0\n" for day in range(2, 28)
        )
        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(bt.feeds.BacktraderCSVData(dataname=write(tmp_path, body)))

        class Holder(bt.Strategy):
            __test__ = False

            def __init__(self):
                self.boll = bt.indicators.BollingerBands(self.data, period=5)
                self.rsi = bt.indicators.RSI(self.data, safediv=True)

            def stop(self):
                self.myresult = (self.boll.top[0], self.rsi[0])

        cerebro.addstrategy(Holder)
        strat = cerebro.run()[0]
        assert strat.myresult[0] == pytest.approx(10.0)  # no width, no crash


class TestUnorderedDataIsRejected:
    """A source that goes back in time is refused, not quietly believed.

    Unordered input is not a cosmetic problem: every indicator, the broker and
    every analyzer would go on computing against a timeline that never existed,
    and say nothing about it.
    """

    def dated(self, tmp_path, *days, **feedkwargs):
        body = BT_HEADER + "".join(
            f"2006-01-{day:02d},10,11,9,10.5,100,0\n" for day in days
        )
        seen = []

        class Recorder(bt.Strategy):
            __test__ = False

            def next(self):
                seen.append(self.data.datetime.date(0).day)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.adddata(
            bt.feeds.BacktraderCSVData(dataname=write(tmp_path, body), **feedkwargs)
        )
        cerebro.addstrategy(Recorder)
        cerebro.run()
        return seen

    def test_bars_in_order_are_accepted(self, tmp_path):
        assert self.dated(tmp_path, 2, 3, 4) == [2, 3, 4]

    def test_dates_running_backwards_are_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="before the previous bar"):
            self.dated(tmp_path, 4, 3, 2)

    def test_one_date_out_of_place_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="before the previous bar"):
            self.dated(tmp_path, 2, 9, 3)

    def test_the_message_names_the_bar_and_both_dates(self, tmp_path):
        with pytest.raises(ValueError) as excinfo:
            self.dated(tmp_path, 2, 9, 3)
        message = str(excinfo.value)
        assert "2006-01-03" in message  # the offending bar
        assert "2006-01-09" in message  # the one it should have followed
        assert "checkorder=False" in message  # and the way out

    def test_duplicate_timestamps_are_allowed(self, tmp_path):
        # tick data routinely carries several ticks within the same second,
        # so equal stamps must not be an error
        assert self.dated(tmp_path, 2, 2, 3) == [2, 2, 3]

    def test_checkorder_false_accepts_the_source_as_it_is(self, tmp_path):
        assert self.dated(tmp_path, 4, 3, 2, checkorder=False) == [4, 3, 2]

    def test_a_feed_can_be_replayed_through_a_second_cerebro(self, tmp_path):
        # the check resets per run: one data object driven twice must not see
        # the first run's last bar when the second run starts
        body = BT_HEADER + "".join(
            f"2006-01-{day:02d},10,11,9,10.5,100,0\n" for day in (2, 3, 4)
        )
        data = bt.feeds.BacktraderCSVData(dataname=write(tmp_path, body))
        for _ in range(2):
            cerebro = bt.Cerebro(stdstats=False)
            cerebro.adddata(data)
            cerebro.addstrategy(bt.Strategy)
            cerebro.run()

    def test_the_tracked_tick_fixture_still_loads(self):
        assert (
            len(
                bars_from(
                    datafile("ticksample.csv"),
                    feedcls=bt.feeds.GenericCSVData,
                    dtformat="%Y-%m-%dT%H:%M:%S.%f",
                    timeframe=bt.TimeFrame.Ticks,
                )
            )
            > 0
        )


class TestNoBareExcepts:
    """A mechanical check, because a rule nobody can run is decoration.

    A bare ``except:`` catches ``KeyboardInterrupt``, ``SystemExit`` and
    ``MemoryError`` along with everything else. Every one in the tree was
    either hiding a real failure or one keystroke away from doing so.
    """

    def sources(self):
        root = pathlib.Path(bt.__file__).parent
        return sorted(root.rglob("*.py"))

    def test_the_package_has_no_bare_except(self):
        offenders = []
        for path in self.sources():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if re.match(r"\s*except\s*:", line):
                    offenders.append(f"{path.name}:{number}")
        assert not offenders, "bare `except:` in:\n  " + "\n  ".join(offenders)

    def test_the_package_never_catches_baseexception(self):
        offenders = []
        for path in self.sources():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if re.match(r"\s*except\s+BaseException", line):
                    offenders.append(f"{path.name}:{number}")
        assert not offenders, "catches BaseException in:\n  " + "\n  ".join(offenders)


class TestStoreBaseClass:
    """``Store`` has no subclass left in the tree, so nothing exercised it.

    Every store integration was deleted during the slimming; the class remains
    as the extension point third-party stores build on. These tests cover the
    contract that is left of it.
    """

    def store(self):
        # a fresh subclass each time: MetaSingleton caches one instance per class
        return type("ProbeStore", (bt.Store,), {})

    def test_a_store_is_a_singleton_per_class(self):
        cls = self.store()
        assert cls() is cls()

    def test_two_store_classes_do_not_share_an_instance(self):
        assert self.store()() is not self.store()()

    def test_start_is_idempotent(self):
        store = self.store()()
        store.start()
        store.put_notification("kept")
        store.start()  # must not wipe the queue it already set up
        assert store.get_notifications() == [("kept", (), {})]

    def test_notifications_round_trip_with_args(self):
        store = self.store()()
        store.start()
        store.put_notification("msg", 1, two=2)
        assert store.get_notifications() == [("msg", (1,), {"two": 2})]

    def test_notifications_drain(self):
        store = self.store()()
        store.start()
        store.put_notification("one")
        assert len(store.get_notifications()) == 1
        assert store.get_notifications() == []

    def test_notifications_keep_their_order(self):
        store = self.store()()
        store.start()
        for i in range(5):
            store.put_notification(i)
        assert [msg for msg, _, _ in store.get_notifications()] == [0, 1, 2, 3, 4]

    def test_a_none_message_cannot_be_mistaken_for_the_drain_sentinel(self):
        # get_notifications() marks the end of the queue with a bare None;
        # put_notification always appends a 3-tuple, so a None *message* is
        # still safe to send
        store = self.store()()
        store.start()
        store.put_notification(None)
        assert store.get_notifications() == [(None, (), {})]

    def test_starting_with_a_broker_registers_it(self):
        store = self.store()()
        broker = object()
        store.start(broker=broker)
        assert store.broker is broker

    def test_getdata_without_a_dataclass_says_what_is_missing(self):
        with pytest.raises(NotImplementedError, match="DataCls"):
            self.store()().getdata()

    def test_getbroker_without_a_brokerclass_says_what_is_missing(self):
        with pytest.raises(NotImplementedError, match="BrokerCls"):
            self.store()().getbroker()

    def test_stop_is_a_no_op_on_the_base_class(self):
        store = self.store()()
        store.start()
        assert store.stop() is None
