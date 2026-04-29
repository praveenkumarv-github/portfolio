# 💰 Personal Finance Dashboard

A **local-first, privacy-focused personal finance dashboard** built with Django. Track and visualize your finances entirely on your Windows laptop—no cloud, no APIs, 100% offline.

---

## 🎯 Features

- **Excel-Driven**: Load financial data from `.xlsx` files
- **Privacy First**: All data stays on your local machine
- **Clean Dashboard**: View metrics, charts, and detailed breakdowns
- **100% Offline**: No external API calls, works without internet
- **Single-User**: No authentication required

---

## 📋 Prerequisites

- **Windows 10/11**
- **Python 3.8+** ([Download](https://www.python.org/downloads/))
- **Git** (optional, for cloning)

---

## 🚀 Setup Instructions (Windows)

### Step 1: Open Command Prompt

Press `Win + R`, type `cmd`, and press Enter.

### Step 2: Navigate to Project Directory

```cmd
cd c:\data\tools\personal\port
```

### Step 3: Create Virtual Environment

```cmd
python -m venv venv
```

### Step 4: Activate Virtual Environment

```cmd
venv\Scripts\activate
```

You should see `(venv)` at the beginning of your command prompt.

### Step 5: Install Dependencies

```cmd
pip install -r requirements.txt
```

### Step 6: Run Database Migrations

```cmd
python manage.py makemigrations
python manage.py migrate
```

### Step 7: Generate Sample Excel File

```cmd
python generate_sample_excel.py
```

This creates `sample_finance_data.xlsx` with mock financial data.

### Step 8: Create Media Directory

```cmd
mkdir media
```

### Step 9: Start the Development Server

```cmd
python manage.py runserver
```

### Step 10: Open Dashboard in Browser

Open your browser and navigate to:

```
http://127.0.0.1:8000
```

---

## 📂 Project Structure

```
finance_dashboard/
│
├── manage.py                      # Django management script
├── requirements.txt               # Python dependencies
├── generate_sample_excel.py       # Sample data generator
├── sample_finance_data.xlsx       # Generated sample file
│
├── finance_dashboard/             # Main project config
│   ├── __init__.py
│   ├── settings.py               # Django settings
│   ├── urls.py                   # Project URLs
│   ├── wsgi.py
│   └── asgi.py
│
├── dashboard/                     # Main app
│   ├── __init__.py
│   ├── models.py                 # Database models
│   ├── views.py                  # View logic
│   ├── urls.py                   # App URLs
│   ├── admin.py                  # Admin config
│   │
│   ├── services/                 # Business logic layer
│   │   ├── __init__.py
│   │   └── excel_parser.py      # Excel parsing logic
│   │
│   └── templates/
│       └── dashboard/
│           └── dashboard.html    # Main dashboard template
│
└── media/                        # Uploaded Excel files (created at runtime)
```

---

## 📊 Excel File Format

Your Excel file must have the following sheets and columns:

### Sheet: `MutualFunds`
| Date       | FundName              | InvestedAmount | CurrentValue | Units   |
|------------|-----------------------|----------------|--------------|---------|
| 2024-01-01 | HDFC Equity Fund      | 50000          | 62000        | 2500.50 |

### Sheet: `Retirement`
| Type | Amount |
|------|--------|
| PF   | 350000 |
| NPS  | 180000 |

### Sheet: `Liquid`
| Source         | Amount |
|----------------|--------|
| Savings Bank   | 150000 |
| Cash           | 15000  |

### Sheet: `EmergencyFund`
| Type | Amount |
|------|--------|
| RD   | 75000  |
| FD   | 150000 |

### Sheet: `Insurance`
| Type   | Provider     | Premium | Coverage  |
|--------|--------------|---------|-----------|
| Health | Star Health  | 25000   | 500000    |
| Term   | LIC          | 18000   | 10000000  |

---

## 🖥️ Usage

1. **Upload Excel File**
   - Click "Choose File" button
   - Select your `.xlsx` file
   - Click "Upload & Load Data"

2. **View Dashboard**
   - See global metrics at the top
   - Scroll to view charts and detailed tables
   - All calculations update automatically

3. **Reload Data**
   - Click "Reload Data" to refresh the dashboard
   - Or upload a new file to replace existing data

---

## 📈 Dashboard Features

### Global Metrics
- Total Net Worth
- Total Investments
- Emergency Fund Total
- Insurance Coverage

### Mutual Funds
- Individual fund performance
- Total invested vs current value
- Gain/Loss calculations (absolute & percentage)

### Charts
- **Pie Chart**: Asset allocation across categories
- **Bar Chart**: Mutual fund performance comparison

### Detailed Tables
- Retirement accounts breakdown
- Liquid assets listing
- Emergency fund allocation
- Insurance policies overview
- Complete mutual funds details

---

## 🔧 Troubleshooting

### Port Already in Use
If you see "port is already in use":
```cmd
python manage.py runserver 8001
```
Then visit `http://127.0.0.1:8001`

### Virtual Environment Not Activating
Make sure you're in the project directory:
```cmd
cd c:\data\tools\personal\port
venv\Scripts\activate
```

### Excel File Not Loading
Check that your Excel file has all required sheets and columns exactly as specified.

### Module Not Found Error
Reinstall dependencies:
```cmd
pip install -r requirements.txt --force-reinstall
```

---

## 🔐 Privacy & Security

- ✅ All data stays on your laptop
- ✅ No external API calls
- ✅ No cloud uploads
- ✅ No authentication required (single-user)
- ✅ No telemetry or tracking

---

## 🛠️ Tech Stack

- **Backend**: Django 5.0.4
- **Data Processing**: pandas, openpyxl
- **Frontend**: HTML, CSS (vanilla)
- **Charts**: Chart.js (CDN)
- **Database**: SQLite (file path caching only)

---

## 📝 Development Notes

### Adding New Sheets

1. Update `REQUIRED_SHEETS` in `dashboard/services/excel_parser.py`
2. Add parsing method (e.g., `_parse_new_sheet()`)
3. Update `_calculate_metrics()` if needed
4. Add UI section in `dashboard.html`

### Modifying Dashboard Layout

Edit `dashboard/templates/dashboard/dashboard.html`. The CSS is inline for simplicity.

### Changing Currency

Find and replace `₹` with your currency symbol in `dashboard.html`.

---

## 🎯 Roadmap (Optional Enhancements)

- [ ] CSV import fallback
- [ ] Export to PDF
- [ ] Multiple file comparison
- [ ] Historical data tracking
- [ ] Budget vs actual analysis
- [ ] Custom categories

---

## 📄 License

MIT License - Use freely for personal projects.

---

## 🙏 Credits

Built with Django, pandas, and Chart.js.

---

## 🆘 Support

For issues or questions:
1. Check the Troubleshooting section
2. Verify Excel file format
3. Ensure all dependencies are installed

---

**Made with ❤️ for privacy-conscious personal finance tracking**
