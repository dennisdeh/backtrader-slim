#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################

# The modules below should/must define __all__ with the objects wishes
# or prepend an "_" (underscore) to private classes/variables
#
# There are no live stores in this fork: the Interactive Brokers, VisualChart
# and Oanda stores were removed in 2.0.0 because they depended on abandoned
# packages (IbPy, comtypes, oandapy). The package is kept so that third-party
# stores can still register themselves against backtrader.stores.
