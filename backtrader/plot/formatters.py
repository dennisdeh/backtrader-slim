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

import matplotlib.ticker as mplticker

from ..utils import num2date


class MyVolFormatter(mplticker.Formatter):
    Suffixes = ["", "K", "M", "G", "T", "P"]

    def __init__(self, volmax):
        self.volmax = volmax
        magnitude = 0
        self.divisor = 1.0
        while abs(volmax / self.divisor) >= 1000:
            magnitude += 1
            self.divisor *= 1000.0

        self.suffix = self.Suffixes[magnitude]

    def __call__(self, y, pos=0):
        """Return the label for time x at position pos"""

        if y > self.volmax * 1.20:
            return ""

        y = int(y / self.divisor)
        return "%d%s" % (y, self.suffix)


class MyDateFormatter(mplticker.Formatter):
    """Formats a bar index as its bar's datetime with ``fmt``, in ``tz`` (the
    data feed's timezone; ``None`` keeps the time as stored)."""

    def __init__(self, dates, fmt="%Y-%m-%d", tz=None):
        self.dates = dates
        self.lendates = len(dates)
        self.fmt = fmt
        self.tz = tz

    def __call__(self, x, pos=0):
        """Return the label for time x at position pos"""
        ind = min(max(int(round(x)), 0), self.lendates - 1)
        return num2date(self.dates[ind], tz=self.tz).strftime(self.fmt)
