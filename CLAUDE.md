# CLAUDE.md — Slim Backtrader

*How to work in this repository. What the code *is*, read the code for. What is
here is what the code cannot tell you: which command to trust, what "done"
means, and which plausible-looking action is the wrong one.*

Items marked **(pending)** describe agreed plans that have not landed yet. When
one lands, delete the marker and the "as of" state around it.

---

## Project overview  **[core]**

A slimmed fork of [mementum/backtrader](https://github.com/mementum/backtrader):
a self-contained Python backtesting and live-trading library. It produces an
importable `backtrader` package plus a `btrun` console script — there is no app
and no service. Consumers are your own strategy code and anyone using the fork.

The project's purpose is *subtraction*: remove dead integrations, modernize aged
Python, speed up the core. A change is **done** when the full test suite is green,
the change advances one of those three goals, and any API break is recorded.

- **Primary language / runtime:** Python **3.13** (floor — see *Environment*)
- **Entry point:** there is none for the library. The command that exercises the
  whole thing is `cd tests && python -m pytest -q`.
- **Central concept:** **lines objects built by metaclasses.** Every Indicator,
  Strategy, Data feed and Analyzer is a `LineSeries` whose class-level `lines`,
  `params`, `alias` and `plotinfo` declarations are turned into real machinery at
  class-creation time by `metabase.MetaParams` and `lineseries.MetaLineSeries`.
  Read `backtrader/metabase.py` and `backtrader/lineseries.py` before touching
  anything in the core; almost every surprising behaviour originates there.

## Environment  **[core]**

```bash
conda activate backtrader
```

- Environment definition: `environment.yml` at the repo root. Create the env with
  `conda env create -f environment.yml`. The personal env
  `/home/deh/miniforge3/envs/inv313` also carries an editable install of this
  repo — it is *not* the project env; do not run the suite there or document it.
- Install the package itself editable from the repo root: `pip install -e .`
  (the README currently says `pip install -e`, missing the dot — fix it when you
  next touch the README).
- **Python 3.13 is the floor.** Do not write code that must also run on an older
  interpreter, and delete compatibility shims on sight rather than preserving them.
- A fresh clone needs exactly two things: the conda env, and `pip install -e .`.
  Test fixtures live in `datas/` and are tracked, so the suite needs **no
  network, no credentials, no services and no secrets**. If a change introduces a
  requirement for any of those, that is a design problem in this project, not a
  setup step to document.
- `.idea/` is gitignored, says "Python 3.12", and is stale. Ignore it.

## Key conventions  **[core]**

The non-obvious ones — where a reasonable reader guesses wrong:

- `lines = ('sma',)`, `params = (...)` and `alias = ('SMA', ...)` are **class-level
  declarations consumed by metaclasses**, not plain attributes. Adding, renaming or
  reordering one changes the generated class. Read params as `self.p.<name>`, lines
  as `self.lines.<name>` / `self.l.<name>`, values as `self[0]`.
- **Aliases are public API.** `bt.indicators.SMA`, `SimpleMovingAverage` and
  `MovingAverageSimple` are one class registered under several names, and
  `mabase.MovingAverage` auto-registers every moving average into the `MovAv`
  namespace. Renaming a class silently removes names from `bt.indicators` without
  any import error at definition time.
- **Every indicator has two execution paths:** `next()` (bar-by-bar) and `once()`
  (vectorized, used when `runonce=True`). Fixing one and not the other passes half
  the matrix — `testcommon.runtest` runs every case across
  `runonce ∈ {True, False} × preload ∈ {True, False} × exactbars ∈ {-2, -1, False}`,
  so a one-sided fix surfaces as a mismatch in *some* combination, not all.
- **Indexing is relative to now**, not list semantics: `data.close[0]` is the
  current bar, `[-1]` the previous one.
- **`minperiod` is computed by the framework, not declared**, and the tests assert
  it (`chkmin`). If it moves, the change altered when the indicator becomes valid.
- **`cerebro.plot()` deliberately shows nothing.** `plotter.show()` is commented
  out and the matplotlib backend is forced to `Agg` (`MacOSX` on darwin) — see
  `backtrader/plot/__init__.py`. A plot call that returns without a window is the
  intended non-interactive behaviour, not a bug to fix.
- **The GPLv3 header block at the top of every file stays.** This is a GPL fork:
  keep upstream's copyright line and add to it — never replace or drop it, not
  even during a mechanical sweep.

---

## Scope: what a session may do without asking  **[core]**

Standing authorization, matching the README's stated aims:

- **Mechanical modernization.** Delete `from __future__` imports (169 files as of
  2026-08-22), py2 shims and `utils.py3` usage (61 files), fix deprecated stdlib
  calls (`datetime.utcnow`, invalid escape sequences), modernize syntax to 3.13.
- **Delete dead integrations.** Interactive Brokers, VisualChart and Oanda
  stores/brokers/feeds, the pyfolio analyzer, blaze and quandl feeds. A removal is
  finished only when **nothing in the tree references it** — including
  `__init__.py` exports, `btrun`, `samples/` and the README. Grep the whole tree.
- **Refactor internals** of the metaclass core and indicator bases for clarity or
  speed.

And what bounds it:

- **The public API may break freely** — that is the point of the fork — but every
  break is recorded in `changelog.txt` **in the same commit**. No deprecation shims.
- **One concern per branch.** A modernization sweep and a behaviour change never
  share a commit; a reviewer cannot see the second inside the diff of the first.
- **A performance claim needs a measurement**: the number, the command that
  produced it, and the date. "Faster" without numbers does not go in the changelog.

## Git workflow  **[core]**

- Feature work happens on a **branch in the main checkout**: `git checkout -b <name>`.
  No worktrees.
- Commit when asked. **Never push, never merge into `master`, never delete a
  branch** without an explicit instruction. The full commit→push→merge flow is
  *not* the default here.
- The remote is `origin` = `git@github.com:dennisdeh/backtrader.git` (SSH).
  Run `git remote -v` before diagnosing any push/fetch failure.
- **There is no PR workflow and no `gh` usage in this repository.** Reaching for
  `gh` wastes a turn.
- Upstream (`mementum/backtrader`) is not configured as a remote. Add one only if
  asked.
- Read `git status` before staging; never `git add -A` from the repo root blind.

## Testing  **[core]**

- `cd tests && python -m pytest -q` — **in the foreground, with a bounded
  timeout.** Do not background the runner or spawn polling loops.
- **82 tests, ~55 s** (2026-08-22, Python 3.13). **Report exact pass/fail counts.**
  "Tests pass" without numbers is not a report.
- The suite is offline and credential-free, and must stay that way.
- If you narrow a run to one module, **say so explicitly** — a silently narrowed
  run reads as a full one.
- **The indicator tests are golden-value regressions.** `chkvals` holds formatted
  values at three points (latest, first valid bar, midpoint) plus `chkmin`.
  Changing a golden value changes what the library computes. Never adjust one to
  make a test green: either the change was intended — then say so in the commit
  message and the changelog — or you have found a bug.
- **Every fix ships a regression test demonstrated to FAIL against the unfixed
  code.** Stash the fix, run the test, paste the red output. A test written after
  the fix and never seen red proves nothing.
- A new indicator or feature needs a test in the existing style
  (`tests/test_ind_<name>.py`). Running `python test_ind_<name>.py` directly prints
  the expected block via `main=True` — but **that generator blesses whatever the
  implementation currently does**. Verify the values against the formula by hand
  before pasting them in.
- **Root-cause discipline:** when correcting an expectation or a literal, grep the
  *whole* tree for the same value before declaring it fixed — sibling test files
  duplicate expectations (`rg -n "<value>" tests/`).
- `.travis.yml` is dead (Python 3.6–3.8, `nosetests`) and **no CI runs anywhere**.
  Do not trust it, and do not "fix" it unless asked.
- Known noise, not failure: the suite emits ~740k warnings, dominated by
  `datetime.utcnow()` deprecation in `cerebro.py` and invalid escape sequences in
  docstrings. Reducing them is welcome work; their presence is not a red run.

## Debugging  **[core]**

- **State the root cause with evidence — a log, a reproducing command, or a
  failing test — before editing code.** A patch without a stated cause is a guess
  with a diff attached.
- **Check `samples/` before writing a reproduction.** 68 sample programs exercise
  most code paths; a bug reported against strategy code usually already has one.
- **A scoped grep answers a scoped question.** "Who references this?" is a
  whole-tree question — `samples/`, `contrib/`, `tools/` and the README included.
- Do not treat a prior session's "already fixed" list as an exclusion list. It is
  a point-in-time record, stale by construction. Judge every path on today's source.

## Formatting  **[core]**

- **Black (88 columns) is the formatter**, configured in `pyproject.toml`
  (`target-version = py313`). The one-off sweep across `backtrader/` landed on
  2026-08-22 (167 files); **there should never be a second wholesale reformat.**
- From here, run Black on the files a task modifies — not on the tree.
- `samples/`, `contrib/` and `tools/` are excluded on purpose: they are upstream
  material being pruned, and reformatting them would bury the removals in noise.
  `tests/` is not excluded but was not swept; it converges file by file.

## Versioning and release  **[core]**

- **The next release is `2.0.0`, plain semver.** Upstream's `X.Y.Z.I` scheme —
  where `I` counted the built-in indicators — is **retired**; the fourth digit is
  gone, and `__btversion__` in `backtrader/version.py` is a 3-tuple, derived from
  `__version__` — bumping the string is the whole change.
- Bump the version **only when asked**.
- **Never run `pypi.sh`, `setup.py bdist_wheel` for release, or `twine upload`.**
  Publishing is not an agent action.
- `changelog.txt` is the change record: append notable changes, and always
  API breaks.

---

## Documentation  **[core]**

Three files at the repo root, plus `changelog.txt`. There is deliberately **no
`reports/` tree, no per-module `docs/`, and no docs-check gate** — this is a
library, and the code plus the changelog carry most of the record.

| the fact | the file |
|---|---|
| the code does something other than what it should | `OPEN_ITEMS.md` |
| the code is correct and could be better | `IMPROVEMENT_SUGGESTIONS.md` |
| examined, found correct, not to be re-raised | `DECISIONS.md` |
| what changed, and every API break | `changelog.txt` |

**(pending — the three `.md` files do not exist yet; create one the first time
there is something to put in it, not before.)**

- `OPEN_ITEMS` vs `IMPROVEMENT_SUGGESTIONS` is *"is something wrong?"*, not *"is
  something worth doing?"*. A finding that turns out to be by design moves to
  `DECISIONS.md` **with its reasoning**, so the next session does not reopen it.
- **End a session by filing what is left.** A summary in the chat is not filing.
- **Update the existing file; do not create a parallel one.** State a fact once.
- **Anchor to symbol names, never line numbers** — in code comments too. Every
  `file.py:NNN` in a real repository was stale when audited.
- **Date every measurement.** "measured 2026-08-22: 82 tests, 54.5 s" stays
  checkable; a bare number does not.
- **Never write branch or merge state as present tense.** Give the date instead.
- Search these files before starting an investigation from scratch — then check
  their vintage before trusting them.

### Where prose lives: docs, not code comments

**A code comment says *what* and points; the `.md` files say *why*, with the
evidence.** Measurements, dated incidents, upstream contracts and the reasoning
behind a constant belong in the docs.

- **Keep in the code:** what the value is, the one-sentence trap, the pointer.
- **Move to docs:** the measurement and its date, the incident, what it cost.
- **Never delete a comment that records a defect or a measurement** — relocating
  is the only acceptable way to shorten it. A fact with no home is a regression
  waiting to be re-introduced.
- **Do not number steps** (`# 0.1: ...`) — the numbers drift. **Do not restate the
  next line.** Note that this codebase inherits upstream's habit of long
  explanatory docstrings; leave them where they are correct.

## Housekeeping  **[situational]**

The root was cleaned on 2026-08-22. `optbinning/` (a separate project, 276
unversioned files), `create_coolercontrol_udev_rules.sh` and two root-owned
`.csm_setup_*` files were **moved**, not deleted, to
`../_moved_out_of_backtrader/`; the stale `build/` tree was deleted outright as
regenerable output.

**Keep the root clean.** Unrelated material does not live in this repository. If
something unexplained appears there, move it out and say so — do not delete
unversioned files, and do not `git add -A` from the root without reading
`git status` first.

---

## Rules vs. checks — how to grow this file

In order of value:

1. **A mechanical check** — a lint rule, a pre-commit hook, a test. Every check
   should exist because a defect got through.
2. **A rule in this file**, when a check is impossible or not yet worth writing.
3. **Nothing.** A rule nobody follows is worse than no rule: it trains the reader
   that this file is decoration.

**Keep this file about *how to work here*, not *what the code is*.** Anything an
agent can learn by reading the code belongs in the code.

**Prune as well as add.** Delete a rule when its check exists, when the subsystem
it guards is gone, or when it has never once been the thing that went wrong.
