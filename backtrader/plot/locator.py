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

"""Date ticks for the index-based x axis.

The plot draws bar ``i`` at ``x == i``, so non-trading time leaves no gaps.
Tick placement and labels therefore have to translate between bar indices and
dates. Both classes delegate the calendar logic to matplotlib's own
``AutoDateLocator`` and ``ConciseDateFormatter``, after converting the bars'
datetimes to matplotlib date numbers. Backtrader's date numbers count from
year 1, while matplotlib's count from 1970, so the two are never mixed.
"""

import bisect
import datetime
import math

import matplotlib.dates as mdates
import matplotlib.ticker as mticker

from ..utils import num2date

_UTC = datetime.timezone.utc


def bars_to_mpl(xdates, tz=None, floor_to_day=False):
    """Matplotlib date numbers for backtrader date numbers ``xdates``.

    The bars' wall-clock time in ``tz`` (the data feed's timezone, or the time
    as stored when it is ``None``) is kept as naive UTC, so ticks fall on that
    calendar's boundaries. ``floor_to_day`` drops the session-end time daily
    and longer bars are stamped with."""
    out = []
    for x in xdates:
        dt = num2date(x, tz=tz)
        if floor_to_day:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        out.append(mdates.date2num(dt))
    return out


class DateIndexLocator(mticker.Locator):
    """Places ticks on calendar boundaries, at the first bar on or after each.

    ``mdates_seq`` holds one matplotlib date number per bar, ascending. After
    each call, ``nominal`` maps every tick index to the date it stands for:
    the calendar boundary itself, or the bar's own date when several
    boundaries fall in one gap (a weekend, an overnight close)."""

    def __init__(self, mdates_seq, minticks=3, maxticks=None):
        self._num = list(mdates_seq)
        self.datelocator = mdates.AutoDateLocator(
            tz=_UTC, minticks=minticks, maxticks=maxticks
        )
        self.nominal = {}

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        nbars = len(self._num)
        lo, hi = sorted((vmin, vmax))
        i0 = max(0, math.ceil(lo))
        i1 = min(nbars - 1, math.floor(hi))
        if i0 > i1:
            self.nominal = {}
            return []

        dmin, dmax = self._num[i0], self._num[i1]
        if dmin == dmax:
            self.nominal = {i0: dmin}
            return [i0]

        hits = {}
        span = (mdates.num2date(dmin, tz=_UTC), mdates.num2date(dmax, tz=_UTC))
        for t in self.datelocator.tick_values(*span):
            if dmin <= t <= dmax:
                hits.setdefault(bisect.bisect_left(self._num, t), []).append(t)

        self.nominal = {
            i: ts[0] if len(ts) == 1 else self._num[i] for i, ts in hits.items()
        }
        return sorted(self.nominal)

    def barnum(self, x):
        """Matplotlib date number of the bar at index ``x`` (clamped)."""
        return self._num[min(max(int(round(x)), 0), len(self._num) - 1)]

    def num(self, x):
        """The tick's nominal date if ``x`` is a tick, else its bar's date."""
        return self.nominal.get(int(round(x)), self.barnum(x))


class DateIndexFormatter(mticker.Formatter):
    """Labels bar indices with dates.

    With ``fmt`` set, every label is the tick's bar formatted with
    ``strftime(fmt)``. Without it, labels are matplotlib's concise ones for
    the calendar boundary each tick marks: only what changes from tick to
    tick, with the rest (the year, for instance) shown once as the offset."""

    def __init__(self, locator, fmt=None):
        self.locator = locator
        self.fmt = fmt
        self._concise = None
        if fmt is None:
            self._concise = mdates.ConciseDateFormatter(locator.datelocator, tz=_UTC)

    def format_ticks(self, values):
        if self._concise is None:
            return [
                mdates.num2date(self.locator.barnum(v), tz=_UTC).strftime(self.fmt)
                for v in values
            ]
        return self._concise.format_ticks([self.locator.num(v) for v in values])

    def __call__(self, x, pos=None):
        return self.format_ticks([x])[0]

    def get_offset(self):
        return "" if self._concise is None else self._concise.get_offset()
