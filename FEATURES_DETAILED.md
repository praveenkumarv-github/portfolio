# Detailed Feature Documentation: XIRR and Economic Allocation

This document provides deep technical guidance for understanding and extending the XIRR and Economic Allocation features. Use this alongside source code for complete context.

---

## Part 1: XIRR (Internal Rate of Return) Solver

### Purpose

Calculate the annualized return (XIRR) from a portfolio of cash flows with irregular dates. This is essential for quantifying SIP returns on mutual funds and comparing against benchmarks.

### Implementation: `dashboard/services/xirr.py`

**Entry Point:**
```python
def xirr(cashflows: list[tuple[date, float]]) -> float | None
```

**Input:**
- List of tuples: `[(date_object, amount), ...]`
- Amounts: negative = outflow (investment), positive = inflow (redemption/current value)
- Dates must be in order (earliest first)
- At least 2 cash flows required

**Output:**
- Float: 0.0–1.0 representing annualized return (0.10 = 10%)
- None: if unsolvable (all outflows, single cashflow, no valid rate)

### Algorithm

**Step 1: Newton-Raphson Method**
Finds the rate `r` where Net Present Value (NPV) = 0:

```
NPV(r) = Σ[ amount / (1 + r)^(days_since_first / 365) ] = 0
```

- Start with initial guess: r = 0.1 (10%)
- Iterate: r_new = r - NPV(r) / NPV'(r)
- Converge when |NPV(r)| < 1e-10 or after 100 iterations

**Step 2: Bisection Fallback**
If Newton-Raphson doesn't converge:
- Use bisection search: r ∈ [-0.99, 100]
- Finds a root by halving intervals where NPV changes sign
- Tolerance: 1e-10

**Step 3: Return Validation**
- Return r only if |NPV(r)| < 1e-6 (close to zero)
- Otherwise return None (no valid rate found)

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
annual_return = xirr(cashflows)  # e.g., 0.15 = 15% annualized
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

### Testing

Tests in `tests/test_xirr.py`:
- `test_basic_cash_flows`: Simple +−+ sequence
- `test_zero_irr`: Flat investment (0% return)
- `test_high_volatility`: Large NAV swings
- `test_multi_year_sip`: Realistic 2-year SIP
- `test_no_cashflows`: Empty list → None
- `test_single_cashflow`: Single outflow → None

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

**Required columns:**
- `FundIdentifier`: AMFI code or ISIN (matches `MutualFunds.Identifier`)
- `Date`: Transaction date (YYYY-MM-DD, past dates only)
- `Type`: "Invested" or "Redeemed" (case-insensitive; invalid types skipped)
- `Units`: Units bought/sold (float, positive)
- `NAV`: NAV on transaction date (float, positive)

**Optional column:**
- `Amount`: If omitted, auto-computed as `Units × NAV`

### Parsing: `dashboard/services/excel_parser.py`

**Function:**
```python
def _parse_mf_transactions(self, sheet_name: str = 'MFTransactions') 
    -> dict[str, list[dict]]
```

**Returns:**
```python
{
    'identifier': [
        {
            'date': datetime.date(2025, 1, 1),
            'type': 'Invested',  # Normalized case
            'units': 100.5,
            'nav': 150.25,
            'amount': 15100.125
        },
        ...
    ]
}
```

**Validation:**
- Date must be ≤ today (future transactions skipped)
- Type must be Invested/Redeemed (unknown types skipped with warning)
- Units and NAV must be positive floats
- If sheet is absent, returns empty dict (backward compatible)

### Calculation Engine: `dashboard/services/calculation_engine.py`

#### Function 1: Per-Fund Analytics

```python
def _fund_transaction_analytics(
    identifier: str,
    transactions: list[dict],
    current_value: float
) -> dict | None
```

**Returns:**
```python
{
    'invested_amount': 95684.50,        # Sum of all Invested transactions
    'redeemed_amount': 0.0,             # Sum of Redeemed (redemption proceeds)
    'net_invested': 95684.50,           # invested - redeemed
    'current_value': 102032.00,         # From MutualFunds.Units × current NAV
    'absolute_gain': 6347.50,           # current - net_invested
    'absolute_return_pct': 6.63,        # (gain / net_invested) × 100
    'xirr_pct': 12.96,                  # XIRR solver output × 100
    'first_investment_date': '2024-05-01',
    'transactions': [
        {'date': '2025-01-01', 'type': 'Invested', 'units': 50.52, 'nav': 162.00, 'amount': 8184.24},
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
   - Append final: (today, +current_value) or last_transaction_date + 1 day
8. Call xirr(cashflows) → XIRR rate → multiply by 100 for percentage
9. Track first_investment_date (earliest Invested transaction)

**Returns None** if:
- Net invested ≤ 0 (no buy-side transactions)
- XIRR unsolvable (e.g., only 1 date, all outflows)

#### Function 2: Portfolio-Level Analytics

```python
def _portfolio_mf_analytics(
    mf_list: list[dict],
    mf_txns: dict[str, list[dict]]
) -> dict | None
```

**Critical Logic:**
Only includes funds that have MFTransactions records. This prevents untracked funds from inflating portfolio gain.

**Returns:**
```python
{
    'invested_amount': 95684.50,      # Sum across all tracked funds
    'current_value': 102032.00,       # Sum of (Units × NAV) for tracked funds only
    'absolute_gain': 6347.50,         # current - invested
    'absolute_return_pct': 6.63,      # (gain / invested) × 100
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

**In `_build_payload()`:**
```python
# Line ~410-415
if portfolio.mutual_funds:
    portfolio = self._calculate_mf_analytics(portfolio, data.mf_transactions)
    # Adds 'mf_analytics' field to PortfolioSummary
```

**Field added to PortfolioSummary:**
```python
{
    ...
    'mf_analytics': {
        'invested_amount': 95684.50,
        'current_value': 102032.00,
        'absolute_gain': 6347.50,
        'absolute_return_pct': 6.63,
        'xirr_pct': 12.96
    }
}
```

**If no transactions:** `mf_analytics = None` (funds fall back to basic display)

### Template Display: `dashboard/templates/dashboard/dashboard.html`

**MF Blade (lines ~639–700):**
- Per-fund row columns: Invested, Gain (€ + %), XIRR, Return %
- Portfolio summary card: "Invested (net) | Current (tracked) | Gain (€ + %) | Portfolio XIRR"
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

Heuristic classification based on `FundName`:
- "Equity" → Equity
- "Debt" or "Bond" → Corporate Debt
- "Gilt" or "G-Sec" → Government Securities
- "Hybrid" → Hybrid (50/50 mix)
- "Arbitrage" → Arbitrage (special cash/equity mix)
- Unknown → Other

**Returns:** One of [Equity, Debt, Hybrid, Arbitrage, Gilt, Other]

**For Retirement/Liquid/Emergency/Metals:**
```python
def _classify_instrument_category(type_label: str) -> str
```

**Mapping:**
- "EPF" → EPF (known 85% Govt Sec / 15% Equity)
- "NPS", "PPF" → NPS, PPF (explicit names)
- "FD", "RD", "Savings", "CA" → Cash
- "Gold", "Silver" → Gold
- Custom entries → Custom

### Step 2: Default Look-Through Mix

**`_DEFAULT_MIX` dictionary (lines ~46–68):**

```python
_DEFAULT_MIX = {
    'Equity': {'Equity': 100},                              # 100% equity
    'Debt': {'CorporateDebt': 100},                          # 100% corporate debt
    'Hybrid': {'Equity': 60, 'CorporateDebt': 40},           # 60/40 equity/debt
    'Arbitrage': {'Equity': 20, 'Cash': 80},                 # 20/80 (low risk, opportunistic)
    'Gilt': {'GovtSecurities': 100},                         # 100% govt securities
    'EPF': {'GovtSecurities': 85, 'Equity': 15},             # EPFO published mix
    'PPF': {'GovtSecurities': 100},                          # 100% govt securities
    'NPS': {},                                               # (intentionally empty; see unclassified)
    'Cash': {'Cash': 100},                                   # 100% cash
    'Gold': {'Gold': 100},                                   # 100% gold
    'Other': {'Other': 100},                                 # 100% other (fallback)
}
```

**Why NPS is empty:**
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
) -> tuple[dict, str]
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

**Returns:** (mix_dict, source) where mix_dict = {bucket: percentage, ...}

### Step 4: Main Orchestrator

**Function:**
```python
def build_economic_allocation(
    data: ParsedData,
    portfolio: PortfolioSummary
) -> dict
```

**Returns comprehensive report:**
```python
{
    'buckets': {
        'Equity': {
            'amount': 18567.50,
            'pct': 18.7,
            'contributors': [
                {'name': 'Axis Equity', 'amount': 50000, 'pct_of_bucket': 75, 'mix_pct': 100, 'source': 'default'},
                {'name': 'EPF', 'amount': 2000, 'pct_of_bucket': 25, 'mix_pct': 15, 'source': 'default'},
            ]
        },
        'CorporateDebt': {...},
        'GovtSecurities': {...},
        'Cash': {...},
        'Gold': {...},
        'Other': {...}
    },
    'summary': {
        'total_portfolio_value': 99300.50,
        'naive_equity_pct': 12.0,      # Based on Equity/Hybrid/Debt labels alone
        'effective_equity_pct': 18.7,  # Including look-through
        'hidden_equity': 6.7            # Difference (equity exposure not obvious from labels)
    },
    'equity_style': {
        'Large': 25.0,
        'Mid': 45.0,
        'Small': 20.0,
        'Intl': 10.0
    },
    'targets': {
        'Equity': {'current': 18.7, 'target': 55, 'deviation': -36.3},
        'Gold': {'current': 40.2, 'target': 10, 'deviation': +30.2},
        ...
    },
    'unclassified_notes': [
        "NPS (₹2,000.00) has no LookThrough override; classified as Other.",
    ]
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
   - naive_equity_pct = sum of funds labeled Equity, Hybrid (60%), Arbitrage (20%)
   - effective_equity_pct = total Equity bucket % after look-through
   - hidden_equity = effective − naive (should be ≥ 0)
   - Example: Equity fund 50% + Hybrid 30% (18% equity) + Arbitrage 20% (4% equity) = 72% naive
     - After look-through: actual 50% + 18% + 4% = 72% effective ✓ (no hidden)
     - But if EPF has 15% equity not in naive: effective = 73%, hidden = 1%

5. **Target deviations (if Targets sheet):**
   - For each target: current % from buckets, target % from sheet
   - deviation = current − target (in percentage points)
   - Positive = over target, negative = under target

6. **Unclassified warnings:**
   - Collect all holdings with source = "unclassified"
   - Add to unclassified_notes list (e.g., NPS without override)
   - Propagated to aggregator warnings

### Step 5: Data Quality

**Validation in `validators.py`:**
- Percentages in LookThrough must sum to ≥ 95 and ≤ 105 (allows rounding)
- Equity style split must sum to ≥ 95 and ≤ 105 if present
- Targets percentages should typically sum to 100, but not enforced (allows tilts)

### Template Display: `dashboard/templates/dashboard/dashboard.html`

**Economic Allocation Blade (lines ~687–758):**

1. **Doughnut Chart:** 6-color pie showing bucket percentages
2. **Summary Panel:**
   - "Label Equity: 12.0%"
   - "Effective Equity: 18.7%"
   - "Hidden Equity: +6.7 pts" (in orange if > 0)
3. **Main Table:**
   - Columns: Asset Class, Value (€), Current %, Target %, Deviation
   - Rows: one per bucket, sorted by value descending
4. **Expandable Contributors (per bucket):**
   - Disclosure list: Scheme/Product, Amount, % of bucket, Mix %, Source (override/default/unclassified)
   - Expandable to show where equity exposure comes from
5. **Equity Style Breakdown (if present):**
   - Table: Large, Mid, Small, Intl percentages
6. **Conditional Notes:**
   - "No LookThrough sheet found; using default classification" (if absent)
   - "No Targets sheet found; deviation not computed" (if absent)

### Integration: `dashboard/services/aggregator.py`

**In `_build_payload()` (lines ~91–95):**
```python
try:
    economic_allocation = build_economic_allocation(data, portfolio)
    payload['economic_allocation'] = economic_allocation
    payload['warnings'].extend(economic_allocation.get('unclassified_notes', []))
except Exception as exc:
    payload['warnings'].append(f"Economic allocation engine failed: {exc}")
```

**Defensive try/except:**
- If engine fails, warnings are added (not a fatal error)
- Dashboard displays with partial data

**In `dashboard/views.py` (line ~78):**
```python
context = {
    ...
    'economic_allocation': payload.get('economic_allocation'),
}
```

---

## Part 4: Example Walkthrough

### Input Excel Workbook

**MutualFunds sheet:**
```
FundName                | Units   | Identifier
Axis Equity Direct      | 500.5   | 120716
Kotak Hybrid Fund       | 250.0   | 119651
```

**MFTransactions sheet (Axis fund only):**
```
FundIdentifier | Date       | Type     | Units  | NAV
120716         | 2024-05-01 | Invested | 50.52  | 152.10
120716         | 2024-06-01 | Invested | 50.52  | 156.30
...
120716         | 2024-04-01 | Invested | 50.52  | 148.00
```

**LookThrough sheet:**
```
Key    | Equity | CorporateDebt | GovtSecurities | Cash | Gold | Other
120716 | 100    | 0             | 0              | 0    | 0    | 0
119651 | 60     | 40            | 0              | 0    | 0    | 0
```

**Targets sheet:**
```
AssetClass        | TargetPct
Equity            | 55
CorporateDebt     | 15
GovtSecurities    | 15
Cash              | 5
Gold              | 10
```

### Processing

1. **Parser reads sheets:**
   - MutualFunds: 2 funds, 750.5 total units
   - MFTransactions: 12 entries for Axis, 0 for Kotak
   - LookThrough: explicit mix for both funds

2. **Per-fund analytics (Axis fund):**
   - invested_amount: 50.52 × 12 months = 606.24 units
   - Net NAV at end: 168.31
   - current_value = 500.5 × 168.31
   - absolute_gain = current − invested
   - xirr = solver on 12 + 1 cashflows → 12.96%

3. **Per-fund analytics (Kotak fund):**
   - No MFTransactions → analytics = None
   - Displayed as "–" (no history)

4. **Portfolio analytics:**
   - Only Axis has transactions
   - invested_amount = 606.24 (Axis only)
   - current_value = 500.5 × 168.31 (Axis only)
   - Kotak (250 units worth ~42,000) is NOT included
   - Portfolio XIRR = 12.96% (Axis only)

5. **Economic allocation:**
   - Axis: 500.5 units × 168.31 = €84,300 → 100% Equity (from LookThrough override)
   - Kotak: 250 units × 155.00 = €38,750 → 60% Equity, 40% Debt (from LookThrough)
   - **Buckets:**
     - Equity: 84,300 + (38,750 × 0.6) = €107,550 (74.0%)
     - CorporateDebt: 38,750 × 0.4 = €15,500 (10.7%)
     - Others: €0
   - **Naive equity:** Axis (100% Equity) + Kotak (Hybrid → 60%) = weighted ~85%
   - **Effective equity:** 74% (lower than naive because Kotak is only 60% equity)
   - **Hidden equity:** −11% (less hidden risk than labels suggest)
   - **Targets deviations:**
     - Equity: 74% vs 55% target → +19 pts (over target)
     - Debt: 10.7% vs 15% target → −4.3 pts (under target)

6. **UI rendering:**
   - MF blade: shows Axis with XIRR, Kotak as "–"
   - EA blade: doughnut (74% Equity, 10.7% Debt), table, contributors drill-down
   - Deviation card: "Equity +19 pts over target (too much risk)"

---

## Part 5: Edge Cases and Known Limitations

### XIRR

| Case | Behavior | Example |
|------|----------|---------|
| Recent investment (< 1 day) | XIRR undefined | Bought today, no time elapsed |
| High intra-year volatility | May oscillate | NAV swings 20%/month |
| Negative returns | Returns negative rate | Loss of capital |
| Breaking even | Returns 0.0 | Current = Invested |
| Multiple zero-crossings | Picks first (Newton-Raphson) | Rare in practice |

**Recommendation:** Show XIRR only for investments > 30 days old to avoid spurious noise.

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
| Ambiguous fund name | Falls through to defaults | Custom fund name → Other |
| Very small holdings (<0.01%) | Included but may round to 0% | Micro amount in bucket |
| Equity style split but 0% equity | Ignored (no equity to split) | Debt fund with style columns |
| Targets summing to 95% | Accepted (loose validation) | 55% + 40% = 95% (5% unallocated) |

---

## Part 6: Testing Guide

### Test Files and Coverage

**`tests/test_xirr.py` (6 tests):**
- Basic monthly SIP cashflows
- Zero IRR (break-even)
- High volatility
- Multi-year investment
- Empty list handling
- Single cashflow handling

**`tests/test_economic_allocation.py` (6 tests):**
- Default classification and bucket sums
- NPS unclassified behavior
- LookThrough override priority
- Target deviation computation
- Hidden equity detection (EPF)
- Equity style split

**`tests/test_calculation_engine.py` (+3 new tests):**
- Per-fund analytics from real transactions
- Funds without transactions (None return)
- **Regression:** portfolio gain ignores untracked funds

**`tests/test_excel_parser.py` (+5 new tests):**
- Optional sheets default to empty
- MFTransactions parsed with computed amount
- Invalid transaction type handling
- LookThrough overrides parsed
- Targets sheet parsed

**`tests/test_validators.py` (new, 4 tests):**
- Reconciled ledger passes silently
- Mismatched units trigger warning
- Redemptions reduce net units correctly
- Funds without transactions skipped

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_xirr.py -v

# Specific test
pytest tests/test_economic_allocation.py::test_hidden_equity_exposure_via_epf -v

# With coverage
pytest tests/ --cov=dashboard/services --cov-report=term-missing
```

### Expected Coverage

- `xirr.py`: 100% (all paths tested)
- `economic_allocation.py`: 100% (all classifications, overrides, edges)
- `calculation_engine.py`: 99% (analytics paths)
- `excel_parser.py` (optional sheet parsing): 100%
- `validators.py` (MFTransactions check): 100%

---

## Part 7: Common Troubleshooting

### XIRR Returns None

**Symptom:** Transaction history shows no XIRR percentage.

**Root causes:**
1. Only 1 cashflow recorded (need ≥2)
2. All investments are in redemptions (no positive value)
3. All cashflows are outflows (no current value)
4. Dates too close together or in future

**Fix:**
- Add current value as final (today) cashflow in MFTransactions
- Ensure at least 1 Invested and 1 current value

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
- Portfolio risk is LOWER than labels suggest
- Good if risk-averse; bad if targeting higher returns

---

## Part 8: Future Enhancements

1. **Transaction editing UI:** Allow adding/modifying MFTransactions in-app
2. **Recurring SIP templates:** Auto-generate next month's SIP entry
3. **Benchmark comparison:** Show XIRR vs. index/peer fund returns
4. **Rebalancing suggestions:** Alert when deviation exceeds threshold
5. **Tax-lot tracking:** Track holding period for long-term capital gains
6. **Income analysis:** Compute dividend yield and interest income

---

## Part 9: API Reference

### Key Functions by File

**xirr.py:**
- `xirr(cashflows)` → float | None

**excel_parser.py:**
- `_parse_mf_transactions(sheet_name)` → dict
- `_parse_lookthrough(sheet_name)` → dict
- `_parse_targets(sheet_name)` → dict

**calculation_engine.py:**
- `_fund_transaction_analytics(identifier, txns, current_value)` → dict | None
- `_portfolio_mf_analytics(mf_list, mf_txns)` → dict | None

**economic_allocation.py:**
- `build_economic_allocation(data, portfolio)` → dict
- `_classify_mf_category(fund)` → str
- `_classify_instrument_category(type_label)` → str
- `_resolve_mix(key, category, overrides)` → (dict, str)

**validators.py:**
- `validate_portfolio_data(data)` → list[str]

---

**End of Detailed Feature Documentation**

Use this guide alongside:
- [AI_CONTEXT.md](AI_CONTEXT.md) for system overview
- [AI_FULL_REPO_PROMPT.md](AI_FULL_REPO_PROMPT.md) for operational guidelines
- [OPERATIONS.md](OPERATIONS.md) for runtime behavior
- [DEPLOYMENT.md](DEPLOYMENT.md) for workbook schema
- [CHECKLIST.md](CHECKLIST.md) for setup and sample workbook creation
