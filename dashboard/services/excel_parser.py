"""
Excel Parser Service
Handles all Excel file parsing and data validation logic
"""
import pandas as pd
import sys
from typing import Dict, Any, List
from .nav_service import get_nav_service
from .metal_price_service import get_metal_price


class ExcelParserError(Exception):
    """Custom exception for Excel parsing errors"""
    pass


class ExcelParser:
    """Parse and validate personal finance Excel files"""
    
    # Expected sheet names
    REQUIRED_SHEETS = {
        'MutualFunds': ['FundName', 'Units', 'Identifier'],
        'Retirement': ['Type', 'Amount'],
        'Liquid': ['AccountName', 'Type', 'Amount'],
        'EmergencyFund': ['AccountName', 'Type', 'Amount', 'MaturityDate'],
        'Insurance': ['Type', 'Provider', 'Premium', 'Coverage'],
        'Metals': ['Type', 'Quantity'],
    }
    
    def __init__(self, file_path: str):
        """Initialize parser with file path"""
        self.file_path = file_path
        self.excel_file = None
        self.data = {}
        self.errors = []
        self.warnings = []
        self.nav_service = get_nav_service()
    
    def load(self) -> Dict[str, Any]:
        """
        Load and parse the Excel file
        Returns a dictionary with all parsed data and metadata
        """
        try:
            # Load Excel file
            self.excel_file = pd.ExcelFile(self.file_path)
            
            # Parse each sheet
            self._parse_mutual_funds()
            self._parse_retirement()
            self._parse_liquid()
            self._parse_emergency_fund()
            self._parse_insurance()
            self._parse_metals()
            self._parse_mf_transactions()
            self._parse_lookthrough()
            self._parse_targets()

            return {
                'success': True,
                'data': self.data,
                'errors': self.errors,
                'warnings': self.warnings,
            }

        except FileNotFoundError:
            raise ExcelParserError(f"File not found: {self.file_path}")
        except ExcelParserError:
            raise
        except Exception as e:
            if "openpyxl" in str(e).lower():
                raise ExcelParserError(
                    "Error loading file: Missing optional dependency 'openpyxl' in current "
                    f"interpreter ({sys.executable}). Install with: {sys.executable} -m pip install openpyxl"
                ) from e
            raise ExcelParserError(f"Error loading file: {str(e)}")
        finally:
            # Explicitly close so Windows can release the file handle
            if self.excel_file is not None:
                try:
                    self.excel_file.close()
                except Exception:
                    pass
    
    def _parse_mutual_funds(self):
        """Parse MutualFunds sheet with Units + Identifier"""
        sheet_name = 'MutualFunds'
        
        if sheet_name not in self.excel_file.sheet_names:
            self.warnings.append(f"Sheet '{sheet_name}' not found")
            self.data['mutual_funds'] = []
            self.data['mutual_funds_summary'] = {
                'total_current_value': 0,
                'total_units': 0,
            }
            return
        
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        
        # Validate columns
        expected_cols = self.REQUIRED_SHEETS[sheet_name]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            self.errors.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)}")
            self.data['mutual_funds'] = []
            self.data['mutual_funds_summary'] = {'total_current_value': 0, 'total_units': 0}
            return
        
        # Clean data
        df = df.dropna(subset=['FundName', 'Identifier'])
        df['Units'] = pd.to_numeric(df['Units'], errors='coerce').fillna(0)
        if 'Symbol' not in df.columns:
            df['Symbol'] = ''
        
        # Convert to list of dictionaries and fetch NAV
        funds = []
        total_value = 0
        
        for _, row in df.iterrows():
            identifier = str(row['Identifier']).strip()
            fund_name = str(row['FundName']).strip()
            units = float(row['Units'])
            symbol = str(row.get('Symbol', '')).strip() if pd.notna(row.get('Symbol')) else ''
            fund_type = ""
            if 'Type' in df.columns and pd.notna(row.get('Type')):
                fund_type = str(row.get('Type')).strip()
            
            # Fetch NAV
            nav, nav_source = self.nav_service.get_nav(identifier, fund_name, symbol)
            
            if nav is None:
                nav = 0
                nav_source = "Manual Input Required"
                self.warnings.append(f"NAV not available for {fund_name} ({identifier})")
            
            current_value = units * nav
            total_value += current_value
            
            funds.append({
                'fund_name': fund_name,
                'identifier': identifier,
                'symbol': symbol,
                'fund_type': fund_type,
                'units': float(units),
                'nav': float(nav) if nav else 0,
                'nav_source': nav_source,
                'current_value': float(current_value),
            })
        
        self.data['mutual_funds'] = funds
        self.data['mutual_funds_summary'] = {
            'total_current_value': float(total_value),
            'total_units': float(df['Units'].sum()),
            'fund_count': len(funds),
        }
    
    def _parse_retirement(self):
        """Parse Retirement sheet"""
        sheet_name = 'Retirement'
        
        if sheet_name not in self.excel_file.sheet_names:
            self.warnings.append(f"Sheet '{sheet_name}' not found")
            self.data['retirement'] = []
            self.data['retirement_total'] = 0
            return
        
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        
        # Validate columns
        expected_cols = self.REQUIRED_SHEETS[sheet_name]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            self.errors.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)}")
            return
        
        # Clean data
        df = df.dropna(subset=['Type'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        
        retirement = []
        for _, row in df.iterrows():
            retirement.append({
                'type': row['Type'],
                'amount': float(row['Amount']),
            })
        
        self.data['retirement'] = retirement
        self.data['retirement_total'] = float(df['Amount'].sum())
    
    def _parse_liquid(self):
        """Parse Liquid sheet with AccountName"""
        sheet_name = 'Liquid'
        
        if sheet_name not in self.excel_file.sheet_names:
            self.warnings.append(f"Sheet '{sheet_name}' not found")
            self.data['liquid'] = []
            self.data['liquid_total'] = 0
            return
        
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        
        # Validate columns
        expected_cols = self.REQUIRED_SHEETS[sheet_name]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            self.errors.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)}")
            self.data['liquid'] = []
            self.data['liquid_total'] = 0
            return
        
        # Clean data
        df = df.dropna(subset=['AccountName'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        
        liquid = []
        for _, row in df.iterrows():
            liquid.append({
                'account_name': str(row['AccountName']),
                'type': str(row['Type']),
                'amount': float(row['Amount']),
            })
        
        self.data['liquid'] = liquid
        self.data['liquid_total'] = float(df['Amount'].sum())
    
    def _parse_emergency_fund(self):
        """Parse EmergencyFund sheet with AccountName and MaturityDate"""
        sheet_name = 'EmergencyFund'
        
        if sheet_name not in self.excel_file.sheet_names:
            self.warnings.append(f"Sheet '{sheet_name}' not found")
            self.data['emergency_fund'] = []
            self.data['emergency_fund_total'] = 0
            self.data['emergency_fund_by_type'] = {}
            return
        
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        
        # Validate columns
        expected_cols = self.REQUIRED_SHEETS[sheet_name]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            self.errors.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)}")
            self.data['emergency_fund'] = []
            self.data['emergency_fund_total'] = 0
            self.data['emergency_fund_by_type'] = {}
            return
        
        # Clean data
        df = df.dropna(subset=['AccountName'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        
        emergency_fund = []
        type_totals = {}
        
        for _, row in df.iterrows():
            account_type = str(row['Type'])
            amount = float(row['Amount'])
            
            emergency_fund.append({
                'account_name': str(row['AccountName']),
                'type': account_type,
                'amount': amount,
                'maturity_date': str(row['MaturityDate']) if pd.notna(row['MaturityDate']) else '',
            })
            
            # Aggregate by type
            type_totals[account_type] = type_totals.get(account_type, 0) + amount
        
        self.data['emergency_fund'] = emergency_fund
        self.data['emergency_fund_total'] = float(df['Amount'].sum())
        self.data['emergency_fund_by_type'] = type_totals
    
    def _parse_insurance(self):
        """Parse Insurance sheet"""
        sheet_name = 'Insurance'
        
        if sheet_name not in self.excel_file.sheet_names:
            self.warnings.append(f"Sheet '{sheet_name}' not found")
            self.data['insurance'] = []
            self.data['insurance_summary'] = {
                'total_premium': 0,
                'total_coverage': 0,
            }
            return
        
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        
        # Validate columns
        expected_cols = self.REQUIRED_SHEETS[sheet_name]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            self.errors.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)}")
            return
        
        # Clean data
        df = df.dropna(subset=['Type'])
        df['Premium'] = pd.to_numeric(df['Premium'], errors='coerce').fillna(0)
        df['Coverage'] = pd.to_numeric(df['Coverage'], errors='coerce').fillna(0)
        
        insurance = []
        for _, row in df.iterrows():
            insurance.append({
                'type': row['Type'],
                'provider': str(row['Provider']) if pd.notna(row['Provider']) else '',
                'premium': float(row['Premium']),
                'coverage': float(row['Coverage']),
            })
        
        self.data['insurance'] = insurance
        self.data['insurance_summary'] = {
            'total_premium': float(df['Premium'].sum()),
            'total_coverage': float(df['Coverage'].sum()),
        }
    
    def _parse_metals(self):
        """Parse Metals sheet (Gold, Silver) with dynamic pricing"""
        sheet_name = 'Metals'
        
        if sheet_name not in self.excel_file.sheet_names:
            self.warnings.append(f"Sheet '{sheet_name}' not found")
            self.data['metals'] = []
            self.data['metals_total'] = 0
            return
        
        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        
        # Validate columns
        expected_cols = self.REQUIRED_SHEETS[sheet_name]
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            self.errors.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)}")
            self.data['metals'] = []
            self.data['metals_total'] = 0
            return
        
        # Clean data
        df = df.dropna(subset=['Type'])
        df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0)
        
        metals = []
        total_value = 0
        
        for _, row in df.iterrows():
            metal_type = str(row['Type']).lower()
            quantity = float(row['Quantity'])
            
            # Layer-aware price resolution — NEVER returns None
            price, price_source = get_metal_price(metal_type)
            
            value = quantity * price
            total_value += value
            
            metals.append({
                'type': metal_type.capitalize(),
                'quantity': float(quantity),
                'price_per_gram': float(price) if price else 0,
                'price_source': price_source,
                'value': float(value),
            })
        
        self.data['metals'] = metals
        self.data['metals_total'] = float(total_value)

    def _parse_mf_transactions(self):
        """Parse optional MFTransactions sheet (SIP/lump-sum ledger per fund).

        Preferred columns: Scheme Name, Transaction Type, Units, NAV, Amount,
        Date. Scheme Name is resolved to MutualFunds.FundName and its matching
        Identifier is retained internally. The legacy FundIdentifier and Type
        columns remain supported. Amount is optional and otherwise calculated
        from Units * NAV.
        """
        sheet_name = 'MFTransactions'
        self.data['mf_transactions'] = []

        if sheet_name not in self.excel_file.sheet_names:
            return

        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        identifier_col = 'FundIdentifier' if 'FundIdentifier' in df.columns else None
        scheme_name_col = 'Scheme Name' if 'Scheme Name' in df.columns else None
        type_col = 'Transaction Type' if 'Transaction Type' in df.columns else 'Type'
        missing_cols = [
            col for col in ('Date', 'Units', 'NAV') if col not in df.columns
        ]
        if not identifier_col and not scheme_name_col:
            missing_cols.append('Scheme Name or FundIdentifier')
        if type_col not in df.columns:
            missing_cols.append('Transaction Type or Type')
        if missing_cols:
            self.warnings.append(
                f"{sheet_name}: Missing columns - {', '.join(missing_cols)} (transaction history skipped)"
            )
            return

        required_row_cols = ['Date', type_col]
        if identifier_col:
            required_row_cols.append(identifier_col)
        else:
            required_row_cols.append(scheme_name_col)
        df = df.dropna(subset=required_row_cols)
        df['Units'] = pd.to_numeric(df['Units'], errors='coerce').fillna(0)
        df['NAV'] = pd.to_numeric(df['NAV'], errors='coerce').fillna(0)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        has_amount = 'Amount' in df.columns
        if has_amount:
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')

        def normalize_fund_name(value: Any) -> str:
            return ' '.join(str(value).casefold().split())

        identifiers_by_name = {}
        for fund in self.data.get('mutual_funds', []):
            name = normalize_fund_name(fund.get('fund_name', ''))
            if name:
                identifiers_by_name.setdefault(name, []).append(str(fund.get('identifier', '')).strip())

        transactions = []
        for _, row in df.iterrows():
            if pd.isna(row['Date']):
                self.warnings.append(f"{sheet_name}: Skipped row with unparsable Date")
                continue
            raw_type = str(row[type_col]).strip()
            type_map = {
                'invested': 'Invested',
                'purchase': 'Invested',
                'purchased': 'Invested',
                'redeemed': 'Redeemed',
                'redeem': 'Redeemed',
                'redemption': 'Redeemed',
            }
            txn_type = type_map.get(raw_type.casefold())
            if txn_type is None:
                self.warnings.append(
                    f"{sheet_name}: Unknown {type_col} '{raw_type}' — must be PURCHASE or REDEEM"
                )
                continue

            if identifier_col:
                identifier = str(row[identifier_col]).strip()
            else:
                scheme_name = str(row[scheme_name_col]).strip()
                matches = identifiers_by_name.get(normalize_fund_name(scheme_name), [])
                if len(matches) != 1:
                    reason = 'does not match a MutualFunds FundName' if not matches else 'matches multiple MutualFunds rows'
                    self.warnings.append(
                        f"{sheet_name}: Scheme Name '{scheme_name}' {reason}; transaction skipped"
                    )
                    continue
                identifier = matches[0]

            units = float(row['Units'])
            nav = float(row['NAV'])
            amount = float(row['Amount']) if has_amount and pd.notna(row.get('Amount')) else units * nav

            transactions.append({
                'identifier': identifier,
                'date': row['Date'].to_pydatetime().date(),
                'type': txn_type,
                'units': units,
                'nav': nav,
                'amount': float(amount),
            })

        self.data['mf_transactions'] = transactions

    def _parse_lookthrough(self):
        """Parse optional LookThrough sheet (economic asset-class overrides).

        Columns: Key (Identifier for a fund, or Type for retirement/liquid/
        emergency-fund/metals rows), Equity, CorporateDebt, GovtSecurities,
        Cash, Gold, Other — all percentages of that holding's value.
        Optional style split of the Equity sleeve: EquityLarge, EquityMid,
        EquitySmall, EquityIntl.
        """
        sheet_name = 'LookThrough'
        self.data['lookthrough_overrides'] = []

        if sheet_name not in self.excel_file.sheet_names:
            return

        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        if 'Key' not in df.columns:
            self.warnings.append(f"{sheet_name}: Missing column - Key (overrides skipped)")
            return

        df = df.dropna(subset=['Key'])
        bucket_cols = ['Equity', 'CorporateDebt', 'GovtSecurities', 'Cash', 'Gold', 'Other']
        style_cols = ['EquityLarge', 'EquityMid', 'EquitySmall', 'EquityIntl']
        for col in bucket_cols + style_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else:
                df[col] = 0.0

        overrides = []
        for _, row in df.iterrows():
            overrides.append({
                'key': str(row['Key']).strip(),
                'equity': float(row['Equity']),
                'corporate_debt': float(row['CorporateDebt']),
                'govt_securities': float(row['GovtSecurities']),
                'cash': float(row['Cash']),
                'gold': float(row['Gold']),
                'other': float(row['Other']),
                'equity_large': float(row['EquityLarge']),
                'equity_mid': float(row['EquityMid']),
                'equity_small': float(row['EquitySmall']),
                'equity_intl': float(row['EquityIntl']),
            })

        self.data['lookthrough_overrides'] = overrides

    def _parse_targets(self):
        """Parse optional Targets sheet (AssetClass, TargetPct) for the
        economic allocation deviation column."""
        sheet_name = 'Targets'
        self.data['targets'] = {}

        if sheet_name not in self.excel_file.sheet_names:
            return

        df = pd.read_excel(self.excel_file, sheet_name=sheet_name)
        missing_cols = [c for c in ('AssetClass', 'TargetPct') if c not in df.columns]
        if missing_cols:
            self.warnings.append(f"{sheet_name}: Missing columns - {', '.join(missing_cols)} (targets skipped)")
            return

        df = df.dropna(subset=['AssetClass'])
        df['TargetPct'] = pd.to_numeric(df['TargetPct'], errors='coerce').fillna(0)

        targets = {}
        for _, row in df.iterrows():
            targets[str(row['AssetClass']).strip()] = float(row['TargetPct'])

        self.data['targets'] = targets


def parse_excel_file(file_path: str) -> Dict[str, Any]:
    """
    Convenience function to parse an Excel file
    Returns the parsed data dictionary
    """
    parser = ExcelParser(file_path)
    return parser.load()
