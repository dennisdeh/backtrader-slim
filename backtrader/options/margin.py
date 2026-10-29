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
"""Margin models: how much cash a set of positions must keep in reserve.

The broker asks its margin model (``broker.set_margin_model``) twice: when an
order is submitted, about the positions the order would leave, and after
every bar, about the positions held. An order is refused (``Margin``) if
the cash after it would not cover the requirement. A breach after a bar is
reported to the strategies through ``notify_margin`` and nothing more.
"""

import collections
import math
from dataclasses import dataclass

__all__ = ["MarginModel", "CashCovered", "MarginCall"]


@dataclass(frozen=True)
class MarginCall:
    """What ``notify_margin`` receives while cash is short of the
    requirement. ``shortfall`` is ``inf`` if a position cannot be covered
    at all (a naked short call under ``CashCovered``)."""

    dt: object
    cash: float
    requirement: float
    shortfall: float


class MarginModel:
    """The interface: ``requirement`` returns the cash the positions must
    keep, or ``math.inf`` if they are not allowed at all."""

    def requirement(self, broker, positions):
        """``positions`` maps each data feed to a position size."""
        return 0.0


class CashCovered(MarginModel):
    """Every short position is backed by cash or by another position: no
    borrowing.

    For each underlying, across the whole portfolio:

    - A short call is covered by ``multiplier`` units of the underlying held
      long, anywhere in the portfolio, or by a long call on the same
      underlying expiring no earlier. Covered by a long call with a higher
      strike, it reserves the gap between the strikes (the spread's
      maximum loss). A short call with neither cover is not allowed.
    - A short put reserves its strike times the multiplier (cash-secured),
      less the strike of a long put on the same underlying expiring no
      earlier (a put spread reserves only the gap).
    - A short position in the underlying itself reserves its market value:
      the sale's proceeds stay as collateral.
    - Long positions are paid in full and reserve nothing.

    Covers are assigned greedily: stock first, then the cheapest long
    option.
    """

    def requirement(self, broker, positions):
        books = collections.defaultdict(lambda: dict(units=0.0, calls=[], puts=[]))
        for data, size in positions.items():
            if not size:
                continue
            c = getattr(data, "contract", None)
            if c is None:
                books[data._name]["units"] += size
            else:
                kind = "calls" if c.iscall else "puts"
                books[c.underlying][kind].append(
                    (size, c.strike, c.expiry, c.multiplier)
                )

        total = 0.0
        for name, book in books.items():
            if book["units"] < 0:
                und = broker.cerebro.datasbyname.get(name)
                price = und.close[0] if und is not None and len(und) else 0.0
                total += -book["units"] * price
            total += self._calls(book)
            if total == math.inf:
                return total
            total += self._puts(book)
        return total

    @staticmethod
    def _calls(book):
        shorts = sorted((k, e, m, -s) for s, k, e, m in book["calls"] if s < 0)
        longs = sorted([k, e, m, s] for s, k, e, m in book["calls"] if s > 0)
        units = max(book["units"], 0.0)
        need = 0.0
        for strike, expiry, mult, qty in shorts:
            covered = min(qty, units / mult)
            units -= covered * mult
            qty -= covered
            for long in longs:  # cheapest strike first
                if qty <= 0:
                    break
                if long[3] <= 0 or long[1] < expiry:
                    continue
                take = min(qty, long[3])
                long[3] -= take
                qty -= take
                need += take * max(long[0] - strike, 0.0) * mult
            if qty > 1e-12:
                return math.inf
        return need

    @staticmethod
    def _puts(book):
        shorts = sorted(
            ((k, e, m, -s) for s, k, e, m in book["puts"] if s < 0), reverse=True
        )
        longs = sorted(
            ([k, e, m, s] for s, k, e, m in book["puts"] if s > 0), reverse=True
        )
        need = 0.0
        for strike, expiry, mult, qty in shorts:
            for long in longs:  # highest strike first: the smallest gap
                if qty <= 0:
                    break
                if long[3] <= 0 or long[1] < expiry:
                    continue
                take = min(qty, long[3])
                long[3] -= take
                qty -= take
                need += take * max(strike - long[0], 0.0) * mult
            need += qty * strike * mult  # cash-secured
        return need
