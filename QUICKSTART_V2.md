# 💰 FINANCIAL COCKPIT v2.0 - QUICK START

## 🚀 What's New

### Major Features
1. **Single-Page Cockpit** - Everything visible in one screen
2. **Metals Tracking** - Gold & Silver with auto-pricing
3. **Smart NAV Fetching** - Auto-fetch mutual fund NAV using AMFI codes
4. **Enhanced Accounts** - Multiple bank accounts, RD/FD with maturity dates
5. **Dark Theme** - Professional cockpit-style interface

---

## 📝 Quick Setup

### 1. Install Dependencies
```cmd
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Generate Sample Data
```cmd
python generate_sample_excel.py
```

### 3. Start Server
```cmd
python manage.py runserver
```

### 4. Open Browser
```
http://127.0.0.1:8000
```

### 5. Upload Sample File
Click "Choose File" → Select `sample_finance_data.xlsx` → Click "Upload & Load"

---

## 📊 New Excel Format

### MutualFunds
```
FundName | Units | Identifier
```
- Identifier = AMFI code (e.g., 120503)
- NAV fetched automatically

### Liquid
```
AccountName | Type | Amount
```
- Multiple bank accounts supported

### EmergencyFund
```
AccountName | Type | Amount | MaturityDate
```
- Maturity dates tracked

### Metals (NEW)
```
Type | Quantity
```
- Gold, Silver in grams
- Prices auto-fetched or manual input

---

## ⚡ Key Changes

### Removed from MutualFunds
- ❌ Date
- ❌ InvestedAmount
- ❌ CurrentValue
→ System calculates using Units × NAV

### Added Features
- ✅ NAV auto-fetch with caching
- ✅ Metal price tracking
- ✅ Account-level tracking for liquid/emergency
- ✅ Maturity date tracking
- ✅ Fallback for offline mode

---

## 🎨 New UI

- **Dark theme** cockpit design
- **Summary table** at top
- **Asset allocation** pie chart
- **Detail sections** in grid layout
- **Badge indicators** for data sources

---

## 🔧 Manual Price Input

### If NAV not available:
Edit `cache/nav_cache.json`:
```json
{
  "120503": {
    "nav": 750.50,
    "date": "2026-04-29",
    "timestamp": "2026-04-29T23:00:00",
    "fund_name": "HDFC Top 100",
    "manual": true
  }
}
```

### If metal prices not available:
Edit `cache/metal_cache.json`:
```json
{
  "gold": {
    "price": 6500,
    "date": "2026-04-29",
    "timestamp": "2026-04-29T23:00:00",
    "manual": true
  },
  "silver": {
    "price": 80,
    "date": "2026-04-29",
    "timestamp": "2026-04-29T23:00:00",
    "manual": true
  }
}
```

---

## ✅ Verification Checklist

After starting the server:

- [ ] Summary table loads with all categories
- [ ] Mutual funds show NAV badges
- [ ] Metals section appears
- [ ] Asset allocation shows 5 categories
- [ ] Emergency fund shows maturity dates
- [ ] Liquid accounts show account names
- [ ] Dark theme applied
- [ ] No console errors

---

## 🆘 Troubleshooting

### NAV not fetching
- Check internet connection
- Verify AMFI codes are correct
- Check `cache/nav_cache.json` for cached values

### Metals showing 0 value
- Manual input required
- Edit `cache/metal_cache.json` with prices

### Template errors
- Restart server: `Ctrl+C` then `python manage.py runserver`

### Cache issues
- Delete `cache/` folder to reset

---

## 📚 Documentation

- **UPGRADE_NOTES.md** - Detailed upgrade documentation
- **README.md** - Original setup guide
- **QUICKSTART.md** - This file

---

**🎉 Upgrade complete - Happy tracking! 🎉**
