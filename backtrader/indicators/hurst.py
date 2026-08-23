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

from . import PeriodN

__all__ = ["HurstExponent", "Hurst"]

# numpy is optional: `import backtrader` must not require it, so it is imported
# on first use. The names are declared here rather than left to the metaclass
# `frompackages` directive, which injected them into this module's globals from
# outside - and into every base class's module besides. What next() refers to is
# now visible to a reader, and to a static checker, which reported all six as
# undefined and so could not see a genuine mistake anywhere in this file.
asarray = log10 = polyfit = sqrt = std = subtract = None


def _importnumpy():
    """Bind the numpy names used below. Called on first construction."""
    global asarray, log10, polyfit, sqrt, std, subtract
    try:
        from numpy import asarray, log10, polyfit, sqrt, std, subtract
    except ImportError:
        raise ImportError(
            "HurstExponent needs numpy, which is not installed: pip install numpy"
        ) from None


class HurstExponent(PeriodN):
    """
     References:

       - https://www.quantopian.com/posts/hurst-exponent
       - https://www.quantopian.com/posts/some-code-from-ernie-chans-new-book-implemented-in-python

    Interpretation of the results

       1. Geometric random walk (H=0.5)
       2. Mean-reverting series (H<0.5)
       3. Trending Series (H>0.5)

     Important notes:

       - The default period is ``40``, but experimentation by users has shown
         that it would be advisable to have at least 2000 samples (i.e.: a
         period of at least 2000) to have stable values.

       - The `lag_start` and `lag_end` values will default to be ``2`` and
         ``self.p.period / 2`` unless the parameters are specified.

         Experimentation by users has also shown that values of around ``10``
         and ``500`` produce good results

     The original values (40, 2, self.p.period / 2) are kept for backwards
     compatibility

    """

    alias = ("Hurst",)
    lines = ("hurst",)
    params = (
        ("period", 40),  # 2000 was proposed
        ("lag_start", None),  # 10 was proposed
        ("lag_end", None),  # 500 was proposed
    )

    def _plotlabel(self):
        plabels = [self.p.period]
        plabels += [self._lag_start]
        plabels += [self._lag_end]
        return plabels

    def __init__(self):
        super(HurstExponent, self).__init__()
        _importnumpy()
        # Prepare the lags array
        self._lag_start = lag_start = self.p.lag_start or 2
        self._lag_end = lag_end = self.p.lag_end or (self.p.period // 2)
        self.lags = asarray(range(lag_start, lag_end))
        self.log10lags = log10(self.lags)

    def next(self):
        # Fetch the data
        ts = asarray(self.data.get(size=self.p.period))

        # Calculate the array of the variances of the lagged differences
        tau = [sqrt(std(subtract(ts[lag:], ts[:-lag]))) for lag in self.lags]

        # Use a linear fit to estimate the Hurst Exponent
        poly = polyfit(self.log10lags, log10(tau), 1)

        # Return the Hurst exponent from the polyfit output
        self.lines.hurst[0] = poly[0] * 2.0
