"""
Generate Sample Excel File for Finance Dashboard (Updated Schema)
Run this script to create sample_finance_data.xlsx
"""
import pandas as pd
from datetime import datetime, timedelta
import os

# Create sample data for each sheet

# MUTUAL FUNDS - NEW SCHEMA: FundName, Units, Identifier, Symbol
mutual_funds_data = {
    'FundName': [
        'UTI Nifty 50 Index Fund Direct Growth',
        'Kotak Nifty Next 50 Index Fund Direct Growth',
        'Navi Nifty Smallcap250 Momentum Quality 100 Index Fund Direct Growth',
        'Nippon India Nifty IT Index Fund Direct Growth',
        'Motilal Oswal ELSS Tax Saver Fund Direct Growth',
        'Sundaram Arbitrage Fund Direct Growth',
    ],
    'Units': [
        606.20,
        1485.98,
        3650.36,
        4039.20,
        865.75,
        3194.04,
    ],
    'Identifier': [
        '120716',
        '148745',
        '153362',
        '152392',
        '133386',
        '149550',
    ],
    'Symbol': [
        'MUTF_IN:UTI_NIFT_50_FGX2CX',
        'MUTF_IN:KOTA_NIFT_NEXT_73M1DZ',
        'MUTF_IN:NAVI_NIFT_SMCP_3JD6FI',
        'MUTF_IN:NIPP_INDI_NIFT_L2SD3Y',
        'MUTF_IN:MOTI_OSWA_ELSS_GGNULV',
        'MUTF_IN:SUND_ARBI_DIR_14G5PYB',
    ],
}

# RETIREMENT - Same schema
retirement_data = {
    'Type': ['PF', 'NPS'],
    'Amount': [350000, 180000],
}

# LIQUID - NEW SCHEMA: AccountName, Type, Amount
liquid_data = {
    'AccountName': ['HDFC Savings', 'ICICI Current', 'Cash in Hand'],
    'Type': ['Savings', 'Savings', 'Cash'],
    'Amount': [150000, 50000, 15000],
}

# EMERGENCY FUND - NEW SCHEMA: AccountName, Type, Amount, MaturityDate
emergency_fund_data = {
    'AccountName': ['SBI RD', 'HDFC FD', 'Axis Savings', 'Emergency Cash'],
    'Type': ['RD', 'FD', 'Bank', 'Cash'],
    'Amount': [75000, 150000, 50000, 10000],
    'MaturityDate': [
        (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d'),
        (datetime.now() + timedelta(days=730)).strftime('%Y-%m-%d'),
        '',
        '',
    ],
}

# INSURANCE - Same schema
insurance_data = {
    'Type': ['Health', 'Term', 'Life'],
    'Provider': ['Star Health', 'LIC', 'HDFC Life'],
    'Premium': [25000, 18000, 15000],
    'Coverage': [500000, 10000000, 5000000],
}

# METALS - NEW SHEET: Type, Quantity
metals_data = {
    'Type': ['Gold', 'Silver'],
    'Quantity': [50, 500],  # in grams
}

# MF TRANSACTIONS - NEW SHEET: SIP/lump-sum ledger per fund (optional)
# Powers Invested-vs-Current, absolute gain, and XIRR in the MF blade.
# UTI Nifty 50 (identifier 120716) gets a realistic 12-month SIP history
# that reconciles to its full 606.20 declared Units; the other funds have
# no ledger, demonstrating the "no history available" fallback state too.
_sip_months = 12
_sip_units_per_month = round(606.20 / _sip_months, 4)
_sip_nav_series = [148.00, 150.40, 152.10, 149.80, 153.60, 156.20,
                   158.90, 161.30, 163.00, 165.40, 167.10, 168.31]
mf_transactions_data = {
    'FundIdentifier': ['120716'] * _sip_months,
    'Date': [
        (datetime.now() - timedelta(days=30 * (_sip_months - i))).strftime('%Y-%m-%d')
        for i in range(_sip_months)
    ],
    'Type': ['Invested'] * _sip_months,
    'Units': [_sip_units_per_month] * _sip_months,
    'NAV': _sip_nav_series,
}

# LOOKTHROUGH - NEW SHEET: economic look-through overrides (optional)
# Key = fund Identifier for mutual funds, or Type for retirement/liquid/
# emergency-fund/metals rows. Percentages should sum to 100.
lookthrough_data = {
    'Key': ['NPS'],
    'Equity': [50],
    'CorporateDebt': [30],
    'GovtSecurities': [20],
    'Cash': [0],
    'Gold': [0],
    'Other': [0],
}

# TARGETS - NEW SHEET: target asset allocation (optional)
# Powers the Current % vs Target % vs Deviation column in Economic Allocation.
targets_data = {
    'AssetClass': ['Equity', 'Corporate Debt', 'Government Securities', 'Cash', 'Gold'],
    'TargetPct': [55, 15, 15, 5, 10],
}

# Create DataFrames
df_mutual_funds = pd.DataFrame(mutual_funds_data)
df_retirement = pd.DataFrame(retirement_data)
df_liquid = pd.DataFrame(liquid_data)
df_emergency_fund = pd.DataFrame(emergency_fund_data)
df_insurance = pd.DataFrame(insurance_data)
df_metals = pd.DataFrame(metals_data)
df_mf_transactions = pd.DataFrame(mf_transactions_data)
df_lookthrough = pd.DataFrame(lookthrough_data)
df_targets = pd.DataFrame(targets_data)

# Write to Excel file with multiple sheets
output_file = 'sample_finance_data.xlsx'

def _write_workbook(path: str) -> None:
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        df_mutual_funds.to_excel(writer, sheet_name='MutualFunds', index=False)
        df_retirement.to_excel(writer, sheet_name='Retirement', index=False)
        df_liquid.to_excel(writer, sheet_name='Liquid', index=False)
        df_emergency_fund.to_excel(writer, sheet_name='EmergencyFund', index=False)
        df_insurance.to_excel(writer, sheet_name='Insurance', index=False)
        df_metals.to_excel(writer, sheet_name='Metals', index=False)
        df_mf_transactions.to_excel(writer, sheet_name='MFTransactions', index=False)
        df_lookthrough.to_excel(writer, sheet_name='LookThrough', index=False)
        df_targets.to_excel(writer, sheet_name='Targets', index=False)


try:
    _write_workbook(output_file)
except PermissionError:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'sample_finance_data_{ts}.xlsx'
    _write_workbook(output_file)

print(f"✅ Sample Excel file created: {output_file}")
print(f"📍 Location: {os.path.abspath(output_file)}")
print("\n📊 Sample Data Summary (Updated Schema):")
print(f"  - Mutual Funds: {len(df_mutual_funds)} entries (Units + AMFI codes + Symbol)")
print(f"  - Retirement: {len(df_retirement)} accounts")
print(f"  - Liquid: {len(df_liquid)} accounts (with names)")
print(f"  - Emergency Fund: {len(df_emergency_fund)} accounts (with maturity dates)")
print(f"  - Insurance: {len(df_insurance)} policies")
print(f"  - Metals: {len(df_metals)} types (Gold & Silver)")
print(f"  - MFTransactions: {len(df_mf_transactions)} SIP entries (optional, powers XIRR)")
print(f"  - LookThrough: {len(df_lookthrough)} override(s) (optional, economic allocation)")
print(f"  - Targets: {len(df_targets)} asset-class target(s) (optional)")
print("\n⚠️  NOTE:")
print("  - NAV will be fetched automatically using AMFI codes")
print("  - If AMFI/MFAPI fails, NAV fallback will use the Symbol column")
print("  - Metal prices require manual input (or will use cached values)")
print("  - If offline, NAV fetching will fallback to cached values")

