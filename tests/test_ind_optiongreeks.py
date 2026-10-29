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
"""OptionGreeks across the whole runonce x preload x exactbars matrix.

The fixture ``datas/2006-day-001-c4000.txt`` is a 4000 call on the 2006 daily
data, priced by Black-Scholes at 20% volatility and a 3% rate
(``fixture_text`` below regenerates it). So the implied volatility must come
back as 0.200000 on every bar, and the greeks must be Black-Scholes' at 20%.
Checked by hand for 2006-01-02: S = 3604.33, T = 347/365 = 0.9507, so
d1 = (ln(3604.33/4000) + (0.03 + 0.02) * 0.9507) / (0.2 * sqrt(0.9507))
   = -0.2903, and delta = N(d1) = 0.3858.
"""

import datetime
import itertools

import pytest

import backtrader as bt
from backtrader.options import OptionContract, OptionCSVData, OptionGreeks, pricing

from conftest import csvdata, datafile

FIXTURE = "2006-day-001-c4000.txt"
STRIKE, EXPIRY, RATE, VOL = 4000.0, datetime.date(2006, 12, 15), 0.03, 0.20
CONTRACT = OptionContract("und", STRIKE, EXPIRY, "C")

# (date, iv, delta, gamma, vega per point, theta per day) at the last bar,
# the first bar and the midpoint. Expiry day has no time value left, so
# nothing can be implied from it.
CHKVALS = [
    ("2006-12-15", "nan", "nan", "nan", "nan", "nan"),
    ("2006-01-02", "0.200000", "0.385766", "0.000544", "13.441385", "-0.487595"),
    ("2006-06-27", "0.200000", "0.214800", "0.000608", "7.009861", "-0.467320"),
]


def fixture_text(underlying_text):
    """The fixture, regenerated: priced from the underlying's OHLC, quoted to
    four decimals with a bid/ask half a percent (at least 0.05) either side."""
    out = ["Date,Open,High,Low,Close,Volume,OpenInterest,Bid,Ask"]
    for line in underlying_text.splitlines()[1:]:
        d, o, h, l, c = line.split(",")[:5]
        day = datetime.date.fromisoformat(d)
        if day > EXPIRY:
            break
        T = (EXPIRY - day).days / 365.0

        def px(s):
            return pricing.bsm("C", float(s), STRIKE, T, RATE, VOL).price

        po, ph, pl, pc = px(o), px(h), px(l), px(c)
        half = max(0.05, round(0.005 * pc, 2))
        bid, ask = max(pc - half, 0.0), pc + half
        out.append(f"{d},{po:.4f},{ph:.4f},{pl:.4f},{pc:.4f},0,0,{bid:.4f},{ask:.4f}")
    return "\n".join(out) + "\n"


def option_feed():
    return OptionCSVData(
        dataname=datafile(FIXTURE), dtformat="%Y-%m-%d", bid=7, ask=8, contract=CONTRACT
    )


class Probe(bt.Strategy):
    params = (("greeks", {}),)

    def __init__(self):
        self.g = OptionGreeks(self.datas[1], self.datas[0], **self.p.greeks)

    def stop(self):
        n = len(self.g)
        self.checks = [
            (self.datas[1].datetime.date(ago).isoformat(),)
            + tuple(f"{line[ago]:.6f}" for line in self.g.lines)
            for ago in (0, -n + 1, (-n + 1) // 2)
        ]


def _run(runonce=True, preload=True, exactbars=False, **greeks):
    cerebro = bt.Cerebro(
        runonce=runonce, preload=preload, exactbars=exactbars, stdstats=False
    )
    cerebro.adddata(csvdata(), name="und")
    cerebro.addoption(option_feed(), name="opt")
    cerebro.addstrategy(Probe, greeks=dict(rate=RATE) | greeks)
    return cerebro.run()[0]


def test_the_fixture_is_what_its_generator_writes():
    with open(datafile("2006-day-001.txt")) as f:
        expected = fixture_text(f.read())
    with open(datafile(FIXTURE)) as f:
        assert f.read() == expected


@pytest.mark.parametrize(
    "runonce,preload,exactbars",
    list(itertools.product((True, False), (True, False), (-2, -1, False))),
)
def test_greeks_in_every_mode(runonce, preload, exactbars):
    assert _run(runonce, preload, exactbars).checks == CHKVALS


def test_the_greeks_are_black_scholes_at_the_implied_volatility():
    date, iv, *greeks = CHKVALS[1]
    S, T = 3604.33, (EXPIRY - datetime.date.fromisoformat(date)).days / 365
    g = pricing.bsm("C", S, STRIKE, T, RATE, float(iv))
    expected = (g.delta, g.gamma, g.vega / 100, g.theta / 365)
    # the golden values are rounded to six decimals, and the quotes to four,
    # so the implied volatility is 0.2 only to about 1e-7
    assert [float(x) for x in greeks] == pytest.approx(expected, abs=1e-6)


def test_mid_prices_imply_close_to_the_same_volatility():
    # the quotes sit symmetrically around the model price
    checks = _run(price="mid").checks
    assert float(checks[1][1]) == pytest.approx(VOL, abs=1e-4)


@pytest.mark.parametrize(
    "kw,match",
    [(dict(model="heston"), "model"), (dict(price="last"), "price")],
)
def test_unknown_settings_are_refused(kw, match):
    with pytest.raises(ValueError, match=match):
        _run(**kw)


def test_the_option_feed_must_come_first():
    class Backwards(bt.Strategy):
        def __init__(self):
            OptionGreeks(self.datas[0], self.datas[1])

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(csvdata(), name="und")
    cerebro.addoption(option_feed(), name="opt")
    cerebro.addstrategy(Backwards)
    with pytest.raises(ValueError, match="option feed first"):
        cerebro.run()
