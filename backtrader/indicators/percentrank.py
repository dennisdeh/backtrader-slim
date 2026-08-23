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

from math import fsum

from . import BaseApplyN

__all__ = ["PercentRank", "PctRank"]


class PercentRank(BaseApplyN):
    """
    Measures the percent rank of the current value with respect to that of
    period bars ago
    """

    lines = ("pctrank",)
    params = (
        ("period", 50),
        ("func", lambda d: fsum(x < d[-1] for x in d) / len(d)),
    )


# Declared rather than left to the `alias` directive above. A generated alias
# is invisible to a reader and to a static checker: this module names it, so it
# is written out. The class the directive would have built is exactly this - a
# subclass of the original carrying its docstring and its `aliased` marker.


class PctRank(PercentRank):
    __doc__ = PercentRank.__doc__
    aliased = "PercentRank"
