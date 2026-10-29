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
"""The commission and valuation scheme for option contracts."""

from ..comminfo import CommInfoBase

__all__ = ["OptionCommInfo"]


class OptionCommInfo(CommInfoBase):
    """Premium-style accounting for options, charged per contract.

    The buyer pays ``premium * mult`` per contract and the seller receives
    it; the position is marked at the option's close times ``mult``.

    Params:

      - ``mult`` (def: ``100``): units of the underlying per contract.
        ``cerebro.addoption`` sets it from the contract.
      - ``commission`` (def: ``0.0``): per contract, per execution.
      - ``min_commission`` (def: ``0.0``): the least an execution costs.
      - ``max_commission`` (def: ``None``): the most an execution costs.
      - ``exercise_fee`` (def: ``0.0``): per contract exercised or assigned
        at expiry. A contract expiring worthless is free.
    """

    params = (
        ("stocklike", True),
        ("commtype", CommInfoBase.COMM_FIXED),
        ("mult", 100.0),
        ("min_commission", 0.0),
        ("max_commission", None),
        ("exercise_fee", 0.0),
    )

    def _getcommission(self, size, price, pseudoexec):
        if not size:
            return 0.0
        comm = max(abs(size) * self.p.commission, self.p.min_commission)
        if self.p.max_commission is not None:
            comm = min(comm, self.p.max_commission)
        return comm

    def getsettlementcommission(self, size, kind):
        if kind in ("exercise", "assignment"):
            return abs(size) * self.p.exercise_fee
        return 0.0
