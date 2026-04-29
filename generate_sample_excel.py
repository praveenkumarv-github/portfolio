"""
Generate Sample Excel File for Finance Dashboard (Updated Schema)
Run this script to create sample_finance_data.xlsx
"""
import pandas as pd
from datetime import datetime, timedelta
import os

# Create sample data for each sheet

# MUTUAL FUNDS - NEW SCHEMA: FundName, Units, Identifier
mutual_funds_data = {
    'FundName': [
        'HDFC Top 100 Fund',
        'SBI Blue Chip Fund',
        'ICICI Prudential Technology Fund',
        'Axis Mid Cap Fund',
        'Nippon India Small Cap Fund',
    ],
    'Units': [
        1250.50,
        1800.75,
        750.25,
        1050.00,
        625.50,
    ],
    'Identifier': [
        '120503',  # AMFI codes (MFAPI compatible)
        '120518',
        '120586',
        '120505',
        '118989',
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

# Create DataFrames
df_mutual_funds = pd.DataFrame(mutual_funds_data)
df_retirement = pd.DataFrame(retirement_data)
df_liquid = pd.DataFrame(liquid_data)
df_emergency_fund = pd.DataFrame(emergency_fund_data)
df_insurance = pd.DataFrame(insurance_data)
df_metals = pd.DataFrame(metals_data)

# Write to Excel file with multiple sheets
output_file = 'sample_finance_data.xlsx'

with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    df_mutual_funds.to_excel(writer, sheet_name='MutualFunds', index=False)
    df_retirement.to_excel(writer, sheet_name='Retirement', index=False)
    df_liquid.to_excel(writer, sheet_name='Liquid', index=False)
    df_emergency_fund.to_excel(writer, sheet_name='EmergencyFund', index=False)
    df_insurance.to_excel(writer, sheet_name='Insurance', index=False)
    df_metals.to_excel(writer, sheet_name='Metals', index=False)

print(f"✅ Sample Excel file created: {output_file}")
print(f"📍 Location: {os.path.abspath(output_file)}")
print("\n📊 Sample Data Summary (Updated Schema):")
print(f"  - Mutual Funds: {len(df_mutual_funds)} entries (Units + AMFI codes)")
print(f"  - Retirement: {len(df_retirement)} accounts")
print(f"  - Liquid: {len(df_liquid)} accounts (with names)")
print(f"  - Emergency Fund: {len(df_emergency_fund)} accounts (with maturity dates)")
print(f"  - Insurance: {len(df_insurance)} policies")
print(f"  - Metals: {len(df_metals)} types (Gold & Silver)")
print("\n⚠️  NOTE:")
print("  - NAV will be fetched automatically using AMFI codes")
print("  - Metal prices require manual input (or will use cached values)")
print("  - If offline, NAV fetching will fallback to cached values")

