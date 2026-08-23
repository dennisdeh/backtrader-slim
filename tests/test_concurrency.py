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
"""Running more than one thing at a time.

Two separate questions live here.

**Optimization** spreads parameter combinations over a
:mod:`concurrent.futures` pool, chosen by ``Cerebro``'s ``executor``. Whichever
pool runs it, the results must equal what a single worker produces, in the same
order.

**Independent cerebros in threads** must not see each other. The engine keeps
one piece of genuinely process-wide mutable state - the object cache behind
``objcache``, which ``cerebro.run()`` clears and toggles on every call - and
that state is what these tests pin down.

The strategies are module-level classes on purpose: a process pool has to
pickle them, and a class defined inside a test function cannot be pickled.
"""

import threading

import pytest

import backtrader as bt
from backtrader.indicator import MetaIndicator
from backtrader.linebuffer import MetaLineActions
from backtrader.metabase import ObjectCache

from conftest import csvdata

PERIODS = [5, 10, 15, 20]

# What the four PERIODS produce; asserted rather than merely compared so a
# silently-empty result set cannot pass every "they agree" test in this file.
EXPECTED = [4114.212, 4117.964, 4095.012, 4065.884]


class OptStrategy(bt.Strategy):
    """One SMA, whose final value identifies the parameter combination."""

    __test__ = False

    params = dict(period=10)

    def __init__(self):
        self.sma = bt.indicators.SMA(self.data, period=self.p.period)

    def stop(self):
        self.myresult = round(self.sma[0], 6)


class ThreeIndicators(bt.Strategy):
    """Two identical SMAs and a third, different one.

    The duplicate is the point: with ``objcache`` on, both identical
    expressions resolve to one object and the strategy ends up with two
    indicators instead of three. That count is a direct readout of whether the
    cache was active for *this* run.
    """

    __test__ = False

    params = dict(started=None, waitfor=None)

    def __init__(self):
        # Signalling from inside __init__ pins the interleaving: cerebro.run()
        # has already done its cleancache()/usecache() prologue by the time a
        # strategy is being built.
        if self.p.started is not None:
            self.p.started.set()
        if self.p.waitfor is not None:
            assert self.p.waitfor.wait(timeout=30), "peer thread never started"

        self.a = bt.indicators.SMA(self.data, period=10)
        self.b = bt.indicators.SMA(self.data, period=10)  # identical to self.a
        self.c = bt.indicators.SMA(self.data, period=20)

    def stop(self):
        self.myresult = (round(self.a[0], 6), len(self.getindicators()))


def optcerebro(**kwargs):
    cerebro = bt.Cerebro(stdstats=False, optreturn=False, **kwargs)
    cerebro.adddata(csvdata())
    cerebro.optstrategy(OptStrategy, period=PERIODS)
    return cerebro


def runcerebro(strategy, stratkwargs=None, **kwargs):
    cerebro = bt.Cerebro(stdstats=False, **kwargs)
    cerebro.adddata(csvdata())
    cerebro.addstrategy(strategy, **(stratkwargs or {}))
    return cerebro.run()[0].myresult


class TestOptimizationExecutors:
    """Every pool must agree with the single-worker path."""

    def test_serial_optimization_is_the_reference(self):
        results = optcerebro(maxcpus=1).run()
        assert [r[0].myresult for r in results] == EXPECTED

    def test_process_pool_matches_serial(self):
        results = optcerebro(maxcpus=2, executor="process").run()
        assert [r[0].myresult for r in results] == EXPECTED

    def test_thread_pool_matches_serial(self):
        results = optcerebro(maxcpus=2, executor="thread").run()
        assert [r[0].myresult for r in results] == EXPECTED

    def test_all_cores_matches_serial(self):
        # maxcpus=None means "every core"; on a 1-core box this still has to
        # take the pool branch rather than fall back to the serial one.
        results = optcerebro(maxcpus=None).run()
        assert [r[0].myresult for r in results] == EXPECTED

    def test_results_keep_parameter_order(self):
        # executor.map yields in submission order; the pool must not reorder
        # results by completion time the way as_completed would.
        results = optcerebro(maxcpus=4, executor="thread").run()
        periods = [r[0].p.period for r in results]
        assert periods == PERIODS

    def test_unknown_executor_is_rejected(self):
        with pytest.raises(ValueError, match="executor must be one of"):
            optcerebro(maxcpus=2, executor="threads").run()

    def test_unknown_executor_is_rejected_even_when_serial(self):
        # The pool is never built with maxcpus=1, so a typo would otherwise
        # pass unnoticed until someone raised maxcpus.
        with pytest.raises(ValueError, match="executor must be one of"):
            optcerebro(maxcpus=1, executor="nonsense").run()

    def test_thread_workers_get_their_own_cerebro(self):
        # runstrategies() writes runningstrats/stcount onto the cerebro, so a
        # thread pool driving one shared instance would corrupt every result.
        cerebro = optcerebro(maxcpus=2, executor="thread")
        cerebro._dopreload = cerebro._dorunonce = False
        runner = cerebro._optrunner()
        assert runner is not cerebro

    def test_process_workers_use_the_cerebro_itself(self):
        cerebro = optcerebro(maxcpus=2, executor="process")
        assert cerebro._optrunner() is cerebro


class TestObjectCacheIsolation:
    """``ObjectCache`` keeps its state per thread."""

    def test_same_thread_reuses_the_cached_object(self):
        cache = ObjectCache()
        cache.enable(True)
        cache.clear()
        first = cache.obtain(object, int, (), {})
        second = cache.obtain(object, int, (), {})
        assert first is second

    def test_disabled_cache_always_builds(self):
        cache = ObjectCache()
        assert cache.enabled is False
        assert cache.obtain(object, int, (), {}) is not cache.obtain(
            object, int, (), {}
        )

    def test_unhashable_arguments_are_not_cached(self):
        cache = ObjectCache()
        cache.enable(True)
        cache.clear()
        unhashable = ([1, 2],)
        first = cache.obtain(object, int, unhashable, {})
        second = cache.obtain(object, int, unhashable, {})
        assert first is not second

    def test_enabled_flag_does_not_leak_into_another_thread(self):
        cache = ObjectCache()
        cache.enable(True)
        seen = []
        thread = threading.Thread(target=lambda: seen.append(cache.enabled))
        thread.start()
        thread.join()
        assert seen == [False]

    def test_entries_are_not_shared_between_threads(self):
        cache = ObjectCache()
        cache.enable(True)
        cache.clear()
        mine = cache.obtain(object, int, (), {})

        theirs = []

        def worker():
            cache.enable(True)
            cache.clear()
            theirs.append(cache.obtain(object, int, (), {}))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert theirs[0] is not mine

    def test_clearing_in_one_thread_keeps_another_threads_entries(self):
        cache = ObjectCache()
        cache.enable(True)
        cache.clear()
        mine = cache.obtain(object, int, (), {})

        thread = threading.Thread(target=cache.clear)
        thread.start()
        thread.join()

        assert cache.obtain(object, int, (), {}) is mine

    def test_the_metaclasses_each_own_a_cache(self):
        assert isinstance(MetaIndicator._objcache, ObjectCache)
        assert isinstance(MetaLineActions._objcache, ObjectCache)
        assert MetaIndicator._objcache is not MetaLineActions._objcache


class TestObjcacheParameter:
    """``objcache`` still does what it says, per run."""

    def test_off_by_default_every_expression_builds_its_own(self):
        assert runcerebro(ThreeIndicators) == (4117.964, 3)

    def test_on_the_duplicate_expression_is_shared(self):
        assert runcerebro(ThreeIndicators, objcache=True) == (4117.964, 2)

    def test_a_cached_run_does_not_change_the_next_one(self):
        runcerebro(ThreeIndicators, objcache=True)
        assert runcerebro(ThreeIndicators) == (4117.964, 3)


class TestConcurrentCerebros:
    """Independent cerebros running at the same time in different threads."""

    def test_a_cached_run_cannot_infect_a_concurrent_uncached_one(self):
        """The regression test for the process-wide object cache.

        The two threads are interleaved deliberately, not left to chance:

        1. the uncached cerebro runs its prologue, turning caching *off*
        2. it blocks inside its strategy's ``__init__``, before any indicator
           has been built
        3. the cached cerebro then runs its own prologue, turning caching *on*
        4. the uncached cerebro is released and builds its indicators

        With the flag held on the metaclass, step 3 reaches back into step 4
        and the uncached run silently gets two indicators instead of three.
        """
        uncached_started = threading.Event()
        cached_started = threading.Event()
        results = {}

        def uncached():
            results["uncached"] = runcerebro(
                ThreeIndicators,
                stratkwargs=dict(started=uncached_started, waitfor=cached_started),
            )

        def cached():
            assert uncached_started.wait(timeout=30)
            results["cached"] = runcerebro(
                ThreeIndicators,
                objcache=True,
                stratkwargs=dict(started=cached_started),
            )

        threads = [threading.Thread(target=uncached), threading.Thread(target=cached)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        for thread in threads:
            assert not thread.is_alive(), "a run deadlocked"

        assert results["uncached"] == (4117.964, 3)
        assert results["cached"] == (4117.964, 2)

    def test_many_independent_runs_in_threads_match_serial(self):
        expected = runcerebro(OptStrategy)
        results = [None] * 8

        def worker(slot):
            results[slot] = runcerebro(OptStrategy, objcache=bool(slot % 2))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert results == [expected] * 8
