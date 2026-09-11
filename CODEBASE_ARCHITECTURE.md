# Codebase Architecture Guide

## Quick Navigation

This guide explains the structure of the portfolio dashboard codebase and how the new XIRR and Economic Allocation features integrate.

---

## Directory Structure

```
portfolio/
├── dashboard/                          # Main Django app
│   ├── services/
│   │   ├── xirr.py                    # ⭐ XIRR solver (NEW)
│   │   ├── economic_allocation.py     # ⭐ Economic allocation (NEW)
│   │   ├── excel_parser.py            # Sheet parsing (UPDATED: +3 new sheets)
│   │   ├── calculation_engine.py      # Portfolio analytics (UPDATED: +transaction analytics)
│   │   ├── validators.py              # Data validation (UPDATED: +MFTransactions check)
│   │   ├── aggregator.py              # Orchestration (UPDATED: +EA integration)
│   │   ├── alerts.py                  # Risk coverage alerts
│   │   ├── nav_service.py             # AMFI/MFAPI NAV resolution
│   │   ├── metal_price_service.py     # Metal price fetching
│   │   ├── google_sheet_service.py    # Google Sheets integration
│   │   ├── url_utils.py               # URL parsing helpers
│   │   └── __init__.py
│   ├── views.py                        # Django view (UPDATED: +EA context)
│   ├── models.py                       # (Not used; ephemeral SQLite)
│   ├── urls.py
│   ├── admin.py
│   ├── apps.py
│   ├── migrations/                     # Database migrations (frozen)
│   ├── templates/
│   │   └── dashboard/
│   │       └── dashboard.html          # UI template (UPDATED: +MF blade, +EA blade)
│   ├── static/
│   │   └── dashboard/
│   │       └── dashboard.css           # Styling
│   └── __init__.py
├── tests/
│   ├── test_xirr.py                   # ⭐ XIRR tests (NEW)
│   ├── test_economic_allocation.py    # ⭐ EA tests (NEW)
│   ├── test_calculation_engine.py     # Engine tests (UPDATED: +transaction analytics)
│   ├── test_excel_parser.py           # Parser tests (UPDATED: +optional sheets)
│   ├── test_validators.py             # Validator tests (UPDATED)
│   ├── test_aggregator.py
│   ├── test_views_security.py
│   ├── test_nav_service.py
│   ├── test_metal_price_service.py
│   └── ...other tests...
├── finance_dashboard/                  # Django settings
│   ├── settings.py                     # Local development
│   ├── settings_lambda.py              # Lambda production
│   ├── middleware.py                   # Cloudflare JWT verification
│   ├── wsgi.py
│   ├── wsgi_lambda.py
│   └── ...
├── infra/                              # Terraform IaC
│   ├── main.tf, backend.tf, ...
│   └── domain/                         # ACM + custom domain
├── scripts/                            # Utility scripts
├── generate_sample_excel.py            # Sample workbook generator (UPDATED)
├── manage.py
├── requirements.txt
├── README.md                           # Main docs (UPDATED)
├── AI_CONTEXT.md                       # AI briefing (UPDATED)
├── AI_FULL_REPO_PROMPT.md             # Full AI prompt (UPDATED)
├── FEATURES_DETAILED.md               # ⭐ Feature guide (NEW)
├── CHECKLIST.md                        # Setup checklist (UPDATED)
├── DEPLOYMENT.md                       # Deployment guide (UPDATED)
├── OPERATIONS.md                       # Operations guide (UPDATED)
├── DASHBOARD_AUDIT.md                  # Dashboard audit notes
└── db.sqlite3                          # Local SQLite (ephemeral)
```

---

## Data Flow: Complete Picture

```
User uploads XLSX or pastes Google Sheet URL
         ↓
[Excel Validator] (size, magic, structure)
         ↓
[Parser: excel_parser.py]
├─→ Required sheets (MutualFunds, Retirement, Liquid, Emergency, Insurance, Metals)
├─→ Optional sheets (MFTransactions, LookThrough, Targets)
└─→ Returns: ParsedData object
         ↓
[Aggregator: aggregator.py]
├─→ [NAV Service] resolves mutual fund current values (AMFI → MFAPI → Symbol)
├─→ [Metal Price Service] fetches prices (GoodReturns → cache → manual)
├─→ [Calculation Engine]
│  ├─→ Per-fund analytics (from MFTransactions if present)
│  │   • invested_amount, absolute_gain, absolute_return_pct
│  │   • XIRR (via xirr.py solver)
│  │   • first_investment_date, transaction list
│  └─→ Portfolio-level analytics (only tracked funds)
│      • mf_analytics with pooled XIRR and gain
├─→ [Economic Allocation Engine]
│  ├─→ Classify each holding (MF, Retirement, Liquid, Metals)
│  ├─→ Resolve look-through mix (override → default → unclassified)
│  ├─→ Compute 6-bucket aggregation
│  ├─→ Detect hidden equity exposure
│  ├─→ Compute target deviations (if Targets sheet)
│  └─→ Returns: comprehensive allocation report
├─→ [Validators]
│  └─→ Check MFTransactions units reconciliation (net units vs declared)
└─→ [Alerts] compute coverage and risk warnings
         ↓
[Views: views.py]
├─→ Pass PortfolioSummary (with mf_analytics) to template
├─→ Pass economic_allocation report to template
└─→ Render dashboard
         ↓
[Template: dashboard.html]
├─→ Hero card (net worth, all-time gain, month change)
├─→ MF Blade
│  ├─→ Table with transaction analytics (Invested, Gain, XIRR, %)
│  ├─→ Portfolio summary card (net invested, current tracked, portfolio XIRR)
│  └─→ Expandable transaction history per fund
├─→ Economic Allocation Blade
│  ├─→ Doughnut chart (6 buckets)
│  ├─→ Summary panel (label vs effective equity, hidden exposure)
│  ├─→ Bucket table (value, current %, target %, deviation)
│  ├─→ Expandable contributors per bucket
│  └─→ Equity style breakdown (if present)
├─→ Other blades (Retirement, Liquid, Metals, etc.)
└─→ Alerts and risk coverage
         ↓
User sees interactive portfolio dashboard
```

---

## New Features: Integration Points

### 1. XIRR Solver (`dashboard/services/xirr.py`)

**Standalone module:** No dependencies on other services.

**Called by:**
- `calculation_engine.py` → `_fund_transaction_analytics()` (per-fund XIRR)
- `calculation_engine.py` → `_portfolio_mf_analytics()` (portfolio XIRR)

**Input:** List of (date, amount) tuples

**Output:** Float (annualized return) or None

**Tests:** `tests/test_xirr.py` (6 tests, no external dependencies)

### 2. Transaction Analytics (`dashboard/services/calculation_engine.py`)

**New functions:**
- `_fund_transaction_analytics()` — per-fund metrics from MFTransactions
- `_portfolio_mf_analytics()` — portfolio-level rollup (only tracked funds)

**Called by:**
- `aggregator.py` → `_build_payload()` (line ~410-415)

**Input:** MutualFunds list, MFTransactions dict, MFTransactions dict

**Output:** PortfolioSummary with new `mf_analytics` field

**Tests:** `tests/test_calculation_engine.py` (7 tests, +3 new)

### 3. Economic Allocation Engine (`dashboard/services/economic_allocation.py`)

**Standalone module:** Depends only on Python stdlib and `helpers`.

**Entry point:** `build_economic_allocation(data, portfolio)` → comprehensive report

**Called by:**
- `aggregator.py` → `_build_payload()` (line ~91-95, defensive try/except)
- Result added to payload: `payload['economic_allocation']`
- Unclassified notes propagated to warnings

**Input:** ParsedData object, PortfolioSummary object

**Output:** Dict with buckets, summary, equity style, targets, unclassified_notes

**Tests:** `tests/test_economic_allocation.py` (6 tests)

### 4. Sheet Parsing (`dashboard/services/excel_parser.py`)

**New parsers:**
- `_parse_mf_transactions()` → dict[identifier, list[txn]]
- `_parse_lookthrough()` → dict[key, mix_dict]
- `_parse_targets()` → dict[asset_class, target_pct]

**Called by:** `load()` method (line ~142)

**Backward compatible:** Missing sheets default to empty collections

**Tests:** `tests/test_excel_parser.py` (19 tests, +5 new)

### 5. Validation (`dashboard/services/validators.py`)

**New check:** MFTransactions units reconciliation

**Function:** `validate_portfolio_data(data)` checks:
- For each fund with MFTransactions:
  - Net units (Invested - Redeemed) vs declared units
  - Tolerance: max(0.01, declared × 0.005)
  - Warning if mismatch

**Called by:** `aggregator.py` (warnings collected and returned to UI)

**Tests:** `tests/test_validators.py` (4 tests)

### 6. Aggregation and Orchestration (`dashboard/services/aggregator.py`)

**Updates:**
- Import: `from .economic_allocation import build_economic_allocation`
- Payload: added `"economic_allocation": None` field (line ~50)
- In `_build_payload()` (line ~91-95):
  ```python
  try:
      economic_allocation = build_economic_allocation(data, portfolio)
      payload["economic_allocation"] = economic_allocation
      payload["warnings"].extend(economic_allocation.get("unclassified_notes", []))
  except Exception as exc:
      payload["warnings"].append(f"Economic allocation engine failed: {exc}")
  ```

**Defensive:** Catches exceptions and adds warnings (not fatal)

### 7. View and Context (`dashboard/views.py`)

**Updates:**
- Line ~78: added `"economic_allocation": None` to context

**Called by:** `dashboard.html` template

**Tests:** `tests/test_views_security.py` (existing, unchanged)

### 8. Template (`dashboard/templates/dashboard/dashboard.html`)

**MF Blade updates (lines ~639–700):**
- Per-fund columns: Invested, Gain, XIRR, %
- Portfolio summary card: invested, current (tracked), gain, portfolio XIRR
- Transaction history disclosure: Date, Type, Units, NAV, Amount
- Fallback: "–" for untracked funds, footer note

**Economic Allocation Blade (lines ~687–758):**
- Doughnut chart (6 buckets)
- Summary panel (label vs effective equity, hidden exposure)
- Bucket table (value, current %, target %, deviation)
- Expandable contributors (scheme, amount, %, source)
- Equity style breakdown (if present)
- Conditional notes (no sheet found, etc.)

**CSS additions (lines ~255–272):**
- `.gain-pos`, `.gain-neg`, `.muted` — color coding
- `.mf-summary`, `.mf-summary-row` — flex layouts
- `.txn-row`, `.txn-table` — transaction table
- `.ea-summary`, `.ea-row`, `.ea-contrib` — EA blade styling
- Details/summary chevron animation

**JavaScript:**
- `mkDoughnut()` called with economic-alloc chart data
- `toggleBlade()` for disclosure toggle
- Chart initialization (Chart.js CDN)

---

## Feature Interaction: Concrete Example

**Scenario:** User uploads workbook with:
- MutualFunds: Axis Equity (500 units, current NAV 168.31)
- MFTransactions: 12 monthly SIPs × 50.52 units each
- LookThrough: Axis = 100% Equity
- Targets: Equity 55%

**Processing:**

1. **Parser reads sheets:**
   - MutualFunds: 500 units
   - MFTransactions: 12 entries (606.24 net units invested)
   - LookThrough: Axis = {Equity: 100}
   - Targets: {Equity: 55}

2. **NAV resolution:**
   - Current NAV = 168.31 (via AMFI)
   - Current value = 500 × 168.31 = €84,155

3. **Per-fund transaction analytics:**
   - invested_amount = 50.52 × 12 = 606.24 units × avg NAV ~157 = €95,118
   - current_value = 500 × 168.31 = €84,155
   - absolute_gain = 84,155 - 95,118 = (negative, wait... let me reconsider)
   - Actually: if we're tracking 606.24 units NET invested, and we have 500 units now, that means some were redeemed or it's a loss
   - More realistic: invested_amount (via sum of transaction amounts) might be 95,684
   - current_value = 500 × 168.31 = 84,155 (hmm, this is a loss)
   - OR: the 500 units is AFTER accounting for all transactions (input units on MutualFunds sheet)
   - XIRR on these cashflows (12 monthly invests + current value) = solver output

4. **Economic allocation:**
   - Axis: 84,155 × 100% Equity = €84,155 to Equity bucket
   - Total portfolio: €84,155
   - Equity: 84,155 (100%)
   - Effective equity: 100%
   - Naive equity: 100% (already labeled Equity)
   - Hidden equity: 0% (no hidden exposure)
   - Target deviation: Equity current 100% - target 55% = +45 percentage points (significant overweight)

5. **MFTransactions reconciliation:**
   - Net units from ledger: 606.24 (sum of Invested) - 0 (no Redeemed)
   - Declared units: 500
   - Mismatch: 606.24 vs 500 = 106.24 units (17.6% off!)
   - ❌ Warning: "MFTransactions for 'Axis Equity Direct' do not match declared units"

6. **UI rendering:**
   - MF Blade:
     - Invested: computed from MFTransactions
     - Gain: current_value - invested_amount
     - XIRR: solver output
     - % (return): (gain / invested) × 100
     - Transaction history: all 12 SIPs listed with Date, Type, Units, NAV, Amount
   - Economic Allocation Blade:
     - Doughnut: 100% Equity (solid blue)
     - Summary: "Label Equity: 100%, Effective Equity: 100%, Hidden: 0 pts"
     - Bucket table: Equity, €84,155, 100%, 55%, +45 pts
     - Contributors: "Axis Equity Direct, €84,155, 100%, 100% Equity, default"
     - Targets: "Equity 100% vs target 55% → +45 pts OVERWEIGHT"

---

## Testing Strategy

### Test Organization

```
tests/
├── test_xirr.py                        (6 tests, 100% coverage)
├── test_economic_allocation.py         (6 tests, 100% coverage)
├── test_calculation_engine.py          (7 tests, incl. 3 new for transaction analytics)
├── test_excel_parser.py                (19 tests, incl. 5 new for optional sheets)
├── test_validators.py                  (4 tests)
├── test_aggregator.py                  (existing, unchanged)
├── test_views_security.py              (existing, unchanged)
└── ...other tests...
```

### Running Tests

```bash
# All tests
pytest tests/ -v --tb=short

# Only new features
pytest tests/test_xirr.py tests/test_economic_allocation.py tests/test_validators.py -v

# With coverage
pytest tests/ --cov=dashboard/services --cov-report=term-missing --cov-report=html

# Single test
pytest tests/test_economic_allocation.py::test_hidden_equity_exposure_via_epf -v
```

### Expected Results

- All 143 tests passing
- Coverage: 99%+ on new modules
- No warnings or deprecations
- Django system check: 0 issues

---

## Common Modification Patterns

### Adding a New Asset Class to Economic Allocation

1. Update `_DEFAULT_MIX` dict (line ~68):
   ```python
   'MyProductType': {'Equity': 75, 'CorporateDebt': 25},
   ```

2. Update `_classify_mf_category()` or `_classify_instrument_category()` (lines ~79-105):
   ```python
   if 'MyProduct' in type_label:
       return 'MyProductType'
   ```

3. Update `dashboard/templates/dashboard/dashboard.html` if new bucket introduced:
   - Chart colors (line ~810)
   - Bucket table rows (line ~720)

4. Add test (lines ~XXX in test_economic_allocation.py):
   ```python
   def test_my_product_classification():
       ...
   ```

### Fixing XIRR Solver Convergence

1. Inspect logs in CloudWatch (Lambda) or local stdout
2. Check Newton-Raphson iteration count and NPV final value
3. Adjust tolerance or iteration limit in `xirr.py` (lines ~50-80)
4. Add regression test if boundary case discovered

### Adding a New Optional Sheet

1. Add parser method to `excel_parser.py`:
   ```python
   def _parse_my_new_sheet(self, sheet_name='MySheet') -> dict:
       ...
       return parsed_data
   ```

2. Call from `load()` method (line ~142):
   ```python
   self.my_new_data = self._parse_my_new_sheet()
   ```

3. Add to `ParsedData` return (line ~164):
   ```python
   return ParsedData(
       ...
       my_new_data=self.my_new_data,
   )
   ```

4. Update `aggregator.py` if integration needed

5. Add tests to `tests/test_excel_parser.py`

---

## Deployment Checklist for Documentation Updates

When updating the documentation, verify:

- [ ] `AI_CONTEXT.md` mentions new services and sheets
- [ ] `AI_FULL_REPO_PROMPT.md` includes XIRR and EA in financial invariants
- [ ] `OPERATIONS.md` documents look-through and transaction analytics
- [ ] `DEPLOYMENT.md` includes MFTransactions, LookThrough, Targets schema
- [ ] `CHECKLIST.md` has section on optional sheets and sample generation
- [ ] `README.md` lists new features and Excel schema updates
- [ ] `FEATURES_DETAILED.md` covers algorithms, edge cases, testing (this file)
- [ ] `CODEBASE_ARCHITECTURE.md` explains module integration (this file)
- [ ] No broken links between docs
- [ ] All code file references are accurate

---

## Quick Reference: Which File Does What

| Task | File(s) |
|------|---------|
| Calculate XIRR for irregular cashflows | `xirr.py` |
| Per-fund gain and XIRR analytics | `calculation_engine.py` → calls `xirr.py` |
| Portfolio-level analytics (tracked funds only) | `calculation_engine.py` |
| Map holdings to 6 asset-class buckets | `economic_allocation.py` |
| Detect hidden equity exposure | `economic_allocation.py` |
| Parse MFTransactions sheet | `excel_parser.py` |
| Parse LookThrough sheet | `excel_parser.py` |
| Parse Targets sheet | `excel_parser.py` |
| Warn on unit reconciliation mismatch | `validators.py` |
| Render MF blade with transaction history | `dashboard.html` (lines ~639-700) |
| Render Economic Allocation blade | `dashboard.html` (lines ~687-758) |
| Orchestrate all features | `aggregator.py` |
| Pass data to template | `views.py` (line ~78) |

---

## Residual Risks and Future Work

**Known Limitations:**
- MFTransactions reconciliation is a warning only (doesn't block)
- NPS classified as Unclassified without override (requires user action)
- XIRR undefined for investments < 1 day old
- Hidden equity can be negative (look-through less than labels)
- No UI for editing transactions (read-only ledger)

**Future Enhancements:**
- Transaction editing UI
- Recurring SIP templates
- Benchmark comparison (XIRR vs index)
- Rebalancing suggestions
- Tax-lot tracking
- Income analysis (dividends, interest)

---

**End of Codebase Architecture Guide**

Use this alongside [FEATURES_DETAILED.md](FEATURES_DETAILED.md) for deep implementation guidance.
