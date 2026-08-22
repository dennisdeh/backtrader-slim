# Improvement suggestions

The code is correct here; it could be better. Nothing in this file is a defect
— those live in `OPEN_ITEMS.md`.

*Last updated: 2026-08-22*

### Give the star-exporting modules an `__all__`

Nearly every module is re-exported with `from .module import *` and has no
`__all__`, so imported names leak into the public namespace. Until this
session `bt.feeds.ProxyHandler` and `bt.feeds.urlopen` existed for that reason
alone. An explicit `__all__` per module would make the public surface
intentional and let static analysis work.

### The golden-value tests cannot say which run mode failed

`testcommon.runtest` loops over `runonce × preload × exactbars` inside one test
function, so a failure reports the assertion but not the combination that
produced it. Parametrising at the pytest level would name the failing mode in
the test id. It touches all 70 indicator tests, so it was not done here.

### Coverage is thin in three places that matter

After this session (73% of statements, 69% counting branches):

| module | coverage | what is missing |
|---|---|---|
| `resamplerfilter.py` | 42% | the boundary logic for weekly/monthly/yearly rollover |
| `brokers/bbroker.py` | 57% | margin calls, interest accrual, futures-style cash adjustment |
| `strategy.py` | 61% | the notification paths and multi-data bookkeeping |

### `talib.py` is untested

3% covered, because TA-Lib is not installed in the dev environment. The tests
would need `pytest.importorskip("talib")` and a CI job that installs the C
library.

### The samples are unverified

68 sample programs, none executed by anything. Several referenced feeds that
were removed years before this session. A smoke test that imports each one (or
runs it against tracked data) would keep them honest.

### `setup.py`-era metadata is gone but `contrib/` was not reviewed

`contrib/` holds a pair-trading sample and two data files. It was left alone
beyond deleting the InfluxDB import scripts; it deserves the same pass the rest
of the tree got.
