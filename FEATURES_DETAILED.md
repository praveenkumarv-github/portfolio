# Detailed Feature Documentation

Reviewed against the working tree on **2026-10-31**. Source and regression tests
remain authoritative. Amounts in examples are INR. See
[DOCUMENTATION_UPDATES_SUMMARY.md](DOCUMENTATION_UPDATES_SUMMARY.md) for dated
verification, not a coverage guarantee.

---

## Part 1: XIRR (Internal Rate of Return) Solver

### Purpose

Calculate the annualized return (XIRR) from a portfolio of cash flows with irregular dates. This is essential for quantifying SIP returns on mutual funds and comparing against benchmarks.

### Implementation: `dashboard/services/xirr.py`

**Entry Point:**
```python
def xirr(cashflows, guess=0.1): ...
```

**Input:**
- List of tuples: `[(date_object, amount), ...]`
- Amounts: negative = outflow (investment), positive = inflow (redemption/current value)
- Input is sorted by date internally.
- At least two cashflows, both signs, and two distinct dates are required.

**Output:**
- Decimal annualized rate (0.10 = 10%); negative rates and rates above 100% are possible.
- None for invalid, non-finite, same-date-only, or unsolvable inputs.

### Algorithm

**Step 1: Newton-Raphson Method**
Finds the rate `r` where Net Present Value (NPV) = 0:

```
NPV(r) = Σ[ amount / (1 + r)^(days_since_first / 365) ] = 0
```

- Start with initial guess: r = 0.1 (10%)
- Iterate: r_new = r - NPV(r) / NPV'(r)
- At most 100 iterations; a rate-step change below 1e-9 ends iteration.
- Non-finite intermediates and arithmetic failures trigger fallback or no rate.

**Step 2: Bisection Fallback**
If Newton-Raphson doesn't converge:
- Use bisection search: r in [-0.999, 10.0] (-99.9% to +1000%).
- Finds a root by halving intervals where NPV changes sign
- At most 200 iterations; NPV tolerance is 1e-6.

**Step 3: Return Validation**
- Accept a Newton result when absolute NPV is below 1e-3; otherwise try bisection.
- Bisection returns None when the endpoints do not bracket a root, or its last
    midpoint after the iteration limit. Multiple roots are not enumerated.

### Example

```python
from datetime import date
from dashboard.services.xirr import xirr

# SIP example: 3 months of 10,000 investments, current value 33,500
cashflows = [
    (date(2025, 1, 1), -10000),
    (date(2025, 2, 1), -10000),
    (date(2025, 3, 1), -10000),
    (date(2025, 4, 1), 33500),  # Current value
]
annual_return = xirr(cashflows)
```

### Edge Cases

| Case | Behavior |
|------|----------|
| All outflows | Returns None (no positive cashflow) |
| All inflows | Returns None (no outflows to balance) |
| Single cashflow | Returns None (need at least 2) |
| Zero return (invested = current) | Returns 0.0 |
| High volatility (oscillating NAV) | Bisection fallback may be needed |
| Extreme returns (>100% annual) | Handles via wide bisection range |
| Same-day offsetting flows | Returns None; no elapsed annualization period |
| Non-finite amounts or invalid guess | Returns None |
| Arithmetic overflow/division failure | Returns None if fallback cannot solve |

### Testing

Tests in [tests/test_xirr.py](tests/test_xirr.py) cover one-year returns, SIPs,
losses, insufficient/same-sign flows, unordered input, same-date flows,
non-finite amounts, invalid guesses, and extreme date ranges.

**Run tests:**
```bash
pytest tests/test_xirr.py -v
```

---

## Part 2: Transaction Analytics

### Purpose

Track SIP and lump-sum investments per mutual fund to compute:
- Invested amount (net of redemptions)
- Absolute gain (current value − invested)
- Return % (gain / invested)
- XIRR (annualized return)
- First investment date
- Transaction list (for UI disclosure)

### Data Source: MFTransactions Sheet

**Preferred columns:**
- `Scheme Name`: matches `MutualFunds.FundName`, ignoring case/repeated whitespace.
- `Date`: actual transaction date; supported text formats are listed below.
- `Transaction Type`: PURCHASE/REDEEM or Invested/Redeemed, normalized internally.
- `Units`: Units bought/sold (float, positive)
- `NAV`: NAV on transaction date (float, positive)

**Optional column:**
- `Amount`: If omitted, auto-computed as `Units × NAV`

Legacy `FundIdentifier` plus `Type` columns remain supported. Unmatched or
ambiguous scheme names are skipped with a warning, not guessed.

### Parsing: `dashboard/services/excel_parser.py`

**Function:**
```python
def _parse_mf_transactions(self): ...
```

**Returns:**
```python
[
    {
        'identifier': '120716',
        'date': datetime.date(2025, 1, 1),
        'type': 'Invested',
        'units': 100.5,
        'nav': 150.25,
        'amount': 15100.125,
    },
]
```

**Validation:**
- Native Excel dates and text formats `%d %b %Y`, `%d %B %Y`, `%Y-%m-%d`,
    `%d-%m-%Y`, `%d/%m/%Y`, `%d-%b-%Y` are supported. Invalid dates are skipped;
    future dates are not automatically filtered.
- Type must be Invested/Redeemed (unknown types skipped with warning)
- Numeric text supports commas and rupee symbols. Units/NAV must be positive;
    Amount must be non-negative; all three must be finite. Invalid rows are skipped.
- If the sheet is absent, returns an empty list (backward compatible).
- Parsed portfolio numbers and the computed total must be finite; invalid values
    are rejected before snapshots and chart serialization.

### Calculation Engine: `dashboard/services/calculation_engine.py`

#### Function 1: Per-Fund Analytics

```python
def _fund_transaction_analytics(
    identifier: str,
    txns: list[dict],
    current_value: float,
    current_nav: float = 0.0,
) -> dict: ...
```

**Returns:**
```python
{
    'invested_amount': 95684.50,        # Sum of all Invested transactions
    'redeemed_amount': 0.0,             # Sum of Redeemed (redemption proceeds)
    'net_invested': 95684.50,           # invested - redeemed
    'absolute_gain': 6347.50,           # current - net_invested
    'absolute_return_pct': 6.63,        # (gain / net_invested) × 100
    'xirr_pct': 12.96,                  # XIRR solver output × 100
    'first_investment_date': datetime.date(2024, 5, 1),
    'transactions': [
        {'date': datetime.date(2025, 1, 1), 'type': 'Invested', 'units': 50.52, 'nav': 162.00, 'amount': 8184.24},
        ...
    ]
}
```

**Logic:**
1. Sum all Invested rows → invested_amount
2. Sum all Redeemed rows → redeemed_amount
3. Compute net_invested = invested - redeemed
4. Get current_value from calling function (MutualFunds row)
5. Compute absolute_gain = current_value − net_invested
6. Compute return % = (gain / net_invested) × 100
7. Build cashflows list for XIRR:
   - For each transaction: (date, −amount for Invested, +amount for Redeemed)
    - Append (today, +current_value) when current_value is positive.
8. Call xirr(cashflows) → XIRR rate → multiply by 100 for percentage
9. Track first_investment_date (currently the earliest matching ledger entry).
10. Compute remaining FIFO average cost and holding-period classifications via
    [dashboard/services/capital_gains.py](dashboard/services/capital_gains.py).

The function always returns a dictionary. Missing ledger rows produce empty
transactions, zero amount fields, and unavailable rate/cost fields. Non-positive
net investment suppresses percentage return/CAGR, not the entire analytics result.
An unsolvable XIRR sets only `xirr_pct` to None.

**Remaining cost versus cash invested:** after purchasing 100 units at INR 10
and 50 at INR 12, redeeming 130 at INR 20 leaves 20 units with FIFO basis INR 240
and average cost INR 12. Net cash invested is INR -1,000 (1,600 - 2,600), which
must not be used as remaining cost basis.

Holding-period splits use an approximate 365-day threshold. They are not a
tax-liability calculation and do not implement all asset-specific tax rules.
Purchase-ledger mark-to-market values value each original purchase at today's
NAV, even if units were subsequently sold; they are not remaining-lot values.

#### Function 2: Portfolio-Level Analytics

```python
def _portfolio_mf_analytics(
    mf_list: list[dict],
    mf_txns: list[dict],
) -> dict: ...
```

**Critical Logic:**
Only includes funds that have MFTransactions records. This prevents untracked funds from inflating portfolio gain.

**Returns:**
```python
{
    'invested_amount': 95684.50,      # Purchases across tracked funds
    'redeemed_amount': 0.0,
    'net_invested': 95684.50,
    'tracked_current_value': 102032.00,  # Only funds with a transaction ledger
    'absolute_gain': 6347.50,         # current - net_invested
    'absolute_return_pct': 6.63,      # (gain / net_invested) × 100
    'xirr_pct': 12.96                 # Portfolio XIRR (annualized)
}
```

**Key difference from per-fund:**
- Pools cashflows from **all tracked funds**
- Ignores funds without MFTransactions records
- Avoids artificial inflation from untracked holdings

**Example:**
```
Fund A: invested 40,000, current 44,000 (has transactions) ✓ counted
Fund B: invested 0,     current 60,000 (no transactions)   ✗ ignored
Portfolio result: invested 40,000, current 44,000, gain 10%
NOT: invested 40,000, current 104,000, gain 160% ❌
```

### Data Quality Validation: `dashboard/services/validators.py`

**Function:**
```python
def validate_portfolio_data(data: dict) -> list[str]
```

**Check: MFTransactions Reconciliation**
- For each fund with MFTransactions:
  - Compute net units: Σ(Invested) − Σ(Redeemed)
  - Compare to declared units in MutualFunds sheet
  - If |net − declared| > tolerance, warn

**Tolerance:**
```python
tolerance = max(0.01, abs(declared_units) * 0.005)
# i.e., 0.5% or 0.01 units minimum, whichever is larger
```

**Warning message:**
```
MFTransactions for '{fund_name}' (net units {net:.2f}) do not match declared units {declared:.2f}. 
Gain and XIRR calculations may be inaccurate.
```

**Why it matters:**
- Partial ledgers (missing months) cause net units to be too low
- Gain and XIRR become artificially high on incomplete data
- Early detection prevents incorrect analysis

### Integration: `dashboard/services/aggregator.py`

`_build_payload()` passes the parsed dictionary to `build_portfolio(data)`.
The calculation engine computes the transaction analytics; there is no separate
aggregator `_calculate_mf_analytics` method or `ParsedData` object.

**Field added to PortfolioSummary:**
```python
{
    ...
    'mf_analytics': {
        'invested_amount': 95684.50,
        'tracked_current_value': 102032.00,
        'absolute_gain': 6347.50,
        'absolute_return_pct': 6.63,
        'xirr_pct': 12.96
    }
}
```

**If no transactions:** analytics uses an empty/default dictionary with no
meaningful return rate; the template falls back to the basic holding display.

### Template Display: `dashboard/templates/dashboard/dashboard.html`

**MF Blade:**
- Per-fund columns include average cost, invested, gain (INR and %), XIRR, CAGR.
- Portfolio summary shows net investment, tracked current value, gain and XIRR.
- Transaction history: `<details>` disclosure listing all SIP transactions with Date, Type, Units, NAV, Amount

**Fallback for funds without transactions:**
- Display "–" for analytics columns
- No transaction history
- Footer note: "Based on funds with recorded transactions only"

---

## Part 3: Economic Asset Allocation (Look-Through)

### Purpose

Answer "what do I actually own economically?" by mapping all holdings to six standard asset classes:

**Six Buckets:**
- **Equity**: Stocks (local and international)
- **Corporate Debt**: Bonds issued by companies
- **Government Securities**: Treasury, GSecs, bonds issued by governments
- **Cash**: Savings, FD, RD, money-market
- **Gold**: Physical gold, gold ETFs
- **Other**: Uncategorized or special assets

**Why it matters:**
- Mutual fund labels (Equity, Hybrid, Debt) don't reveal true underlying risk
- Hybrid funds with different equity percentages are not comparable
- Retirement accounts (EPF, NPS) have opaque equity exposure
- Look-through identifies **hidden equity** (e.g., EPF's 15% equity slice)

### Implementation: `dashboard/services/economic_allocation.py`

#### Step 1: Classification by Product Type

**For Mutual Funds:**
```python
def _classify_mf_category(fund: dict) -> str
```

Heuristic classification based on parsed `fund_name` and `fund_type`:
- "Equity" → Equity
- "Debt" or "Bond" → Corporate Debt
- "Gilt" or "G-Sec" → Government Securities
- "Hybrid" and related labels → Hybrid (60/40 mix)
- "Arbitrage" → Arbitrage (special cash/equity mix)
- Remaining mutual funds default to equity; review overrides for unusual funds.

**Returns:** `EQUITY_FUND`, `DEBT_FUND`, `HYBRID_FUND`, `ARBITRAGE_FUND`, or `GILT_FUND`.

**For Retirement/Liquid/Emergency/Metals:**
```python
def _classify_instrument_category(type_label: str) -> str
```

**Mapping:**
- "EPF" → EPF (known 85% Govt Sec / 15% Equity)
- "PPF" → PPF; NPS has no default mix.
- "FD", "RD", "Savings", "Current", "Bank", "Cash" → Cash
- "Gold", "Silver" → Gold
- Unrecognized instrument types return None and fall back to Other without overrides.

### Step 2: Default Look-Through Mix

**`_DEFAULT_MIX` dictionary:**

```python
_DEFAULT_MIX = {
    'EQUITY_FUND': {'equity': 100},
    'DEBT_FUND': {'corporate_debt': 100},
    'HYBRID_FUND': {'equity': 60, 'corporate_debt': 40},
    'ARBITRAGE_FUND': {'equity': 20, 'cash': 80},
    'GILT_FUND': {'govt_securities': 100},
    'EPF': {'govt_securities': 85, 'equity': 15},
    'PPF': {'govt_securities': 100},
    'CASH_LIKE': {'cash': 100},
    'GOLD_LIKE': {'gold': 100},
}
```

**Why NPS has no default:**
- User instruction: "do NOT guess scheme split without override"
- NPS can be 100% equity, 100% debt, or hybrid depending on fund choice
- Without explicit LookThrough row, NPS is marked unclassified (not guessed)

### Step 3: Override Resolution

**Function:**
```python
def _resolve_mix(
    key: str,
    category: str,
    overrides: dict
) -> tuple: ...
```

**Resolution order (first match wins):**
1. **Explicit override** from LookThrough sheet keyed by fund Identifier or Type
   - Source: "override"
   - Example: "120716" → {Equity: 50, Debt: 30, GovtSec: 20}
2. **Default mix** from `_DEFAULT_MIX` if category is known
   - Source: "default"
   - Example: Equity → {Equity: 100}
3. **Other/Unclassified** if no override and no default
   - Source: "unclassified"
   - Added to warnings list with fund name and reason

**Returns:** `(mix_dict, style_dict_or_None, source)`. Override keys are normalized
to uppercase. Positive mix/style weights are normalized separately to 100%.

### Step 4: Main Orchestrator

**Function:**
```python
def build_economic_allocation(
    data: dict,
    portfolio: PortfolioSummary
) -> dict: ...
```

**Returns comprehensive report:**
```python
{
    'basis_total': 100000.0,
    'buckets': [
        {
            'key': 'equity', 'label': 'Equity', 'value': 60000.0,
            'pct': 60.0, 'target_pct': 55.0, 'deviation_pct': 5.0,
            'contributors': [
                {'label': 'Hybrid Fund', 'value': 60000.0,
                 'mix_pct': 60.0, 'source': 'default'},
            ],
        },
        # Five more bucket rows, including zero-value buckets.
    ],
    'chart': {'labels': ['Equity', 'Corporate Debt'],
              'values': [60000.0, 40000.0], 'colours': ['#4f8ef7', '#9333ea']},
    'equity_style': [
        {'key': 'unclassified', 'label': 'Unclassified', 'value': 60000.0, 'pct': 100.0},
    ],
    'effective_equity_pct': 60.0,
    'naive_equity_pct': 0.0,
    'hidden_equity_delta_pct': 60.0,
    'unclassified_notes': [],
    # Additional top-level value/percentage and presence fields are also returned.
}
```

**Calculation Details:**

1. **For each holding (MF, Retirement, Liquid, etc.):**
   - Get value (Units × NAV or declared Amount)
   - Classify by type → category
   - Resolve mix (override → default → other)
   - Distribute value across buckets: `bucket_amount = holding_value × bucket_pct / 100`
   - Track contributor: name, amount, percentage, source

2. **Aggregate by bucket:**
   - Sum all contributions to each bucket
   - Compute bucket % = (bucket_amount / total_portfolio) × 100
   - Compute contributors table (sortable by amount)

3. **Equity style split (if LookThrough has style columns):**
   - For each Equity contribution with style breakdown
   - Distribute: `Large_amount = Equity_amount × EquityLarge_pct / 100`
   - Pool and compute Large/Mid/Small/Intl percentages

4. **Hidden equity detection:**
     - naive_equity_pct = the Equity row of the product-label MF split / total net worth
   - effective_equity_pct = total Equity bucket % after look-through
     - hidden_equity_delta_pct = effective minus naive; it can be negative.
     - This is a label comparison, not a comprehensive risk score.

5. **Target deviations (if Targets sheet):**
   - For each target: current % from buckets, target % from sheet
   - deviation = current − target (in percentage points)
   - Positive = over target, negative = under target

6. **Unclassified warnings:**
   - Collect all holdings with source = "unclassified"
   - Add to unclassified_notes list (e.g., NPS without override)
   - Propagated to aggregator warnings

### Step 5: Data Quality

The allocation engine normalizes positive override/style weights; there is no
95%-105% sum constraint. Missing/zero mixes fall back to defaults. Targets need
not sum to 100, and zero targets are retained. Target names must match display
labels (for example `Corporate Debt`, `Government Securities`) ignoring case.

### Template Display: `dashboard/templates/dashboard/dashboard.html`

**Economic Allocation Blade:**

1. **Doughnut Chart:** 6-color pie showing bucket percentages
2. **Summary Panel:**
   - "Label Equity: 12.0%"
   - "Effective Equity: 18.7%"
   - "Hidden Equity: +6.7 pts" (in orange if > 0)
3. **Main Table:**
    - Columns: Asset Class, Value (INR), Current %, Target %, Deviation
    - Rows: one per bucket in the engine's fixed bucket order
4. **Expandable Contributors (per bucket):**
    - Disclosure list: Product/Scheme, Contribution, Mix Used, Source
   - Expandable to show where equity exposure comes from
5. **Equity Style Breakdown (if present):**
   - Table: Large, Mid, Small, Intl percentages
6. **Conditional Notes:**
   - "No LookThrough sheet found; using default classification" (if absent)
   - "No Targets sheet found; deviation not computed" (if absent)

### Integration: `dashboard/services/aggregator.py`

`_build_payload()` calls `build_economic_allocation(data, portfolio)`, stores the
report in `payload['economic_allocation']`, and adds unclassified notes to
warnings. Do not copy raw exception details into user-visible messages.

**Defensive try/except:**
- If engine fails, warnings are added (not a fatal error)
- Dashboard displays with partial data

**In `dashboard/views.py` (context entry):**
```python
context = {
    ...
    'economic_allocation': payload.get('economic_allocation'),
}
```

---

## Part 4: Example Walkthrough

This simplified example assumes two holdings and no other positive asset values;
a valid workbook still needs all six required sheets.

| Holding | Ledger | Current value |
|---------|--------|---------------|
| Fund A, 100 units | PURCHASE 100 at NAV 10, Amount 1,000 | 100 at NAV 12 = INR 1,200 |
| Fund B, 100 units | No transactions | 100 at NAV 8 = INR 800 |

Fund A has net investment INR 1,000, gain INR 200, absolute return 20%, and
remaining FIFO average cost INR 10. Portfolio transaction analytics includes
only Fund A; net worth and allocation include both funds, totaling INR 2,000.
The engine adds Fund A's current value as today's final XIRR cashflow. The rate
depends on the actual purchase date; it cannot be inferred from gain alone.

With LookThrough overrides of 100% Equity for A and 100% CorporateDebt for B,
economic allocation is Equity 60%, Corporate Debt 40%. Targets of Equity 55%
and Corporate Debt 45% produce deviations of +5 and -5 percentage points.
The ledger's 100 net units reconcile with Fund A's declared units.

---

## Part 5: Edge Cases and Known Limitations

### XIRR

| Case | Behavior | Example |
|------|----------|---------|
| Recent investment (< 1 day) | XIRR undefined | Bought today, no time elapsed |
| High intra-year volatility | May oscillate | NAV swings 20%/month |
| Negative returns | Returns negative rate | Loss of capital |
| Breaking even | Returns 0.0 | Current = Invested |
| Multiple zero-crossings | May find one root or none; not all roots | Alternating investments/redemptions |

Short holding periods can produce extreme annualized rates. There is no 30-day
display restriction in the current implementation.

### MFTransactions Reconciliation

| Case | Behavior | Example |
|------|----------|---------|
| Partial ledger (missing months) | Warning: units don't match | Only 6 months of 12 recorded |
| Rounding differences | Tolerated to 0.5% | 100.0 declared vs 99.95 actual |
| No MFTransactions | Silent (backward compatible) | Old workbooks still work |
| Decimal precision loss | Parser normalizes | 0.001 units preserved |

### Economic Allocation

| Case | Behavior | Example |
|------|----------|---------|
| No LookThrough sheet | Uses all defaults | Fund classification only |
| NPS without override | Marked unclassified | Warning added to dashboard |
| Unrecognized MF category | Defaults to equity | Use an explicit LookThrough override |
| Very small holdings (<0.01%) | Included but may round to 0% | Micro amount in bucket |
| Equity style split but 0% equity | Ignored (no equity to split) | Debt fund with style columns |
| Targets summing to 95% | Accepted (loose validation) | 55% + 40% = 95% (5% unallocated) |

---

## Part 6: Testing Guide

### Focused Tests

- [tests/test_xirr.py](tests/test_xirr.py): solver and invalid-input boundaries.
- [tests/test_calculation_engine.py](tests/test_calculation_engine.py) and
    [tests/test_capital_gains.py](tests/test_capital_gains.py): tracked-fund gains,
    FIFO redemptions, remaining cost basis and holding periods.
- [tests/test_excel_parser.py](tests/test_excel_parser.py) and
    [tests/test_validators.py](tests/test_validators.py): parsing and reconciliation.
- [tests/test_economic_allocation.py](tests/test_economic_allocation.py): defaults,
    overrides, hidden equity, targets and equity style.
- [tests/test_net_worth_history.py](tests/test_net_worth_history.py): CSV and
    stubbed S3 history; no real S3 writes.
- [tests/test_dashboard_ui.py](tests/test_dashboard_ui.py),
    [tests/test_aggregator.py](tests/test_aggregator.py) and
    [tests/test_hardening.py](tests/test_hardening.py): UI, snapshot protection,
    finite-number guards and stubbed cleanup safety.

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_xirr.py -v

# Specific test
pytest tests/test_economic_allocation.py -k hidden_equity -v

# With coverage
pytest tests/ --cov=dashboard/services --cov-report=term-missing
```

Coverage requires `pytest-cov` and a separate measured run; no coverage
percentage is asserted here. The CSV JavaScript regression requires Node and
skips when Node is unavailable. See the dated verification ledger for results.

---

## Part 7: Common Troubleshooting

### XIRR Returns None

**Symptom:** Transaction history shows no XIRR percentage.

**Root causes:**
1. Only 1 cashflow recorded (need ≥2)
2. Only inflows/redemptions exist (no investment outflow)
3. All cashflows are outflows (no current value)
4. All dates are the same, values are invalid, or the rate is outside solver bounds

**Fix:**
- Verify real purchases/redemptions and current holdings/NAV.
- Do not add a fabricated current-value transaction to MFTransactions: the
    calculation engine already adds the terminal valuation automatically.

### MFTransactions Reconciliation Warning

**Symptom:** Dashboard shows "MFTransactions for 'Fund X' do not match declared units."

**Root cause:**
- Ledger net units (Invested - Redeemed) ≠ declared Units
- Typically: partial ledger (missing months)

**Fix:**
- Complete the ledger with all historical SIPs
- Or remove the fund from MFTransactions if history unavailable

### NPS Marked as Unclassified

**Symptom:** Economic allocation shows NPS in "Other" bucket with unclassified note.

**Root cause:**
- NPS scheme mix unknown without explicit LookThrough entry
- Cannot guess (could be 100% equity, 100% debt, or hybrid)

**Fix:**
- Add LookThrough row for NPS with actual fund allocation
- Example: NPS, 50 (Equity), 30 (Debt), 20 (GovtSec)

### Hidden Equity Shows Negative

**Symptom:** "Hidden equity: −5 pts" (negative).

**Root cause:**
- Effective equity (after look-through) is LESS than naive equity
- Hybrid funds are 40% equity despite Hybrid label

**Interpretation:**
- Equity exposure is lower than the product-label baseline. This alone does
    not establish that total portfolio risk is lower or returns will be higher.

---

## Part 8: Future Enhancements

1. **Transaction editing UI:** Allow adding/modifying MFTransactions in-app
2. **Recurring SIP templates:** Auto-generate next month's SIP entry
3. **Benchmark comparison:** Show XIRR vs. index/peer fund returns
4. **Rebalancing suggestions:** Alert when deviation exceeds threshold
5. **Tax calculation:** Extend the existing FIFO/holding-period analytics with
    asset-specific tax rules, only with explicit requirements and tests
6. **Income analysis:** Compute dividend yield and interest income

---

## Part 9: API Reference

### Key Functions by File

**xirr.py:**
- `xirr(cashflows)` → float | None

**excel_parser.py:**
- `ExcelParser.load()` returns the parsed dictionary.
- `_parse_mf_transactions()` returns a flat list of ledger rows.
- `_parse_lookthrough()` returns a list of override rows.
- `_parse_targets()` returns a label-to-percentage dictionary.

**calculation_engine.py:**
- `_fund_transaction_analytics(identifier, txns, current_value, current_nav=0.0)` → dict
- `_portfolio_mf_analytics(mf_list, mf_txns)` → dict

**economic_allocation.py:**
- `build_economic_allocation(data, portfolio)` → dict
- `_classify_mf_category(fund)` → str
- `_classify_instrument_category(type_label)` → str
- `_resolve_mix(key, category, overrides)` → (mix, style_or_None, source)

**validators.py:**
- `validate_portfolio_data(data)` → list[str]
- `require_finite_values(value, path="portfolio")` raises on non-finite numeric data.

---

## Part 10: Daily Net Worth History

[dashboard/services/net_worth_history.py](dashboard/services/net_worth_history.py)
stores one date-only record per save day. The CSRF-protected `POST /net-worth/`
view computes the amount from the loaded portfolio, ignoring posted fake totals.
It rejects parser errors and reports failed writes without claiming success.

| Mode | Storage | Date |
|------|---------|------|
| Local localhost Excel, DEBUG, outside Lambda | `cache/net_worth.csv` | Computer date |
| Configured S3 bucket, Excel or Google Sheet | `net-worth/history/YYYY-MM-DD.json` | Django localdate, UTC by default |
| Local demo | `cache/net_worth_demo.csv` | 54 samples across the preceding year |

CSV columns and S3 JSON fields are `date,total_net_worth`. Values are finite and
rounded to two decimals. Local writes use a process lock plus atomic replacement;
an unreadable CSV is not overwritten. S3 reads paginate and validate records;
writes use AES256 and the same existing private bucket as Zappa artifacts.

Same-day saves replace the value, including decreases. S3 versioning retains
earlier versions; concurrent same-day writes are last-write-wins. Different days
use independent keys. There is no automatic daily scheduler, source refetch,
monthly-history migration, or per-user/workbook partition.

The view reads history outside the cached portfolio payload. The full-width
trend chart filters calendar 3M/6M/1Y/All ranges anchored at the latest record.
Demo history is isolated locally; cloud demo actions are denied. S3 errors do
not fall back to CSV or SQLite. Without configured history, legacy monthly
SQLite chart behavior remains; parser errors now prevent snapshot overwrite.

Cold starts can still lose the loaded workbook: reload it to show the chart.
Backup and deployment instructions are in [OPERATIONS.md](OPERATIONS.md) and
[DEPLOYMENT.md](DEPLOYMENT.md).

## Part 11: Input and Export Hardening

- Gold/silver fallback values are zero when no usable live/cache price exists;
    warnings distinguish missing prices from real valuations.
- Workbook checks enforce compressed/expanded size and ZIP structure limits.
- Google URLs require HTTPS on approved Google hosts with validated sheet IDs;
    both public reads and chunked private downloads enforce the size limit.
- Chart data uses Django `json_script`. CSV cells are quoted, embedded quotes
    escaped, and formula-leading `=`, `+`, `-`, `@` text prefixed with an apostrophe.
- The export labeled Excel is CSV, and PDF export uses the browser print flow.
- Security dependency pins and residual cloud risks are tracked in
    [DASHBOARD_AUDIT.md](DASHBOARD_AUDIT.md).

**End of Detailed Feature Documentation**

Use this guide alongside:
- [AI_CONTEXT.md](AI_CONTEXT.md) for system overview
- [AI_FULL_REPO_PROMPT.md](AI_FULL_REPO_PROMPT.md) for operational guidelines
- [OPERATIONS.md](OPERATIONS.md) for runtime behavior
- [DEPLOYMENT.md](DEPLOYMENT.md) for workbook schema
- [CHECKLIST.md](CHECKLIST.md) for setup and sample workbook creation
