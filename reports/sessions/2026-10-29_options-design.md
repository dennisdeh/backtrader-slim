# Options on the Cerebro engine: implementation options and a questionnaire

An investigation, not a change: no engine code was modified. It answers two
questions. First, how can options be added as a derivative class that
strategies trade through the existing Cerebro valuation engine? Second, how
can strategies that mix several stocks and their options be built on top of
that? It ends with a questionnaire. The answers to it pick between the options
below.

## Summary

- **The engine already does most of the work.** If every option contract is
  its own data feed, `BackBroker` values it from that feed's `close[0]` every
  bar, keeps a per-contract `Position`, books `Trade`s, runs analyzers, and
  synchronises it with the underlying and with other stocks. Several stocks
  plus options on one clock works today.
- **Five gaps stop a correct options backtest today.** Each one was shown by
  running a script (the numbers below were measured on 2026-10-29):
  1. **The ×100 multiplier is valued wrongly** by every built-in
     commission setup. This is a defect, now filed in `OPEN_ITEMS.md`.
  2. **No expiry, exercise or assignment.** Once a contract's feed ends, its
     position stays open forever, valued at its last price, and a market order
     to close it never fills.
  3. **Selling options needs no margin.** On a 100-dollar account, a naked
     short call is accepted and the account value sinks to -2,700, with no
     margin call.
  4. **Multi-leg orders are not atomic.** Whether a spread is accepted depends
     on the order the legs are sent in. In the failing order, the long leg is
     rejected but the short leg fills, which leaves a naked short.
  5. **No pricing, implied volatility (IV) or greeks** (delta, gamma, vega,
     theta).
- **Recommendation:** option **A2**, an additive `options` layer. It consists
  of a contract feed, a commission class for options, pricing and greeks, and
  a single hook in the broker for settling contracts at expiry. Model-priced
  options (**A3**) come with it as a mode, for runs without option market
  data. For several stocks plus options, add **combo orders** and a
  **pluggable margin model** to the broker (**B2 + B3**). The chain-native
  design (**A4**) is only worth its cost if strategies must scan whole chains
  at scale. Question 7 of the questionnaire decides that.

## 1. How the engine values a position today

This is the code path any option design has to fit, traced through the
source.

- **One instrument is one data feed.** `BackBroker.positions` is keyed by the
  data object, and so are `Strategy._trades` and the commission lookup
  (`BrokerBase.getcommissioninfo(data)`).
- **Valuation is marked to the close.** At the end of every bar,
  `BackBroker.next` calls `_get_value`, and that marks every position at
  `data.close[0]` through the data's `CommInfoBase`:
  `getvaluesize`/`getvalue` give the market value, `profitandloss` gives the
  unrealised P&L, and `cashadjust` gives the futures-style daily cash
  variation.
- **Cash flows are set by the commission object.** `BackBroker._execute` asks
  the comminfo for `getoperationcost`/`getvaluesize` (the cash an opening
  costs or a closing returns), `profitandloss` (the realised P&L, which includes
  `mult`) and `getcommission`.
- **The only margin check is `cash >= 0` after a dry run** of the order
  (`BackBroker.check_submitted`). It processes the submitted orders one at a
  time, carrying the cash forward from one to the next. Nothing re-checks
  margin after a fill, and there are no margin calls.
- **Feeds that start late or end early are handled.** Cerebro's `_runnext`
  advances every feed on one clock. A feed that has ended keeps its last bar,
  so its `close[0]` goes stale but stays valid. A feed that has not started
  yet holds the strategy in `prenext` until it does.
- **Some machinery is already usable for options:**
  - `tradeid`, to keep separate trades on one data feed apart;
  - `Order.Historical`, which fills at a price you supply, on whatever bar the
    feed is on;
  - `data.compensate(other)`, which books an order's trade against another
    data feed;
  - `notify_timer` and `tradingcal`, for expiry dates and holidays;
  - `Sizer`, for position sizing.

### Experiments (2026-10-29)

The runs used system Python 3.13.17 with `PYTHONPATH` pointing at this
checkout. The `backtrader` conda env does not exist in this cloud session.
The feeds were synthetic, built from the in-memory `ListData` feed in the
appendix, and every number below came from actually running the scripts.

**E1: the multiplier.** Buy one contract (×100) at a premium of 2.00 and sell
it at 4.00. The right answer is +200, for a final value of 10,200.

| setup | value while open, bars 2-4 | final value | verdict |
|---|---|---|---|
| A: stock-like, `mult=1`, 100 shares as the size | 10000 / 10100 / 10200 | 10200 | correct, but sizes count shares, not contracts |
| B: stock-like, `mult=100`, size 1 | 10000 / 10001 / 10002 | 10200 | **wrong while open**: only 2.00 cash leaves the account, the mark uses ×1, and the value jumps when the position closes |
| C: futures-like, `margin=50`, `mult=100` | 10000 / 10100 / 10200 | 10200 | value is right, but cash is wrong: it takes the 50 margin instead of the 200 premium, and the daily marks go through cash |
| D: futures-like, `automargin=-1` | 10000 / 10200 / 10400 | 10200 | **double-counts** the change while open |
| E: the 25-line `OptionCommInfo` subclass in the appendix | 9999.35 / 10099.35 / 10199.35 | 10198.70 | **correct**, including $0.65 per-contract commission |

The cause of B is that `CommInfoBase.getoperationcost`, `getvaluesize`,
`getvalue` and `getsize` ignore `mult` on the stock-like branch, while
`profitandloss` applies it. The defect is filed in `OPEN_ITEMS.md`.

**E2: short options without margin.** The account has 100 cash. Sell one call
(×100) at 2.00, and the premium then rises to 30. The order is accepted; cash
goes to 300 and value goes 100 → -700 → -2,700. Nothing objects.

**E3: expiry.** The option feed ends on bar 5 at its intrinsic value of 6.00,
and the underlying feed carries on to bar 8.

| what the strategy does on expiry day | outcome at the end of the run |
|---|---|
| holds | position still open, marked at 6.00 forever |
| `close()`, a market order | the order is **still open at the end** of the run, because no next bar ever comes to fill it |
| `close(exectype=Order.Historical, price=intrinsic)` | settled on the next bar at 6.00, with the position flat |

The last row shows that the engine can already settle an expired contract at
a price it is told. What it lacks is something that issues the settlement
automatically, plus physical delivery and assignment.

**E4: a contract listed late.** Results: `prenext1..3, next4..6`. The
strategy stops calling `next()` until the newest contract has a bar. Any
strategy with rolling contracts must override `prenext` to call `next`.

**E5: a bull call spread on 300 cash.** Long a call at 5 and short a call at
3, for a net debit of 200.

| order the legs are submitted in | result |
|---|---|
| long first | **long leg: Margin (rejected); short leg: Completed.** The strategy is left holding a naked short |
| short first | both legs Completed |

**E6: scale.** One underlying plus N contracts, each listed for 60 of 252
daily bars, with an empty strategy (`e6_scale.py` in the appendix, 4 cores):

| option feeds | 0 | 10 | 100 | 500 | 1000 |
|---|---|---|---|---|---|
| wall time | 0.01 s | 0.02 s | 0.20 s | 1.18 s | 2.37 s |

The cost is linear, at about 2.4 ms per contract-year before any strategy
logic runs. A handful of contracts per underlying is free. One liquid
underlying's full chain (several thousand contracts a year) costs seconds of
overhead per year, and an index-wide universe of full chains does not fit
this design. That threshold separates options A2 and A4.

## 2. Part A: options as a derivative class

### A1: user-land only, with no engine change

Each contract is a CSV or `PandasData` feed of premiums. A user-side
`OptionCommInfo` (appendix) handles the multiplier and per-contract fees. The
strategy settles expiring contracts with an `Order.Historical` close at
intrinsic value and overrides `prenext`.

- **Pros:** works today; nothing to maintain in the fork.
- **Cons:** expiry, exercise and assignment are rewritten in every strategy;
  short options have no margin; there are no greeks; contract metadata
  (strike, expiry, right) lives in the user's head or the feed name.
- **Effort:** S. It is a sample program plus documentation.

### A2: an additive `options` layer (recommended)

New modules, with exactly one hook added to the core:

| piece | what it is | where it plugs in |
|---|---|---|
| `OptionData` | a feed subclass. Params: `underlying` (a data object or name), `strike`, `expiry`, `right` (C/P), `mult`, `style` (EU/US), `settlement` (cash/physical). Extra lines: `bid`, `ask`, `iv` and optional vendor greeks | `cerebro.adddata` as today, and it registers its own `OptionCommInfo` |
| `OptionCommInfo` | premium-style cash flows with `mult` applied everywhere (E1, row E); a per-contract fee with minimum and maximum; exercise and assignment fees; `get_margin` for short options under a pluggable rule | `broker.addcommissioninfo(..., name=)` |
| settlement hook | in `BackBroker.next`, after orders execute and before `_get_value`: for each open position whose data is an `OptionData` past its expiry, settle at intrinsic value from the underlying's close. Cash settlement books cash. Physical settlement books a stock position at the strike. A short position is assigned. Each settlement is an `Order.Historical` fill, so `notify_order`, `notify_trade` and analyzers see it | the one core change, a no-op for non-option feeds |
| pricing | Black-Scholes-Merton and Black-76 in closed form; a CRR binomial tree for American options; an IV solver (Newton's method, falling back to bisection) | pure functions in the stdlib (`math.erf`), to keep the engine at **zero runtime dependencies** |
| greeks as indicators | `OptionPrice`, `ImpliedVol`, `Delta`, `Gamma`, `Vega`, `Theta` over (underlying, option, vol, rate) | indicators with **both `next()` and `once()`**, and golden-value tests in `tests/test_ind_option_*.py` |
| early exercise (American options) | optional: a policy object that the settlement hook also calls every bar (for example, exercise when the remaining extrinsic value is less than an upcoming dividend) | off by default |

- **Pros:** fits every existing piece: Strategy, Position, Trade, analyzers,
  plots and sizers. A strategy calls `self.buy(data=opt, size=2)` and sizes in
  contracts.
- **Cons:** a feed per contract caps chain breadth (E6), and contracts must be
  chosen before `cerebro.run()`, because feeds cannot be added mid-run.
- **Effort:** M.

### A3: model-priced (synthetic) options, as a mode of A2

No option market data is needed. An `OptionData` built with `source="model"`
generates its own premium bars from the underlying feed, using a volatility
input (a realised-vol indicator, a VIX-style feed, or a constant) plus a rate
and dividend yield. Everything downstream is A2 unchanged.

- **Pros:** research without paying for option data; any strike or expiry on
  demand.
- **Cons:** no volatility skew, no bid/ask spread and no liquidity, so results
  are optimistic for short-volatility strategies. It must be labelled as a
  model in every report it produces.
- **Effort:** +S on top of A2.

### A4: chain-native instruments

Here one `OptionChain` feed carries a snapshot of the whole chain on each bar,
and contracts become lightweight instruments that the broker creates when an
order for them arrives.

- **The cost is a redesign.** It breaks the "one instrument = one data feed"
  rule that `BackBroker.positions`, `Strategy._trades`, the commission
  lookup, observers and plotting all key on. Positions would be keyed by a
  contract ID, and the broker would value them from the snapshot.
- **Pros:** scanning a whole chain ("sell the 30-delta put each month") at
  index scale; no pre-selection of contracts.
- **Cons:** the largest change to the core; the per-data analyzers, observers
  and plots need equivalents; memory grows with chain size.
- **Effort:** L.

## 3. Part B: strategies with several stocks and options

### What works today

- **Many stocks on one clock.** `self.datas`, `getdatabyname`,
  `order_target_percent(data=...)` and cross-sectional ranking all work
  (`samples/multidata-strategy`, `samples/multi-example`). Timers handle
  rebalancing, and options are just more datas.
- **Covered call and protective put, as two independent orders.** These
  already run under A1/A2: the stock leg is stock-like and the option leg uses
  `OptionCommInfo`.

### What is missing

| gap | why it matters | evidence |
|---|---|---|
| B-gap 1: **leg atomicity** | a spread can end up half-filled, holding a naked short | E5 |
| B-gap 2: **portfolio margin** | margin is checked per order against cash, so a defined-risk spread or covered call is charged like naked legs, or not at all (E2) | `check_submitted` |
| B-gap 3: **contract ↔ underlying link** | a covered call is "covered" only if the margin model knows which stock the option is on, and physical settlement needs the stock's data feed | none in the engine today |
| B-gap 4: **structure-level reporting** | `Trade` is per data feed (plus `tradeid`), so an iron condor shows up as four unrelated trades | `Strategy._trades` |
| B-gap 5: **sizing** | `Sizer`s size one data feed at a time in units; option strategies size by contracts, notional, delta or max loss | `Sizer.getsizing` |
| B-gap 6: **stale marks** | an illiquid option with no bar keeps its last close (E3) while the underlying moves | `_runnext` |
| B-gap 7: **corporate actions** | splits change the strike and the multiplier; special dividends change deliverables | none |

### Implementation options

- **B1: strategy-level helpers, no core change.** A `Combo` helper sends the
  legs in a cash-safe order (credit legs first, which is E5's working order),
  watches `notify_order`, and flattens the filled legs if any leg comes back
  `Margin`. Closing those filled legs costs a bar of exposure and, in a live
  market, would cost slippage. Effort: S.
- **B2: combo orders in the broker.** `broker.submit_combo(legs)` runs a dry
  run of all legs together in `check_submitted`: accept all or reject all.
  `_try_exec` fills them **all on the same bar or none** (every leg's feed
  must have a bar), and a net-price limit is optional. The legs share one
  `tradeid` and one combo reference, which also closes B-gap 4. Effort: M,
  confined to `bbroker.py`.
- **B3: a pluggable margin model.** `broker.set_margin_model(m)`, called (a)
  from `check_submitted` against the projected positions and (b) at the end
  of `BackBroker.next` as a maintenance check, which either notifies the
  strategy or forces liquidation. Three models:
  - `CashOnly`: today's behaviour, and the default, so nothing changes for
    existing users.
  - `StrategyBased`: Reg-T-style rules that recognise covered calls,
    cash-secured puts, verticals and condors (B-gap 3 supplies the
    underlying link).
  - `RiskBased`: a scenario grid (underlying ±x%, IV ±y) priced by A2's
    pricing module, close to how portfolio margin works.

  Effort: M for the hook plus `CashOnly`/`StrategyBased`; +M for `RiskBased`.
- **B4: a structure as one synthetic instrument.** One feed carries the net
  price of a fixed structure (for example, a constant 30-DTE iron condor),
  traded as a single instrument. It is the cheapest route to research results,
  but it has no per-leg accounting, assignment or margin realism. Effort: S,
  built on top of A3.
- **Analytics, whichever of the above is chosen.**
  - A `PortfolioGreeks` observer: sum of delta, gamma, vega and theta across
    positions, per underlying and in total.
  - A `StructureTrades` analyzer: P&L per combo, maximum adverse excursion
    while the structure was open, and days held.
  - A sizer that sizes by contracts, delta or max loss, to close B-gap 5.

### Recommended phasing

1. **Fix the stock-like multiplier defect** (`OPEN_ITEMS.md`), with a
   regression test that is shown failing first. This decision comes first:
   question 17.
2. **A2 core:** `OptionData`, `OptionCommInfo`, the settlement hook, pricing
   and greeks, with tests anchored to textbook values (Hull's example: S=42,
   K=40, r=10%, σ=20%, T=0.5 gives a call of 4.76 and a put of 0.81), checked
   by hand before they become golden values.
3. **A3 model mode**, plus one sample per strategy family: a covered call, a
   cash-secured put, and a vertical spread.
4. **B2 combo orders and B3 margin hook** with `CashOnly` and
   `StrategyBased`, plus the `PortfolioGreeks` observer and the
   `StructureTrades` analyzer.
5. **Only if question 7 asks for it:** `RiskBased` margin, then A4.

Every phase records its API additions and breaks in `changelog.txt` in the same
commit and ships tests in the existing style. None of them adds a runtime
dependency (the stdlib `math` module is enough for closed-form pricing).

## 4. Questionnaire

Pick one answer per question unless it says otherwise. **(R)** marks the
recommended default where one exists. Numbers in brackets point to the
section the answer decides.

**Purpose and instruments**

1. What is this for?
   (a) research backtests only **(R)**; (b) research now, live trading later;
   (c) something else. Note that this fork removed every live integration in
   2.0.0.
2. Which underlyings? (choose all that apply)
   (a) US single stocks and ETFs; (b) cash-settled indices (SPX, NDX); (c)
   futures options; (d) FX or crypto; (e) other.
3. Exercise style. (a) European only; (b) American, assignment at expiry only
   **(R)** to start; (c) American with early exercise and assignment
   modelled (A2, early exercise).
4. Settlement. (a) cash; (b) physical, into the underlying stock; (c) both,
   per contract **(R)**.

**Data**

5. Do you have option market data? If yes: vendor and format (for example
   ORATS, CBOE DataShop, OptionMetrics, Polygon, IVolatility, your own CSV),
   frequency (end-of-day or intraday), and whether it carries bid/ask, IV and
   greeks.
6. Without market data, is model pricing acceptable (A3)? If yes, which
   volatility input: (a) realised volatility of the underlying; (b) a VIX-style
   index; (c) an IV surface file; (d) a constant.
7. How wide a chain does a strategy look at on each bar? (a) a few chosen
   contracts per underlying (A2 is enough) **(R)**; (b) the full chain of a
   few underlyings (A2 at the edge of its scale, E6); (c) full chains across
   many underlyings (A4).
8. Fill price. (a) mid; (b) cross the spread (buy at the ask, sell at the bid);
   (c) mid ± a configurable fraction of the spread **(R)**; (d) the bar's
   open or close, as for stocks today.

**Strategies**

9. Which strategies first? (choose all that apply) Covered call · cash-secured
   put / wheel · protective put / collar · vertical spreads · iron condor /
   butterfly · straddle / strangle · calendar / diagonal · delta-hedged
   volatility trades · ratio spreads · other.
10. Delta hedging with the underlying? (a) no; (b) yes, on a schedule (daily or
    weekly); (c) yes, when delta crosses a threshold.
11. How many underlyings at once? (a) up to 10 **(R)**; (b) up to 100; (c) an
    index universe of about 500.
12. Is the options book an overlay on a stock portfolio that rebalances on
    its own schedule (for example, covered calls written on a momentum
    portfolio)? (a) yes; (b) no, options-only.

**Risk and accounting**

13. Margin model (B3). (a) cash-only, every short fully collateralised;
    (b) strategy-based Reg-T rules **(R)**; (c) risk-based or portfolio margin;
    (d) none, as today.
14. When margin is breached: (a) notify the strategy only **(R)**; (b) forced
    liquidation by the broker.
15. Commissions. Per-contract fee, minimum and maximum per order, and
    exercise and assignment fees? Please give your broker's schedule if you
    want it matched.
16. Should cash earn interest, and should stocks pay dividends? Both affect
    put-call parity and early exercise.

**Engine and API**

17. The stock-like `mult` defect: (a) fix it in `CommInfoBase` (an API
    break, recorded in the changelog; no current test or sample depends on
    the broken behaviour) **(R)**; (b) leave the core alone and contain the
    fix in `OptionCommInfo`.
18. Core changes. (a) accept the A2 settlement hook and the B2/B3 broker
    changes in `BackBroker` **(R)**; (b) keep them in an `OptionBroker`
    subclass instead; (c) user-land only (A1/B1).
19. Analytics wanted? (choose all that apply) Greeks per position · portfolio
    greeks observer · per-structure P&L analyzer · P&L attribution
    (delta/gamma/vega/theta) · plots of greeks over time.
20. Dependencies. (a) stdlib only, keeping the engine dependency-free **(R)**;
    (b) numpy/scipy allowed behind a new optional `options` extra.
21. Is there a performance target? For example, "10 years × 50 underlyings ×
    the options on them, in under N minutes".
22. Corporate actions (splits adjusting strike and multiplier): (a) out of
    scope for now **(R)**; (b) needed.
23. Which phase from §3 should start first, and is there a deadline?

## 5. Answers (2026-10-29)

The questionnaire was answered in the session chat on 2026-10-29.

| # | answer |
|---|---|
| 1 | research backtests only |
| 2 | US stocks & ETFs, cash-settled indices, futures options, FX/crypto |
| 3 | American, assignment at expiry only |
| 4 | both settlement types, declared per contract |
| 5 | has end-of-day option data with bid/ask |
| 6 | model mode uses the underlying's realised volatility |
| 7 | **full chains across many underlyings** |
| 8 | mid ± a configurable fraction of the spread |
| 9 | all ten strategy families |
| 10 | delta hedging with the underlying, triggered by a threshold |
| 11 | **index-wide, about 500 underlyings** |
| 12 | options as an overlay on a stock portfolio |
| 13 | **cash-only margin** |
| 14 | a margin breach notifies the strategy only |
| 15 | per-contract fees plus exercise and assignment fees |
| 16 | interest on cash and dividends on stock |
| 17 | fix the `mult` defect in `CommInfoBase`, as a recorded API break |
| 18 | broker changes go into `BackBroker` |
| 19 | all four: per-position greeks, a portfolio greeks observer, per-structure P&L, P&L attribution |
| 20 | numpy/scipy allowed behind an optional `options` extra |
| 21 | **10 years × 500 underlyings in under 30 minutes** |
| 22 | corporate actions out of scope for now |
| 23 | start with the `mult` fix plus the A2 core |

### What the answers imply

- **A4 is required, not optional.** Answers 7, 11 and 21 together rule out a
  data feed per contract as the end state. Here is an estimate built from
  E6's ~2.4 ms per feed for a 252-bar year. Assume about 3,000 contracts
  listed per underlying per year. Then 500 underlyings × 10 years is about
  15 million feeds, and the feed overhead alone, before any strategy logic,
  comes to roughly 10 hours, against a 30-minute target. The 3,000 is an
  assumption, not a measurement, and should be checked against the vendor
  data.
- **Starting with the `mult` fix and the A2 core (answer 23) is still
  right**, as long as the pieces are written to carry over to A4: the
  commission class, the settlement logic, the fee model, and pricing,
  greeks and IV written as pure functions that A4's chain snapshots can call
  vectorised (answer 20). The per-contract `OptionData` feed is the one A2
  piece A4 replaces.
- **Cash-only margin (13) conflicts with part of the strategy list (9).**
  Under cash-only, a short call has to be covered by stock and a short put by
  cash. A naked short call has unlimited risk, so no amount of cash covers
  it, and the broker would reject it. Short straddles and strangles, ratio
  spreads, and delta-hedged short volatility all rely on naked or partly
  covered short calls. One of these needs choosing: (a) reject them under
  cash-only as specified; (b) add `StrategyBased` margin before those
  strategies are built; (c) a cash-only variant that counts a short call as
  covered by stock held anywhere in the overlay (12), or by a long call in
  the same structure. **Undecided.**
- **American options exercised only at expiry (3), combined with dividends
  (16), makes covered calls optimistic.** In-the-money short calls are often
  assigned early, just before the stock goes ex-dividend, and this model
  never assigns them early. Record that as a known bias in any
  covered-call result until early exercise is added.
- **Multi-leg orders (B2) are needed early.** Ten strategy families (9),
  threshold-triggered delta hedging (10) and per-structure P&L (19) all assume
  that legs fill together and are reported as one structure.

## Appendix: reproduction

The experiment scripts lived in the session scratchpad. Their essentials are
below; E1-E7 were 10-40 lines each on top of these.

```python
# The in-memory feed every experiment used
class ListData(bt.feed.DataBase):
    params = (("rows", None),)          # [(date, o, h, l, c), ...]
    def start(self):
        super().start(); self._it = iter(self.p.rows)
    def _load(self):
        try: d, o, h, l, c = next(self._it)
        except StopIteration: return False
        self.lines.datetime[0] = bt.date2num(dt.datetime.combine(d, dt.time()))
        self.lines.open[0], self.lines.high[0] = o, h
        self.lines.low[0], self.lines.close[0] = l, c
        return True
```

```python
# E1 row E: premium accounting with the multiplier applied everywhere
class OptionCommInfo(bt.CommInfoBase):
    params = (("stocklike", True), ("commtype", bt.CommInfoBase.COMM_FIXED),
              ("mult", 100), ("commission", 0.65))   # $ per contract
    def getsize(self, price, cash):       return int(cash // (price * self.p.mult))
    def getoperationcost(self, size, price): return abs(size) * price * self.p.mult
    def getvaluesize(self, size, price):  return size * price * self.p.mult
    def getvalue(self, position, price):  return position.size * price * self.p.mult
    def cashadjust(self, size, price, newprice): return 0.0
```

```python
# E3: settling an expired contract with existing machinery
intrinsic = max(self.data0.close[0] - strike, 0.0)
self.close(data=opt, exectype=bt.Order.Historical, price=intrinsic)
```

E6 timing command: `PYTHONPATH=. python3 e6_scale.py 0 10 100 500 1000`, with
one 252-bar underlying and N feeds, each listed for 60 bars at a random
start (`random.seed(1)`), and a strategy whose `prenext` calls an empty
`next`.
