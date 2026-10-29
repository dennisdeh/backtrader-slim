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
"""Data feeds for option contracts.

An option feed is an ordinary data feed - its OHLC are the option's premium
per unit - carrying an ``OptionContract`` and two more lines, ``bid`` and
``ask``. Add it with ``cerebro.addoption``, which also registers an
``OptionCommInfo`` with the contract's multiplier.
"""

from ..feeds import GenericCSVData, PandasData

__all__ = ["OptionCSVData", "OptionPandasData"]


class _OptionFeed:
    """What every option feed adds: the contract, checked at start.

    It goes *after* the feed class in the bases: the lines metaclass takes the
    first base as the primary one and copies the lines of every other base,
    so a mixin listed first would duplicate them all."""

    @property
    def contract(self):
        return self.p.contract

    def mid(self, ago=0):
        """The bid/ask midpoint ``ago`` bars back; the close if either is
        missing."""
        bid, ask = self.lines.bid[ago], self.lines.ask[ago]
        if bid == bid and ask == ask:  # neither is NaN
            return 0.5 * (bid + ask)
        return self.lines.close[ago]

    def _checkcontract(self):
        if self.p.contract is None:
            raise ValueError(f"{type(self).__name__} needs a contract=")


class OptionCSVData(GenericCSVData, _OptionFeed):
    """``GenericCSVData`` for an option. ``bid``/``ask`` are column indices
    like every other line (-1: not in the file)."""

    lines = ("bid", "ask")
    params = (("contract", None), ("bid", -1), ("ask", -1))

    def start(self):
        self._checkcontract()
        super().start()


class OptionPandasData(PandasData, _OptionFeed):
    """``PandasData`` for an option. ``bid``/``ask`` columns are found by
    name, as ``close`` is."""

    lines = ("bid", "ask")
    params = (("contract", None), ("bid", -1), ("ask", -1))

    def start(self):
        self._checkcontract()
        super().start()
