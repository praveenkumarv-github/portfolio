# 🔄 MIGRATION GUIDE - v1 to v2

## 📋 Overview

This guide helps you migrate your existing Excel file from v1 schema to v2 schema.

---

## 🗂️ Schema Changes

### 1. MutualFunds Sheet

#### OLD FORMAT (v1)
```
Date | FundName | InvestedAmount | CurrentValue | Units
```

#### NEW FORMAT (v2)
```
FundName | Units | Identifier
```

#### Migration Steps:
1. **Keep**: FundName, Units
2. **Remove**: Date, InvestedAmount, CurrentValue
3. **Add**: Identifier (AMFI code)

#### Finding AMFI Codes:
- Visit: https://www.amfiindia.com/net-asset-value/nav-history
- Search for your fund name
- Copy the scheme code (usually 6 digits)
- Or use: https://api.mfapi.in/ to search

**Example:**
```
OLD: 2024-01-01 | HDFC Top 100 | 50000 | 62000 | 1250
NEW: HDFC Top 100 | 1250 | 120503
```

---

### 2. Liquid Sheet

#### OLD FORMAT (v1)
```
Source | Amount
```

#### NEW FORMAT (v2)
```
AccountName | Type | Amount
```

#### Migration Steps:
1. **Rename**: Source → AccountName
2. **Add**: Type column
3. **Fill Type**: "Savings" for bank accounts, "Cash" for cash

**Example:**
```
OLD: Savings Bank | 150000
NEW: HDFC Savings | Savings | 150000

OLD: Cash | 15000
NEW: Cash in Hand | Cash | 15000
```

---

### 3. EmergencyFund Sheet

#### OLD FORMAT (v1)
```
Type | Amount
```

#### NEW FORMAT (v2)
```
AccountName | Type | Amount | MaturityDate
```

#### Migration Steps:
1. **Add**: AccountName column (name each account)
2. **Keep**: Type, Amount
3. **Add**: MaturityDate (YYYY-MM-DD format, leave blank if not applicable)

**Example:**
```
OLD: RD | 75000
NEW: SBI RD | RD | 75000 | 2027-04-29

OLD: FD | 150000
NEW: HDFC FD | FD | 150000 | 2028-04-29

OLD: Bank | 50000
NEW: Axis Savings | Bank | 50000 | (blank)
```

---

### 4. Metals Sheet (NEW)

#### Add this sheet if you have gold/silver:
```
Type | Quantity
Gold | 50
Silver | 500
```

- **Type**: Gold or Silver
- **Quantity**: In grams

If you don't have metals, you can:
- Leave the sheet blank
- Or remove the sheet (warning will show but won't break)

---

### 5. Retirement & Insurance (UNCHANGED)

These sheets remain the same:

**Retirement:**
```
Type | Amount
```

**Insurance:**
```
Type | Provider | Premium | Coverage
```

---

## 📝 Step-by-Step Migration

### Step 1: Backup Your Current File
```
Copy your existing Excel file to a backup location
```

### Step 2: Open Your Excel File

### Step 3: Update MutualFunds Sheet
1. Delete columns: Date, InvestedAmount, CurrentValue
2. Add column: Identifier (after Units)
3. Fill in AMFI codes for each fund
4. Reorder columns: FundName, Units, Identifier

### Step 4: Update Liquid Sheet
1. Rename column: Source → AccountName
2. Add column: Type (between AccountName and Amount)
3. Fill Type: "Savings" or "Cash"
4. Give each account a descriptive name

### Step 5: Update EmergencyFund Sheet
1. Insert column: AccountName (before Type)
2. Add column: MaturityDate (after Amount)
3. Fill AccountName with descriptive names
4. Fill MaturityDate in YYYY-MM-DD format (or leave blank)

### Step 6: Add Metals Sheet (Optional)
1. Create new sheet: "Metals"
2. Add columns: Type, Quantity
3. Add rows for Gold and/or Silver
4. Enter quantities in grams

### Step 7: Save and Upload
1. Save the Excel file
2. Upload to the dashboard
3. Verify all data loads correctly

---

## 🔍 Validation Checklist

Before uploading:

- [ ] MutualFunds has 3 columns: FundName, Units, Identifier
- [ ] All AMFI codes are filled (6-digit numbers)
- [ ] Liquid has 3 columns: AccountName, Type, Amount
- [ ] EmergencyFund has 4 columns: AccountName, Type, Amount, MaturityDate
- [ ] Retirement unchanged: Type, Amount
- [ ] Insurance unchanged: Type, Provider, Premium, Coverage
- [ ] Metals sheet added (or prepared to ignore warning)

---

## 💡 Tips

### Finding AMFI Codes:
1. **Google Search**: "AMFI code [fund name]"
2. **Fund Fact Sheet**: Check your fund's official website
3. **MFAPI**: Use https://api.mfapi.in/mf/[try-numbers]

### Common AMFI Codes:
- HDFC Top 100: 120503
- SBI Blue Chip: 120518
- ICICI Prudential Technology: 120586
- Axis Mid Cap: 120505
- Nippon India Small Cap: 118989

### Account Naming:
- Be descriptive: "HDFC Savings Primary" instead of "Bank1"
- Include bank name: "SBI RD Monthly" instead of "RD1"
- Helps track multiple accounts clearly

### Maturity Dates:
- Format: YYYY-MM-DD (e.g., 2027-12-31)
- Leave blank for savings accounts
- For RD/FD: use actual maturity date
- Helps plan for upcoming maturities

---

## ⚠️ Common Issues

### Issue: NAV shows 0 or "Manual Input Required"
**Cause**: Invalid AMFI code or API unavailable
**Fix**: 
- Verify AMFI code is correct
- Check internet connection
- Use manual cache editing (see QUICKSTART_V2.md)

### Issue: Metal prices show 0
**Cause**: Auto-fetch not implemented, manual input required
**Fix**: Edit `cache/metal_cache.json` with current prices

### Issue: Old file format doesn't load
**Cause**: Schema mismatch
**Fix**: Follow this migration guide completely

---

## 📊 Migration Example

### Original File (v1):
**MutualFunds:**
```
Date       | FundName         | InvestedAmount | CurrentValue | Units
2024-01-01 | HDFC Top 100     | 50000          | 62000        | 1250
2024-01-01 | SBI Blue Chip    | 75000          | 85000        | 1800
```

**Liquid:**
```
Source          | Amount
Savings Bank    | 150000
Cash            | 15000
```

**EmergencyFund:**
```
Type | Amount
RD   | 75000
FD   | 150000
```

### Migrated File (v2):
**MutualFunds:**
```
FundName         | Units | Identifier
HDFC Top 100     | 1250  | 120503
SBI Blue Chip    | 1800  | 120518
```

**Liquid:**
```
AccountName      | Type    | Amount
HDFC Savings     | Savings | 150000
Cash in Hand     | Cash    | 15000
```

**EmergencyFund:**
```
AccountName | Type | Amount | MaturityDate
SBI RD      | RD   | 75000  | 2027-04-29
HDFC FD     | FD   | 150000 | 2028-04-29
```

**Metals:** (NEW)
```
Type   | Quantity
Gold   | 50
Silver | 500
```

---

## ✅ Post-Migration

After successful upload:

1. **Verify Summary Table**
   - All categories appear
   - Totals are correct

2. **Check NAV Badges**
   - Mutual funds show NAV source
   - Green badge = cached
   - Blue badge = from API

3. **Verify Metals**
   - If manual input required, edit cache
   - Values should appear in summary

4. **Review Detail Sections**
   - All accounts listed
   - Maturity dates visible

---

## 🆘 Need Help?

If migration fails:
1. Check error messages in dashboard
2. Review UPGRADE_NOTES.md
3. Use sample_finance_data.xlsx as reference
4. Verify Excel sheet names match exactly

---

**📌 Remember: Backup your original file before migration!**
