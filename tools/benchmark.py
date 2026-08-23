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
"""Measure where the engine spends its time.

A performance claim in ``changelog.txt`` needs a number, the command that
produced it and a date; this script is that command.  It is offline and
deterministic - it reads only the tracked fixtures in ``datas/``.

    python tools/benchmark.py                # every suite
    python tools/benchmark.py core           # engine phases only
    python tools/benchmark.py indicators     # per-indicator cost
    python tools/benchmark.py profile        # cProfile of the hot path

Timings are reported as the *minimum* of N repetitions.  The minimum is the
least noisy estimator here: a run can be delayed by the scheduler or the GC,
never sped up, so the floor is the closest thing to the true cost.
"""

import argparse
import cProfile
import gc
import io
import pstats
import subprocess
import sys
import time
from pathlib import Path

import backtrader as bt

ROOT = Path(__file__).resolve().parent.parent
DATAS = ROOT / "datas"

# 4713 daily bars - long enough that per-bar cost dominates fixed setup cost.
BIGFILE = DATAS / "yhoo-1996-2014.txt"


def feed():
    return bt.feeds.YahooFinanceCSVData(dataname=str(BIGFILE))


def bars():
    """Number of bars the benchmark feed yields, for per-bar figures."""
    with open(BIGFILE) as f:
        return sum(1 for _ in f) - 1  # minus the header


def timeit(fn, repeat=5):
    best = float("inf")
    for _ in range(repeat):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


# ---------------------------------------------------------------- strategies


class Empty(bt.Strategy):
    """Measures the engine floor: iteration with nothing attached."""


class OneSMA(bt.Strategy):
    def __init__(self):
        bt.indicators.SMA(self.data, period=30)


class TenIndicators(bt.Strategy):
    """A realistic-ish load: ten common indicators on one feed."""

    def __init__(self):
        d = self.data
        bt.indicators.SMA(d, period=30)
        bt.indicators.EMA(d, period=30)
        bt.indicators.RSI(d)
        bt.indicators.MACD(d)
        bt.indicators.ATR(d)
        bt.indicators.BollingerBands(d)
        bt.indicators.Stochastic(d)
        bt.indicators.CCI(d)
        bt.indicators.DirectionalMovement(d)
        bt.indicators.WilliamsR(d)


def run(strategy, **cerebrokwargs):
    cerebrokwargs.setdefault("stdstats", False)

    def _run():
        cerebro = bt.Cerebro(**cerebrokwargs)
        cerebro.adddata(feed())
        cerebro.addstrategy(strategy)
        cerebro.run()

    return _run


def load_only():
    # _start() reaches for _env (the owning cerebro) to pick up the trading
    # calendar, so a feed cannot be started standalone.
    cerebro = bt.Cerebro(stdstats=False)
    data = feed()
    cerebro.adddata(data)
    data._start()
    data.preload()
    data.stop()


# --------------------------------------------------------------- core suite


CORE_CASES = [
    ("feed: load + preload only", load_only),
    ("empty strategy: runonce + preload", run(Empty, runonce=True, preload=True)),
    ("empty strategy: next mode", run(Empty, runonce=False, preload=True)),
    ("empty strategy: no preload", run(Empty, runonce=False, preload=False)),
    ("1 indicator: runonce + preload", run(OneSMA, runonce=True, preload=True)),
    ("1 indicator: next mode", run(OneSMA, runonce=False, preload=True)),
    (
        "10 indicators: runonce + preload",
        run(TenIndicators, runonce=True, preload=True),
    ),
    ("10 indicators: next mode", run(TenIndicators, runonce=False, preload=True)),
    (
        "10 indicators: exactbars=-2",
        run(TenIndicators, runonce=False, preload=True, exactbars=-2),
    ),
    ("empty strategy: stdstats observers on", run(Empty, stdstats=True)),
]


def suite_core(args):
    nbars = bars()
    print(f"\n== core ==  ({nbars} bars, best of {args.repeat})\n")
    print(f"{'case':<44}{'ms':>9}{'us/bar':>10}")
    print("-" * 63)
    for name, fn in CORE_CASES:
        secs = timeit(fn, args.repeat)
        print(f"{name:<44}{secs * 1000:>9.1f}{secs / nbars * 1e6:>10.1f}")


# --------------------------------------------------------- indicators suite


def indicator_classes():
    """Every built-in indicator that a single data feed is enough to build."""
    skip = {
        # need a second data feed, external packages or explicit parameters
        "OLS_Slope_InterceptN",
        "OLS_TransformationN",
        "OLS_BetaN",
        "CointN",
    }
    seen, out = set(), []
    for name in dir(bt.indicators):
        if name.startswith("_") or name in skip:
            continue
        cls = getattr(bt.indicators, name)
        if not isinstance(cls, type) or not issubclass(cls, bt.Indicator):
            continue
        if cls in seen:  # aliases point at one class; measure it once
            continue
        seen.add(cls)
        out.append((name, cls))
    return sorted(out)


def suite_indicators(args):
    nbars = bars()
    print(f"\n== indicators ==  ({nbars} bars, best of {args.repeat})\n")

    baseline = timeit(run(Empty, runonce=True, preload=True), args.repeat)
    print(f"engine floor (empty strategy, runonce): {baseline * 1000:.1f} ms\n")

    rows, failed = [], []
    for name, cls in indicator_classes():

        class _Strat(bt.Strategy):
            _ind = cls

            def __init__(self):
                self._ind(self.data)

        for mode in ("runonce", "next"):
            try:
                secs = timeit(
                    run(_Strat, runonce=(mode == "runonce"), preload=True),
                    args.repeat,
                )
            except Exception as exc:  # noqa: BLE001 - a survey, not a test
                failed.append((name, mode, type(exc).__name__))
                break
            rows.append((name, mode, max(secs - baseline, 0.0)))

    net = {}
    for name, mode, secs in rows:
        net.setdefault(name, {})[mode] = secs

    print(f"{'indicator':<32}{'runonce ms':>12}{'next ms':>10}{'next/once':>11}")
    print("-" * 65)
    ranked = sorted(net.items(), key=lambda kv: -max(kv[1].values()))
    for name, modes in ranked[: args.top]:
        once, nxt = modes.get("runonce", 0.0), modes.get("next", 0.0)
        ratio = (nxt / once) if once > 1e-6 else float("nan")
        print(f"{name:<32}{once * 1000:>12.1f}{nxt * 1000:>10.1f}{ratio:>11.1f}")

    print(
        f"\nmeasured {len(net)} indicators; showing the slowest {min(args.top, len(net))}"
    )
    if failed:
        print("could not build with a bare data feed:")
        for name, mode, exc in failed:
            print(f"  {name} ({mode}): {exc}")


# ------------------------------------------------------------ profile suite


def suite_profile(args):
    print(f"\n== profile ==  (10 indicators, runonce + preload)\n")
    prof = cProfile.Profile()
    prof.enable()
    run(TenIndicators, runonce=True, preload=True)()
    prof.disable()
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(args.top)
    print(buf.getvalue())

    print(f"\n== profile ==  (10 indicators, next mode)\n")
    prof = cProfile.Profile()
    prof.enable()
    run(TenIndicators, runonce=False, preload=True)()
    prof.disable()
    buf = io.StringIO()
    pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(args.top)
    print(buf.getvalue())


# ------------------------------------------------------------- import suite


def suite_import(args):
    print(f"\n== import ==  (best of {args.repeat}, cold interpreter each time)\n")
    best = float("inf")
    for _ in range(args.repeat):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "import backtrader"],
            check=True,
            capture_output=True,
        )
        best = min(best, time.perf_counter() - t0)

    bare = float("inf")
    for _ in range(args.repeat):
        t0 = time.perf_counter()
        subprocess.run([sys.executable, "-c", "pass"], check=True, capture_output=True)
        bare = min(bare, time.perf_counter() - t0)

    print(f"bare interpreter start : {bare * 1000:>7.1f} ms")
    print(f"+ import backtrader    : {best * 1000:>7.1f} ms")
    print(f"= cost of the package  : {(best - bare) * 1000:>7.1f} ms")
    print(
        "\nfor a per-module split, run:\n"
        "  python -X importtime -c 'import backtrader' 2>&1 | sort -t'|' -k2 -rn | head -30"
    )


SUITES = {
    "core": suite_core,
    "indicators": suite_indicators,
    "profile": suite_profile,
    "import": suite_import,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "suites",
        nargs="*",
        choices=sorted(SUITES) + [[]],
        default=[],
        help="suites to run (default: all)",
    )
    parser.add_argument("--repeat", type=int, default=5, help="repetitions per case")
    parser.add_argument("--top", type=int, default=25, help="rows of output per table")
    args = parser.parse_args()

    for name in args.suites or sorted(SUITES):
        SUITES[name](args)


if __name__ == "__main__":
    main()
