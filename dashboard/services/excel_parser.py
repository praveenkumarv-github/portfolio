"""
Excel Parser Service
Handles all Excel file parsing and data validation logic
"""
import pandas as pd
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
            
            # Calculate aggregates
            self._calculate_metrics()

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
        
        # Convert to list of dictionaries and fetch NAV
        funds = []
        total_value = 0
        
        for _, row in df.iterrows():
            identifier = str(row['Identifier']).strip()
            fund_name = str(row['FundName']).strip()
            units = float(row['Units'])
            
            # Fetch NAV
            nav, nav_source = self.nav_service.get_nav(identifier, fund_name)
            
            if nav is None:
                nav = 0
                nav_source = "Manual Input Required"
                self.warnings.append(f"NAV not available for {fund_name} ({identifier})")
            
            current_value = units * nav
            total_value += current_value
            
            funds.append({
                'fund_name': fund_name,
                'identifier': identifier,
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
    
    def _calculate_metrics(self):
        """Calculate global metrics"""
        total_investments = (
            self.data.get('mutual_funds_summary', {}).get('total_current_value', 0) +
            self.data.get('retirement_total', 0)
        )
        
        total_net_worth = (
            total_investments +
            self.data.get('liquid_total', 0) +
            self.data.get('emergency_fund_total', 0) +
            self.data.get('metals_total', 0)
        )
        
        self.data['global_metrics'] = {
            'total_net_worth': float(total_net_worth),
            'total_investments': float(total_investments),
            'total_emergency_fund': float(self.data.get('emergency_fund_total', 0)),
            'total_insurance_coverage': float(
                self.data.get('insurance_summary', {}).get('total_coverage', 0)
            ),
            'total_liquid': float(self.data.get('liquid_total', 0)),
            'total_metals': float(self.data.get('metals_total', 0)),
        }


def parse_excel_file(file_path: str) -> Dict[str, Any]:
    """
    Convenience function to parse an Excel file
    Returns the parsed data dictionary
    """
    parser = ExcelParser(file_path)
    return parser.load()
