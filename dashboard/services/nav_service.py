"""
NAV and Price Service
Fetches NAV for mutual funds and metal prices with fallback support
"""
import requests
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import json
import os


class NAVService:
    """Service to fetch NAV and metal prices with caching and fallback"""
    
    # Cache file paths
    CACHE_DIR = 'cache'
    NAV_CACHE_FILE = os.path.join(CACHE_DIR, 'nav_cache.json')
    METAL_CACHE_FILE = os.path.join(CACHE_DIR, 'metal_cache.json')
    
    # Cache expiry (24 hours)
    CACHE_EXPIRY_HOURS = 24
    
    def __init__(self):
        """Initialize NAV service and ensure cache directory exists"""
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        self.nav_cache = self._load_cache(self.NAV_CACHE_FILE)
        self.metal_cache = self._load_cache(self.METAL_CACHE_FILE)
    
    def _load_cache(self, file_path: str) -> Dict:
        """Load cache from file"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_cache(self, file_path: str, data: Dict):
        """Save cache to file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _is_cache_valid(self, cached_data: Dict) -> bool:
        """Check if cached data is still valid"""
        if not cached_data or 'timestamp' not in cached_data:
            return False
        
        cached_time = datetime.fromisoformat(cached_data['timestamp'])
        age = datetime.now() - cached_time
        return age.total_seconds() < (self.CACHE_EXPIRY_HOURS * 3600)
    
    def get_nav(self, identifier: str, fund_name: str = "") -> Tuple[Optional[float], str]:
        """
        Get NAV for a mutual fund by ISIN, AMFI code, or scheme code
        Returns: (nav_value, source)
        """
        # Check cache first
        cache_key = identifier.strip().upper()
        if cache_key in self.nav_cache:
            cached = self.nav_cache[cache_key]
            if self._is_cache_valid(cached):
                return cached.get('nav'), f"Cached ({cached.get('date', 'N/A')})"
        
        # Try to fetch from MFAPI (India mutual fund API)
        nav, source = self._fetch_nav_from_mfapi(identifier)
        
        if nav:
            # Cache the result
            self.nav_cache[cache_key] = {
                'nav': nav,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat(),
                'fund_name': fund_name,
            }
            self._save_cache(self.NAV_CACHE_FILE, self.nav_cache)
            return nav, source
        
        # Fallback to cached value even if expired
        if cache_key in self.nav_cache:
            cached = self.nav_cache[cache_key]
            return cached.get('nav'), f"Cached (Offline - {cached.get('date', 'N/A')})"
        
        return None, "Not Available"
    
    def _fetch_nav_from_mfapi(self, identifier: str) -> Tuple[Optional[float], str]:
        """
        Fetch NAV from MFAPI (free India mutual fund API)
        Supports AMFI codes
        """
        try:
            # MFAPI uses AMFI code in URL
            # Format: https://api.mfapi.in/mf/{amfi_code}
            
            # Clean identifier
            amfi_code = identifier.strip()
            
            # Try to extract numeric code if it's ISIN
            if len(amfi_code) == 12 and amfi_code.startswith('INF'):
                # ISIN format - we can't directly convert, return None
                # User should provide AMFI code
                return None, "ISIN not supported, use AMFI code"
            
            # Make API request
            url = f"https://api.mfapi.in/mf/{amfi_code}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and len(data['data']) > 0:
                    latest = data['data'][0]
                    nav = float(latest['nav'])
                    date = latest['date']
                    return nav, f"MFAPI ({date})"
        except requests.Timeout:
            return None, "API Timeout"
        except requests.RequestException:
            return None, "API Error"
        except (ValueError, KeyError):
            return None, "Invalid Response"
        except Exception as e:
            return None, f"Error: {str(e)}"
        
        return None, "Not Found"
    
    def get_metal_prices(self) -> Dict[str, Tuple[Optional[float], str]]:
        """
        Get current metal prices (Gold and Silver) per gram in INR
        Returns: {'gold': (price, source), 'silver': (price, source)}
        """
        results = {}
        
        # Check cache
        for metal in ['gold', 'silver']:
            if metal in self.metal_cache and self._is_cache_valid(self.metal_cache[metal]):
                cached = self.metal_cache[metal]
                results[metal] = (cached.get('price'), f"Cached ({cached.get('date', 'N/A')})")
                continue
            
            # Try to fetch live prices
            price, source = self._fetch_metal_price(metal)
            
            if price:
                # Cache the result
                self.metal_cache[metal] = {
                    'price': price,
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'timestamp': datetime.now().isoformat(),
                }
                self._save_cache(self.METAL_CACHE_FILE, self.metal_cache)
                results[metal] = (price, source)
            else:
                # Fallback to cached even if expired
                if metal in self.metal_cache:
                    cached = self.metal_cache[metal]
                    results[metal] = (cached.get('price'), f"Cached (Offline - {cached.get('date', 'N/A')})")
                else:
                    results[metal] = (None, "Not Available")
        
        return results
    
    def _fetch_metal_price(self, metal: str) -> Tuple[Optional[float], str]:
        """
        Fetch current metal price per gram in INR
        Note: This is a placeholder - real implementation would use actual API
        For now, returns None to trigger manual input
        """
        # Real implementation would use:
        # - GoodReturns API
        # - BankBazaar API
        # - Or scrape from reliable source
        
        # For now, return None to allow manual input
        return None, "Manual Input Required"
    
    def set_manual_nav(self, identifier: str, nav: float, fund_name: str = ""):
        """Manually set NAV for a fund (useful when offline)"""
        cache_key = identifier.strip().upper()
        self.nav_cache[cache_key] = {
            'nav': nav,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.now().isoformat(),
            'fund_name': fund_name,
            'manual': True,
        }
        self._save_cache(self.NAV_CACHE_FILE, self.nav_cache)
    
    def set_manual_metal_price(self, metal: str, price: float):
        """Manually set metal price (useful when offline)"""
        self.metal_cache[metal.lower()] = {
            'price': price,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.now().isoformat(),
            'manual': True,
        }
        self._save_cache(self.METAL_CACHE_FILE, self.metal_cache)
    
    def clear_cache(self):
        """Clear all cached data"""
        self.nav_cache = {}
        self.metal_cache = {}
        self._save_cache(self.NAV_CACHE_FILE, {})
        self._save_cache(self.METAL_CACHE_FILE, {})


# Singleton instance
_nav_service = None


def get_nav_service() -> NAVService:
    """Get or create NAV service singleton"""
    global _nav_service
    if _nav_service is None:
        _nav_service = NAVService()
    return _nav_service
