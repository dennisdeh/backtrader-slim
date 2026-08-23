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
import ast
import io
import pathlib
import re
import subprocess
import sys

import pytest

import backtrader

import testcommon


class TestFrompackages(testcommon.SampleParamsHolder):
    __test__ = False  # not a pytest class

    """
    This class is used for testing that inheriting from base class that
    uses `frompackages` import mechanism, doesnt brake the functionality
    of the base class.
    """

    def __init__(self):
        super(TestFrompackages, self).__init__()
        # Prepare the lags array


def test_run(main=False):
    """
    Instantiate the TestFrompackages and see that no exception is raised
    Bug Discussion:
    https://community.backtrader.com/topic/2661/frompackages-directive-functionality-seems-to-be-broken-when-using-inheritance
    """
    test = TestFrompackages()


class TestNothingOptionalIsImportedEagerly:
    """`import backtrader` must not drag in a third-party package.

    The engine declares no runtime dependencies, and the optional integrations
    keep that true by importing their package on first use. This has to run in
    a fresh interpreter: by the time the suite gets here, other tests have
    already put numpy, pandas and matplotlib in ``sys.modules``.
    """

    OPTIONAL = ["numpy", "pandas", "statsmodels", "matplotlib", "requests"]

    def imported_after(self, statement):
        code = (
            "import sys\n"
            f"{statement}\n"
            f"print([m for m in {self.OPTIONAL!r} if m in sys.modules])"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=pathlib.Path(__file__).resolve().parent.parent,
        )
        return ast.literal_eval(out.stdout.strip())

    def test_importing_backtrader_pulls_in_nothing_optional(self):
        assert self.imported_after("import backtrader") == []

    def test_importing_the_indicators_pulls_in_nothing_optional(self):
        assert self.imported_after("import backtrader.indicators") == []

    def test_numpy_arrives_only_when_hurst_is_built(self):
        statement = (
            "import backtrader as bt\n"
            "c = bt.Cerebro(stdstats=False)\n"
            "c.adddata(bt.feeds.BacktraderCSVData("
            "dataname='datas/2006-day-001.txt'))\n"
            "class S(bt.Strategy):\n"
            "    def __init__(self):\n"
            "        bt.indicators.HurstExponent(self.data)\n"
            "c.addstrategy(S)\n"
            "c.run()"
        )
        assert self.imported_after(statement) == ["numpy"]


class TestNoNameIsInjectedBehindTheReadersBack:
    """No module under ``backtrader/`` relies on a name it does not contain.

    Two metaclass directives used to put names into a module's globals from
    outside it. ``packages``/``frompackages`` imported a package at
    construction time and ``setattr`` the names into the defining module - and
    into every base class's module besides. ``alias`` builds a subclass per
    alias and ``setattr``\\s that in too.

    Both still work, and ``TestFrompackages`` above still exercises the first,
    but a name a reader cannot find is a name a checker cannot check: pyflakes
    reported 15 undefined names across the modules that referred to their own
    injected names, and so could not have seen a genuine mistake in any of
    them. Where a module names an alias - in code, or in its own ``__all__`` -
    the alias is written out as the subclass the directive would have built.
    """

    def root(self):
        return pathlib.Path(backtrader.__file__).parent

    def test_no_module_declares_packages_or_frompackages(self):
        offenders = []
        for path in sorted(self.root().rglob("*.py")):
            if path.name == "metabase.py":
                continue  # implements the directive rather than using it
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if re.match(r"\s*(from)?packages\s*=", line):
                    offenders.append(f"{path.name}:{number}")
        assert not offenders, "injected imports in:\n  " + "\n  ".join(offenders)

    def test_pyflakes_finds_no_undefined_name_anywhere(self):
        """The whole package, not a sample of it.

        Only ``undefined name`` is asserted on. pyflakes also reports the
        star-import re-exports every ``__init__.py`` is built from, which are
        deliberate - see reports/IMPROVEMENT_SUGGESTIONS.md for the standing
        suggestion to give those modules an ``__all__``.
        """
        pytest.importorskip("pyflakes")
        reporter = pytest.importorskip("pyflakes.reporter")
        api = pytest.importorskip("pyflakes.api")

        out, err = io.StringIO(), io.StringIO()
        for path in sorted(self.root().rglob("*.py")):
            api.checkPath(str(path), reporter.Reporter(out, err))

        undefined = [
            line for line in out.getvalue().splitlines() if "undefined name '" in line
        ]
        assert not undefined, "\n".join(undefined)


if __name__ == "__main__":
    test_run(main=True)
