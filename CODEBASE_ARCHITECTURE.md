# Codebase Architecture Guide

## Quick Navigation

Reviewed **2026-10-31**. This guide maps current source ownership, financial
analytics, storage, and UI integration. Verification results are recorded in
[DOCUMENTATION_UPDATES_SUMMARY.md](DOCUMENTATION_UPDATES_SUMMARY.md).

---

## Directory Structure

```
portfolio/
├── dashboard/                          # Main Django app
│   ├── services/
│   │   ├── xirr.py                    # Bounded XIRR solver
│   │   ├── capital_gains.py           # FIFO lots and remaining cost basis
│   │   ├── economic_allocation.py     # Economic look-through allocation
│   │   ├── excel_parser.py            # Six required and three optional sheets
│   │   ├── calculation_engine.py      # Portfolio and transaction analytics
│   │   ├── validators.py              # Reconciliation and finite-value checks
│   │   ├── aggregator.py              # Payload cache and monthly snapshots
│   │   ├── net_worth_history.py       # Daily local CSV/S3 history and local demo
│   │   ├── workbook_validation.py     # XLSX size and ZIP structure checks
│   │   ├── alerts.py                  # Risk coverage alerts
│   │   ├── nav_service.py             # AMFI/MFAPI NAV resolution
│   │   ├── metal_price_service.py     # Metal price fetching
│   │   ├── google_sheet_service.py    # Google Sheets integration
│   │   ├── url_utils.py               # URL parsing helpers
│   │   └── __init__.py
│   ├── views.py                        # Workbook actions, rendering, daily save
│   ├── models.py                       # UploadedFile and NetWorthSnapshot
│   ├── urls.py
│   ├── admin.py
│   ├── apps.py
│   ├── migrations/                     # Initial schema and monthly snapshot model
│   ├── templates/
│   │   └── dashboard/
│   │       └── dashboard.html          # Self-contained UI with inline CSS/JS
│   ├── static/
│   │   └── dashboard/
│   │       └── dashboard.css           # Legacy file, not linked by template
│   └── __init__.py
├── tests/
│   ├── test_xirr.py                   # Solver and invalid-input boundaries
│   ├── test_economic_allocation.py    # Allocation defaults and overrides
│   ├── test_calculation_engine.py     # Core and transaction analytics
│   ├── test_capital_gains.py          # FIFO remaining costs and holding periods
│   ├── test_net_worth_history.py      # Local CSV and stubbed S3
│   ├── test_dashboard_ui.py           # Template and CSV export regression
│   ├── test_excel_parser.py           # Workbook parsing
│   ├── test_validators.py             # Data quality warnings
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
│   └── domain/                         # Certificate validation and custom domain
├── scripts/                            # Utility scripts
├── generate_sample_excel.py            # Sample workbook generator
├── manage.py
├── requirements.txt
├── README.md                           # Main docs
├── AI_CONTEXT.md                       # AI briefing
├── AI_FULL_REPO_PROMPT.md               # Full AI prompt
├── FEATURES_DETAILED.md                # Feature reference
├── CHECKLIST.md                        # Setup checklist
├── DEPLOYMENT.md                       # Deployment guide
├── OPERATIONS.md                       # Operations guide
├── DASHBOARD_AUDIT.md                  # Dashboard audit notes
└── db.sqlite3                          # Local SQLite; Lambda uses ephemeral /tmp
```

---

## Data Flow: Complete Picture

```
User uploads XLSX or pastes Google Sheet URL
         ↓
[Excel Validator] (size, magic, structure)
         ↓
[Parser: excel_parser.py]
├─→ Required sheets (MutualFunds, Retirement, Liquid, EmergencyFund, Insurance, Metals)
├─→ Optional sheets (MFTransactions, LookThrough, Targets)
├─→ Resolves NAV and metal prices while parsing
└─→ Returns: dictionary with rows, summaries, warnings and errors
         ↓
[Aggregator: aggregator.py]
├─→ [Calculation Engine]
│  ├─→ Per-fund analytics (from MFTransactions if present)
│  │   • invested_amount, absolute_gain, absolute_return_pct
│  │   • XIRR (via xirr.py solver)
│  │   • first_investment_date, transaction list
│  │   • remaining FIFO average cost and holding-period classifications
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
├─→ Read daily CSV/S3 history outside the cached portfolio payload
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
         ↓ explicit Update Net Worth POST
[views.update_net_worth → net_worth_history.save_net_worth]
└─→ Local CSV or one date-keyed JSON object in existing private S3 bucket
```

---

## Integration Points

### 1. XIRR Solver (`dashboard/services/xirr.py`)

**Standalone module:** No dependencies on other services.

**Called by:**
- `calculation_engine.py` → `_fund_transaction_analytics()` (per-fund XIRR)
- `calculation_engine.py` → `_portfolio_mf_analytics()` (portfolio XIRR)

**Input:** List of (date, amount) tuples

**Output:** Float (annualized return) or None

**Tests:** [tests/test_xirr.py](tests/test_xirr.py). The solver uses only stdlib.
It sorts flows internally, guards invalid/same-day inputs, and searches within
rate bounds -0.999 to 10.0. No result is represented by None, not zero.

### 2. Transaction Analytics (`dashboard/services/calculation_engine.py`)

**Analytics helpers:**
- `_fund_transaction_analytics()` — per-fund metrics from MFTransactions
- `_portfolio_mf_analytics()` — portfolio-level rollup (only tracked funds)

**Called by:**
- `build_portfolio(data)`, invoked by aggregator `_build_payload()`.

**Input:** Parsed data dictionary; MFTransactions is a flat list of ledger rows.

**Output:** `PortfolioSummary` with per-fund and pooled analytics, FIFO remaining
cost, and purchase-ledger valuation/grouping fields. Insurance is excluded.

**Tests:** [tests/test_calculation_engine.py](tests/test_calculation_engine.py)
and [tests/test_capital_gains.py](tests/test_capital_gains.py).

### 3. Economic Allocation Engine (`dashboard/services/economic_allocation.py`)

**Standalone module:** Uses Python stdlib and the supplied portfolio object.

**Entry point:** `build_economic_allocation(data, portfolio)` → comprehensive report

**Called by:**
- `aggregator.py` → `_build_payload()` (defensive try/except)
- Result added to payload: `payload['economic_allocation']`
- Unclassified notes propagated to warnings

**Input:** Parsed dictionary, `PortfolioSummary` object

**Output:** Dictionary with a bucket list, chart, equity-style list, top-level
equity comparisons, unclassified notes, and presence flags. Targets/deviations
are fields on bucket rows, not a separate targets dictionary.

**Tests:** [tests/test_economic_allocation.py](tests/test_economic_allocation.py).

### 4. Sheet Parsing (`dashboard/services/excel_parser.py`)

**Optional parsers:**
- `_parse_mf_transactions()` → list[txn] with an identifier on each row
- `_parse_lookthrough()` → list[override] with a key on each row
- `_parse_targets()` → dict[asset_class, target_pct]

**Called by:** `ExcelParser.load()`

**Backward compatible:** Missing sheets default to empty collections

**Tests:** [tests/test_excel_parser.py](tests/test_excel_parser.py).
MFTransactions accepts preferred Scheme Name/Transaction Type or legacy
FundIdentifier/Type columns. Invalid numeric/date/type/name rows warn and skip.

### 5. Validation (`dashboard/services/validators.py`)

**Checks:** MFTransactions units reconciliation and recursive finite-value guards

**Function:** `validate_portfolio_data(data)` checks:
- For each fund with MFTransactions:
  - Net units (Invested - Redeemed) vs declared units
  - Tolerance: max(0.01, declared × 0.005)
  - Warning if mismatch

**Called by:** `aggregator.py` (warnings collected and returned to UI)

`require_finite_values` rejects non-finite numeric input before portfolio output.
**Tests:** [tests/test_validators.py](tests/test_validators.py) and
[tests/test_hardening.py](tests/test_hardening.py).

### 6. Aggregation and Orchestration (`dashboard/services/aggregator.py`)

`build_dashboard_context` caches a payload by workbook path/mtime. `_build_payload`
parses, validates, builds the portfolio, alerts, and economic allocation. Error
and warning lists are copied. The monthly `NetWorthSnapshot` write runs only
without parser errors, preserving the previous snapshot on partial input.

Economic allocation failure produces a warning; daily history I/O belongs to the
view/service boundary and is not included in this cached payload.

### 7. View and Context (`dashboard/views.py`)

`dashboard_view` obtains the portfolio payload and reads CSV/S3 history on each
render. It copies errors before adding storage failures to avoid mutating the
cache. A loaded workbook is still required, including after a Lambda cold start.

`update_net_worth` is POST-only and CSRF-protected. It derives the amount from the
loaded portfolio, rejects parser errors, and reports write success only after
storage succeeds. It does not reload the original Google Sheet automatically.

Tests live in [tests/test_views_security.py](tests/test_views_security.py) and
[tests/test_net_worth_history.py](tests/test_net_worth_history.py).

### 8. Template (`dashboard/templates/dashboard/dashboard.html`)

**MF Blade:**
- Per-fund columns: Invested, Gain, XIRR, %
- Portfolio summary card: invested, current (tracked), gain, portfolio XIRR
- Transaction history disclosure: Date, Type, Units, NAV, Amount
- Fallback: "–" for untracked funds, footer note

**Economic Allocation Blade:**
- Doughnut chart (6 buckets)
- Summary panel (label vs effective equity, hidden exposure)
- Bucket table (value, current %, target %, deviation)
- Expandable contributors (scheme, amount, %, source)
- Equity style breakdown (if present)
- Conditional notes (no sheet found, etc.)

**Inline CSS:**
- `.gain-pos`, `.gain-neg`, `.muted` — color coding
- `.mf-summary`, `.mf-summary-row` — flex layouts
- `.txn-row`, `.txn-table` — transaction table
- `.ea-summary`, `.ea-row`, `.ea-contrib` — EA blade styling
- Details/summary chevron animation

**JavaScript:**
- `mkDoughnut()` called with economic-alloc chart data
- `toggleBlade()` for disclosure toggle
- Chart initialization (Chart.js CDN)
- Theme toggle, print/PDF and CSV export; CSV cells neutralize formula prefixes.
- Trend ranges use dates, not row counts, with stable full-width canvas sizing.

### 9. Daily History (`dashboard/services/net_worth_history.py`)

- Local localhost Excel mode writes `cache/net_worth.csv` atomically and uses the
   computer date. Demo writes a separate `cache/net_worth_demo.csv` only locally.
- `NET_WORTH_HISTORY_BUCKET` selects S3 mode for Excel and Google Sheets. Keys
   are `net-worth/history/YYYY-MM-DD.json`, using Django's configured time zone.
- S3 reads paginate and validate records. Same-day saves replace the current
   value; different dates use independent keys. No silent fallback on S3 errors.
- Terraform versions the existing private artifact bucket and grants Lambda only
   prefix-scoped listing/GetObject/PutObject. The patcher derives the history
   bucket from the same bucket selected for Zappa deployment.
- History is shared per deployment. SQLite monthly snapshots are not migrated.

---

## Feature Interaction: Concrete Example

Assume the only positive holding is 100 units of Fund A with current NAV INR 12.
Its ledger contains a purchase of 100 units at NAV INR 10, Amount INR 1,000.

1. The parser resolves Scheme Name to Identifier and reads the dated purchase.
2. The engine computes value INR 1,200, net investment INR 1,000, gain INR 200,
   absolute return 20%, and remaining FIFO average cost INR 10.
3. XIRR uses the dated investment plus today's INR 1,200 value. The rate depends
   on elapsed time and is not necessarily 20%.
4. An explicit 100% Equity override allocates INR 1,200 to Equity. A 55% Equity
   target produces +45 percentage points deviation.
5. Ledger net units 100 match declared units 100. Missing units would warn;
   a market price decrease alone does not reduce unit count.
6. Explicit Update Net Worth saves today's INR 1,200. A later same-day valuation
   of INR 1,100 replaces that day's value, not just its maximum.

---

## Testing Strategy

### Test Organization

```
tests/
├── test_xirr.py, test_calculation_engine.py, test_capital_gains.py
├── test_economic_allocation.py, test_excel_parser.py, test_validators.py
├── test_net_worth_history.py, test_dashboard_ui.py, test_aggregator.py
├── test_hardening.py, test_views_security.py, test_workbook_validation.py
├── test_patch_zappa_settings.py, test_lambda_runtime.py
└── ...service, authentication, and DNS tests...
```

### Running Tests

```bash
# All tests
pytest tests/ -v --tb=short

# Focused analytics tests
pytest tests/test_xirr.py tests/test_economic_allocation.py tests/test_validators.py -v

# Optional coverage run, requires pytest-cov
pytest tests/ --cov=dashboard/services --cov-report=term-missing --cov-report=html

# Single test
pytest tests/test_economic_allocation.py -k hidden_equity -v
```

### Verification Scope

Use the dated record in [DOCUMENTATION_UPDATES_SUMMARY.md](DOCUMENTATION_UPDATES_SUMMARY.md).
No coverage percentage is claimed. S3 and cleanup tests use stubs, not real AWS.
CSV JavaScript tests require Node. Local Python 3.14 results do not replace the
target Python 3.11 Ubuntu/Lambda validation workflow or production checks.

---

## Common Modification Patterns

### Adding a New Asset Class to Economic Allocation

1. Update `_DEFAULT_MIX` using the existing lowercase internal bucket keys:
   ```python
   'MY_PRODUCT_TYPE': {'equity': 75, 'corporate_debt': 25},
   ```

2. Update `_classify_mf_category()` or `_classify_instrument_category()`:
   ```python
      if type_label.lower() == 'myproduct':
         return 'MY_PRODUCT_TYPE'
   ```

3. Update `dashboard/templates/dashboard/dashboard.html` if new bucket introduced:
   - Add any new bucket to the engine's bucket definitions and returned data.
   - Verify chart colors and generic bucket/contributor rendering.

4. Add a focused regression in `test_economic_allocation.py`:
   ```python
   def test_my_product_classification():
       ...
   ```

### Fixing XIRR Solver Convergence

1. Reproduce with synthetic dated cashflows, without logging personal amounts.
2. Check signs, elapsed dates, finite inputs, bounds and residual NPV.
3. Add a focused regression before changing tolerance or iteration limits.
4. Preserve invalid-input behavior; do not turn an unsolvable rate into zero.

### Adding a New Optional Sheet

1. Add parser method to `excel_parser.py`:
   ```python
   def _parse_my_new_sheet(self, sheet_name='MySheet') -> dict:
       ...
       return parsed_data
   ```

2. Call it from `load()` and add the resulting collection to its return dictionary.
3. Apply finite-value checks and preserve missing-sheet backward compatibility.
4. Update the owning calculation service and aggregator only if integration needs it.
5. Add parser and behavior tests alongside the existing optional-sheet tests.

---

## Deployment Checklist for Documentation Updates

When updating the documentation, verify:

- [ ] `AI_CONTEXT.md` mentions new services and sheets
- [ ] `AI_FULL_REPO_PROMPT.md` includes XIRR and EA in financial invariants
- [ ] `OPERATIONS.md` documents look-through and transaction analytics
- [ ] `DEPLOYMENT.md` includes MFTransactions, LookThrough, Targets schema
- [ ] `CHECKLIST.md` has section on optional sheets and sample generation
- [ ] `README.md` lists new features and Excel schema updates
- [ ] `FEATURES_DETAILED.md` covers algorithms, edge cases, testing
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
| Remaining FIFO cost and holding periods | `capital_gains.py` |
| Daily CSV/S3 history and demo generation | `net_worth_history.py` |
| Render MF blade with transaction history | `dashboard.html` |
| Render Economic Allocation blade | `dashboard.html` |
| Orchestrate all features | `aggregator.py` |
| Pass data to template and accept daily save | `views.py` |

---

## Residual Risks and Future Work

**Known Limitations:**
- MFTransactions reconciliation is a warning only (doesn't block)
- NPS classified as Unclassified without override (requires user action)
- XIRR undefined for investments < 1 day old
- Hidden equity can be negative (look-through less than labels)
- No UI for editing transactions (read-only ledger)
- Daily history is shared by the deployment; no tenant isolation.
- Lambda workbook and monthly snapshots remain ephemeral; S3 history is separate.
- FIFO holding periods are approximate analytics, not tax-liability calculations.
- Deployment IAM remains broad despite the application-role-only PassRole policy.

**Future Enhancements:**
- Transaction editing UI
- Recurring SIP templates
- Benchmark comparison (XIRR vs index)
- Rebalancing suggestions
- Asset-specific tax calculation beyond the existing FIFO lot tracking
- Income analysis (dividends, interest)

---

**End of Codebase Architecture Guide**

Use this alongside [FEATURES_DETAILED.md](FEATURES_DETAILED.md) for deep implementation guidance.
