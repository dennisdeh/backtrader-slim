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
"""Shared fixtures and paths for the backtrader test suite.

`backtrader` is imported as an installed package (``pip install -e .``); no
sys.path manipulation happens anywhere in the suite. Data files are addressed
through :data:`DATAS_PATH` so tests can be run from any working directory.
"""

import datetime
from pathlib import Path

import pytest

import backtrader as bt

DATAS_PATH = Path(__file__).resolve().parent.parent / "datas"

FROMDATE = datetime.datetime(2006, 1, 1)
TODATE = datetime.datetime(2006, 12, 31)


def datafile(name):
    """Absolute path of a tracked data file, checked to exist."""
    path = DATAS_PATH / name
    if not path.exists():
        raise FileNotFoundError(f"missing test data file: {path}")
    return str(path)


def csvdata(name="2006-day-001.txt", fromdate=FROMDATE, todate=TODATE, **kwargs):
    """A BacktraderCSVData feed over one of the tracked data files."""
    return bt.feeds.BacktraderCSVData(
        dataname=datafile(name), fromdate=fromdate, todate=todate, **kwargs
    )


@pytest.fixture
def datas_path():
    return DATAS_PATH


@pytest.fixture
def daily_data():
    """One year of daily bars (2006, 255 sessions)."""
    return csvdata("2006-day-001.txt")


@pytest.fixture
def weekly_data():
    """The same year resampled to weekly bars by the data provider."""
    return csvdata("2006-week-001.txt")


@pytest.fixture
def cerebro():
    """A Cerebro with the standard observers off, so tests see only their own."""
    return bt.Cerebro(stdstats=False)


@pytest.fixture
def cerebro_with_data(cerebro, daily_data):
    cerebro.adddata(daily_data)
    return cerebro
