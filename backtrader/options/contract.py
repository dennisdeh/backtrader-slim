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
"""What an option contract is: the terms that do not change while it trades."""

import datetime
from dataclasses import dataclass

from .pricing import CALL, PUT, normalize_right

__all__ = ["OptionContract", "AMERICAN", "EUROPEAN", "PHYSICAL", "CASH"]

AMERICAN, EUROPEAN = "american", "european"
PHYSICAL, CASH = "physical", "cash"


@dataclass(frozen=True)
class OptionContract:
    """The terms of one listed option.

    - ``underlying``: the name the underlying's data feed was added under
      (``cerebro.adddata(data, name=...)``). Expiry settles against that
      feed's close, and physical delivery trades it.
    - ``strike``, ``expiry`` (a ``date`` or ``"YYYY-MM-DD"``), ``right``
      (``"C"``/``"call"`` or ``"P"``/``"put"``).
    - ``multiplier``: units of the underlying per contract (100 for US equity
      and index options).
    - ``style``: ``"american"`` or ``"european"``. Both settle at expiry
      only; early exercise is not modelled yet.
    - ``settlement``: ``"physical"`` (delivers the underlying) or ``"cash"``
      (pays the intrinsic value).
    """

    underlying: str
    strike: float
    expiry: datetime.date
    right: str
    multiplier: float = 100.0
    style: str = AMERICAN
    settlement: str = PHYSICAL

    def __post_init__(self):
        expiry = self.expiry
        if isinstance(expiry, str):
            expiry = datetime.date.fromisoformat(expiry)
        elif isinstance(expiry, datetime.datetime):
            expiry = expiry.date()
        object.__setattr__(self, "expiry", expiry)
        object.__setattr__(self, "right", normalize_right(self.right))
        object.__setattr__(self, "strike", float(self.strike))
        object.__setattr__(self, "multiplier", float(self.multiplier))

        if self.strike <= 0.0 or self.multiplier <= 0.0:
            raise ValueError("strike and multiplier must be positive")
        if self.style not in (AMERICAN, EUROPEAN):
            raise ValueError(f"style is {AMERICAN!r} or {EUROPEAN!r}")
        if self.settlement not in (PHYSICAL, CASH):
            raise ValueError(f"settlement is {PHYSICAL!r} or {CASH!r}")

    @property
    def iscall(self):
        return self.right == CALL

    @property
    def isput(self):
        return self.right == PUT

    def intrinsic(self, price):
        """Per-unit value if exercised at underlying ``price``."""
        if self.iscall:
            return max(price - self.strike, 0.0)
        return max(self.strike - price, 0.0)

    def years_to_expiry(self, when):
        """Calendar years from ``when`` (a date or datetime) to expiry, at
        least 0. On expiry day it is 0."""
        if isinstance(when, datetime.datetime):
            when = when.date()
        return max((self.expiry - when).days, 0) / 365.0
