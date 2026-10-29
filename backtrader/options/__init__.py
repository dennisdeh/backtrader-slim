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
"""Options: contracts, feeds, commission, pricing and greeks.

A contract trades through the ordinary engine: its feed is a data feed of
premiums, the broker values it at ``close * multiplier``, and at expiry the
broker settles it against the underlying's close - in cash, or by
delivering the underlying. See ``cerebro.addoption``.
"""

from . import pricing as pricing
from .comminfo import *
from .contract import *
from .feeds import *
from .indicators import *
from .model import *
from .margin import *
from .analysis import *
from .pricing import CALL, PUT
