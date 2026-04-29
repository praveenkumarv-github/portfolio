# Quick Start Guide

## 🚀 Start the Dashboard in 3 Steps

### 1️⃣ Activate Virtual Environment
```cmd
venv\Scripts\activate
```

### 2️⃣ Start Server
```cmd
python manage.py runserver
```

### 3️⃣ Open Browser
Navigate to: http://127.0.0.1:8000

---

## 📂 Upload Sample Data

1. Click "Choose File"
2. Select `sample_finance_data.xlsx`
3. Click "Upload & Load Data"
4. View your dashboard!

---

## 🛑 Stop Server
Press `Ctrl + C` in the terminal

---

## 📝 Edit Your Data

1. Open `sample_finance_data.xlsx` in Excel
2. Edit the data (follow the sheet structure)
3. Save the file
4. Upload it again in the dashboard

---

## 🔄 Common Commands

### Create new migrations
```cmd
python manage.py makemigrations
```

### Apply migrations
```cmd
python manage.py migrate
```

### Regenerate sample data
```cmd
python generate_sample_excel.py
```

---

## 📊 Excel File Sheets Required

1. **MutualFunds** - Your mutual fund investments
2. **Retirement** - PF/NPS accounts
3. **Liquid** - Bank accounts and cash
4. **EmergencyFund** - Emergency savings
5. **Insurance** - Insurance policies

---

**Need help?** Check the full README.md
