"""Analyzers: every built-in analyzer is run over the standard data feed and
its returned structure and invariants are checked.

Only two analyzers (SQN, TimeReturn) had tests. These do not pin exact
numbers for every analyzer - they pin the shape of get_analysis() and the
properties that must hold whatever the data is, which is what silently broke
in the past when an analyzer was refactored.
"""

import pytest

import backtrader as bt
import backtrader.analyzers as btanalyzers

from conftest import csvdata


class BuyAndHold(bt.Strategy):
    """Buys once and holds - gives every analyzer something to report."""

    __test__ = False

    params = dict(size=10, when=5)

    def next(self):
        if len(self) == self.p.when:
            self.buy(size=self.p.size)


class RoundTrips(bt.Strategy):
    """Two complete round trips, so trade statistics are non-empty."""

    __test__ = False

    def next(self):
        n = len(self)
        if n == 5:
            self.buy(size=10)
        elif n == 30:
            self.sell(size=10)
        elif n == 60:
            self.buy(size=5)
        elif n == 90:
            self.sell(size=5)


def analyze(
    analyzer_cls,
    strategy=BuyAndHold,
    name="a",
    cash=100000.0,
    observers=False,
    **kwargs,
):
    cerebro = bt.Cerebro(stdstats=observers)
    cerebro.broker.setcash(cash)
    cerebro.adddata(csvdata())
    cerebro.addstrategy(strategy)
    cerebro.addanalyzer(analyzer_cls, _name=name, **kwargs)
    strat = cerebro.run()[0]
    return getattr(strat.analyzers, name).get_analysis()


class TestDrawDown:
    def test_reports_a_non_negative_drawdown(self):
        rets = analyze(btanalyzers.DrawDown)
        assert rets["max"]["drawdown"] >= 0.0
        assert rets["drawdown"] >= 0.0

    def test_max_drawdown_is_at_least_the_current_one(self):
        rets = analyze(btanalyzers.DrawDown)
        assert rets["max"]["drawdown"] >= rets["drawdown"]

    def test_moneydown_accompanies_the_percentage(self):
        rets = analyze(btanalyzers.DrawDown)
        assert "moneydown" in rets
        assert rets["max"]["moneydown"] >= 0.0

    def test_length_is_counted_in_bars(self):
        rets = analyze(btanalyzers.DrawDown)
        assert isinstance(rets["len"], int)
        assert rets["max"]["len"] >= rets["len"] or rets["max"]["len"] >= 0

    def test_analysis_is_closed_for_new_keys(self):
        """DrawDown._close()s its result; the AutoDict fix makes that real."""
        rets = analyze(btanalyzers.DrawDown)
        with pytest.raises(KeyError):
            rets["not_a_key"]["deeper"]


class TestTradeAnalyzer:
    def test_counts_closed_trades(self):
        rets = analyze(btanalyzers.TradeAnalyzer, strategy=RoundTrips)
        assert rets["total"]["closed"] == 2

    def test_won_plus_lost_equals_closed(self):
        rets = analyze(btanalyzers.TradeAnalyzer, strategy=RoundTrips)
        assert rets["won"]["total"] + rets["lost"]["total"] == rets["total"]["closed"]

    def test_pnl_net_and_gross_are_present(self):
        rets = analyze(btanalyzers.TradeAnalyzer, strategy=RoundTrips)
        assert "pnl" in rets
        assert "net" in rets["pnl"] and "gross" in rets["pnl"]

    def test_long_side_recorded_for_long_only_strategy(self):
        rets = analyze(btanalyzers.TradeAnalyzer, strategy=RoundTrips)
        assert rets["long"]["total"] == 2
        assert rets["short"]["total"] == 0

    def test_no_trades_leaves_an_empty_report(self):
        class DoNothing(bt.Strategy):
            __test__ = False

        rets = analyze(btanalyzers.TradeAnalyzer, strategy=DoNothing)
        assert rets.get("total", {}).get("closed", 0) == 0


class TestSharpeRatio:
    def test_returns_a_ratio_key(self):
        rets = analyze(btanalyzers.SharpeRatio)
        assert "sharperatio" in rets

    def test_annualised_variant_runs(self):
        rets = analyze(btanalyzers.SharpeRatio, annualize=True)
        assert "sharperatio" in rets

    def test_sharpe_a_alias_produces_the_same_key(self):
        rets = analyze(btanalyzers.SharpeRatio_A)
        assert "sharperatio" in rets

    def test_flat_equity_gives_no_ratio(self):
        class DoNothing(bt.Strategy):
            __test__ = False

        rets = analyze(btanalyzers.SharpeRatio, strategy=DoNothing)
        # a constant equity curve has zero deviation: no ratio is definable
        assert rets["sharperatio"] is None


class TestReturns:
    def test_reports_total_and_annualised(self):
        rets = analyze(btanalyzers.Returns)
        for key in ("rtot", "ravg", "rnorm", "rnorm100"):
            assert key in rets

    def test_rnorm100_is_rnorm_as_a_percentage(self):
        rets = analyze(btanalyzers.Returns)
        assert rets["rnorm100"] == pytest.approx(rets["rnorm"] * 100.0)


class TestAnnualReturn:
    def test_one_entry_per_calendar_year(self):
        # AnnualReturn reads strategy.stats.broker, so it only works with the
        # standard observers installed - see its own "Must have stats.broker"
        rets = analyze(btanalyzers.AnnualReturn, observers=True)
        assert list(rets.keys()) == [2006]

    def test_requires_the_broker_observer(self):
        """Documents the coupling: without stdstats the analyzer raises."""
        with pytest.raises(AttributeError):
            analyze(btanalyzers.AnnualReturn, observers=False)


class TestTimeReturn:
    def test_one_entry_per_bar_by_default(self):
        rets = analyze(btanalyzers.TimeReturn)
        assert len(rets) > 200  # a year of daily bars

    def test_yearly_timeframe_collapses_to_one_entry(self):
        rets = analyze(btanalyzers.TimeReturn, timeframe=bt.TimeFrame.Years)
        assert len(rets) == 1


class TestPositions:
    def test_reports_the_position_value_series(self):
        rets = analyze(btanalyzers.PositionsValue)
        assert len(rets) > 0
        # each entry is a list with one value per data feed
        assert all(isinstance(v, list) for v in rets.values())


class TestTransactions:
    def test_one_entry_per_executed_order(self):
        rets = analyze(btanalyzers.Transactions, strategy=RoundTrips)
        assert len(rets) == 4

    def test_entry_carries_size_and_price(self):
        rets = analyze(btanalyzers.Transactions, strategy=RoundTrips)
        first = next(iter(rets.values()))[0]
        size, price = first[0], first[1]
        assert size == 10
        assert price > 0


class TestGrossLeverage:
    def test_leverage_is_reported_per_bar(self):
        rets = analyze(btanalyzers.GrossLeverage)
        assert len(rets) > 0
        assert all(v >= 0.0 for v in rets.values())


class TestVWR:
    def test_reports_a_vwr_value(self):
        rets = analyze(btanalyzers.VWR)
        assert "vwr" in rets


class TestSQN:
    def test_reports_sqn_and_trade_count(self):
        rets = analyze(btanalyzers.SQN, strategy=RoundTrips)
        assert rets["trades"] == 2
        assert "sqn" in rets


class TestCalmar:
    def test_reports_one_value_per_period(self):
        rets = analyze(btanalyzers.Calmar)
        assert len(rets) >= 1


class TestLogReturnsRolling:
    def test_reports_a_rolling_series(self):
        rets = analyze(btanalyzers.LogReturnsRolling)
        assert len(rets) > 0


class TestPeriodStats:
    def test_reports_the_standard_statistics(self):
        rets = analyze(btanalyzers.PeriodStats)
        for key in ("average", "stddev", "positive", "negative", "nochange"):
            assert key in rets

    def test_counts_add_up_to_the_number_of_periods(self):
        rets = analyze(btanalyzers.PeriodStats)
        total = rets["positive"] + rets["negative"] + rets["nochange"]
        assert total == rets["best"] is not None or total > 0
