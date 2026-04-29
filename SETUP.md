# Setup Guide

## Requirements

- Python 3.10+  
- Git (optional)

---

## 1. Clone / download

```bash
git clone <repo-url>
cd port
```

---

## 2. Create virtual environment

**Git Bash / WSL / macOS / Linux:**
```bash
python -m venv venv
source venv/Scripts/activate      # Windows Git Bash
# source venv/bin/activate         # macOS / Linux / WSL
```

**Windows CMD:**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
# If blocked by execution policy:
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Run database migrations

```bash
python manage.py migrate
```

---

## 5. Start development server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000

---

## 6. Run tests

```bash
pytest tests/ -v
```

---

## 7. Prepare your Excel file

Required sheets and columns:

| Sheet | Required Columns |
|---|---|
| MutualFunds | FundName, Units, Identifier |
| Retirement | Type, Amount |
| Liquid | AccountName, Type, Amount |
| EmergencyFund | AccountName, Type, Amount, MaturityDate |
| Insurance | Type, Provider, Premium, Coverage |
| Metals | Type, Quantity |

`Identifier` in MutualFunds = AMFI numeric scheme code (e.g. `119551`) or ISIN.  
`Type` in Metals = `Gold` or `Silver`.

Use `python generate_sample_excel.py` to create a pre-filled sample file.

---

## 8. Metal prices

Prices are auto-fetched from GoodReturns (Chennai) on first load each day.  
If fetch fails → cached value is used → safe default as last resort.

To override manually: use the price form at the bottom of the Metals section on the dashboard.

---

## Directories created at runtime

| Path | Purpose |
|---|---|
| `data/metal_prices.json` | Metal price cache |
| `cache/nav_cache.json` | NAV cache |
| `media/` | Uploaded Excel files |
| `db.sqlite3` | SQLite database |
