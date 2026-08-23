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
"""Licensing and attribution invariants for the distributed source.

This exists because the notices were once lost by accident: commit 3359215
rewrote the import lists of three ``__init__.py`` files and took the whole
GPLv3 header block with them, and 2.0.0 shipped to PyPI without upstream's
copyright notice in those files. GPL-3.0 section 4 requires the notices to be
kept intact and section 5(a) requires a modified work to say that it was
modified; neither is something to rediscover by hand.

The checks are deliberately offline and read only the working tree, so they
cost nothing and cannot depend on a git remote.
"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "backtrader"
TESTS = REPO / "tests"

GPL_MARKERS = (
    "GNU General Public License",
    "either version 3 of the License",
)

# Derived from matplotlib 1.2.0 and distributed under John D. Hunter's licence,
# not the GPL. It carries that licence in full instead, so it is checked for a
# different marker rather than exempted outright.
MATPLOTLIB_LICENSED = {PACKAGE / "plot" / "multicursor.py"}

# Byte-identical to upstream, so upstream's header is correct as it stands and
# no modification notice belongs on it.
UNMODIFIED_FROM_UPSTREAM = {PACKAGE / "studies" / "contrib" / "fractal.py"}


def _sources():
    return sorted(PACKAGE.rglob("*.py")) + sorted(TESTS.rglob("*.py"))


def test_every_source_file_carries_a_licence_header():
    """GPL-3.0 section 4: the notices are kept intact on every shipped file."""
    missing = []
    for path in _sources():
        head = path.read_text(encoding="utf-8")[:4000]
        if path in MATPLOTLIB_LICENSED:
            if "LICENSE AGREEMENT FOR MATPLOTLIB" not in head:
                missing.append(str(path.relative_to(REPO)))
            continue
        if any(marker not in head for marker in GPL_MARKERS):
            missing.append(str(path.relative_to(REPO)))
    assert not missing, "lost the GPLv3 notice:\n  " + "\n  ".join(missing)


def test_upstream_copyright_is_never_dropped():
    """Upstream's copyright line stays on every file that came from upstream."""
    missing = []
    for path in _sources():
        head = path.read_text(encoding="utf-8")[:4000]
        if path in MATPLOTLIB_LICENSED:
            # Its owner is John D. Hunter. The notice spells it "Copyright (c)"
            # and wraps across two comment lines, so match the parts.
            if "2002-2011 John D. Hunter" not in head:
                missing.append(str(path.relative_to(REPO)))
            continue
        # A file written by this fork must at least claim its own copyright
        # rather than having no owner at all.
        if "Copyright (C)" not in head:
            missing.append(str(path.relative_to(REPO)))
    assert not missing, "no copyright line:\n  " + "\n  ".join(missing)


def test_modified_files_state_that_they_were_modified():
    """GPL-3.0 5(a): a modified work must say so, and give a date."""
    missing = []
    for path in _sources():
        if path in UNMODIFIED_FROM_UPSTREAM or path in MATPLOTLIB_LICENSED:
            continue
        head = path.read_text(encoding="utf-8")[:4000]
        if "Daniel Rodriguez" not in head:
            continue  # fork-authored, nothing of upstream's to have modified
        if "modified version of backtrader" not in head:
            missing.append(str(path.relative_to(REPO)))
    assert not missing, "no modification notice in:\n  " + "\n  ".join(missing)


def test_licence_text_ships_and_is_gplv3():
    licence = REPO / "LICENSE"
    assert licence.is_file(), "LICENSE is missing from the repository root"
    text = licence.read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text


def test_readme_credits_upstream():
    """The README is what PyPI renders, so attribution has to live there too."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Daniel Rodriguez" in readme
    assert "GNU General Public License" in readme
    assert "mementum/backtrader" in readme
