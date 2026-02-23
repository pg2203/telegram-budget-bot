# 💰 Telegram Budget Bot

A Telegram bot that logs your expenses into your **Monthly_Budget_2025** Google Sheet and lets you query summaries by month.

---

## How it works

- Message your bot to log a transaction → it appends a row to the **Transactions Log** sheet
- Use `/summary` to pull computed totals directly from the **Budget** sheet (respects your SUMIFS formulas)
- The bot writes the month/year into cells C14/C15 to trigger Google Sheets recalculation, then reads back the results

---

## Commands

### Logging transactions

| Format | Example |
|--------|---------|
| Guided flow | `/add` |
| Free text | `Groceries 45.50` or `Dining out 32` |

**`/add` — guided step-by-step (5 steps):**
1. Choose type: Income / Fixed Expenses / Variable Expenses / Savings / Debts
2. Choose category (e.g. Groceries, Internet, Karate...)
3. Enter amount (e.g. `45.50`)
4. Enter details/notes (or `-` to skip)
5. Enter date — tap **Today** / **Yesterday**, or type:
   - `22/02` — 22 Feb of current year
   - `22/02/2025` — specific date
   - `2025-02-22` — ISO format

### Summary

| Command | Result |
|---------|--------|
| `/summary` | Current month, short view |
| `/summary full` | Current month, full category breakdown |
| `/summary compare` | Current month vs previous month |
| `/summary full compare` | Full breakdown with month-over-month comparison |
| `/summary 2025 11` | November 2025, short |
| `/summary 2025 11 full` | November 2025, full breakdown |
| `/summary Nov 2025 compare` | November 2025 vs October 2025 |

**Short summary shows:**
- Each type total (Income, Fixed Expenses, Variable Expenses, Savings, Debts)
- Total Expenses (all types except Income)
- Balance (only shown when Income > $0)
- 🔺 / 🔻 arrows when using `compare`

### Other commands

| Command | Description |
|---------|-------------|
| `/categories` | List all available categories |
| `/cancel` | Cancel the current `/add` flow |
| `/help` | Show help message |

---

## Sheet structure expected

Your Google Sheet should have:
- **Transactions Log** worksheet with header row: `DATE | TYPE | CATEGORY | AMOUNT | DETAILS`
- **Budget** worksheet with month selector in `C14` (month name) and `C15` (year)
- **Setup** worksheet listing categories under Income / Fixed Expenses / Variable Expenses / Savings / Debts

---

## Step 1 — Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy your **Bot Token** (looks like `123456789:ABCdef...`)

---

## Step 2 — Set up Google Sheets API

### 2a. Create a Google Cloud project
1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "Budget Bot")

### 2b. Enable APIs
1. Go to **APIs & Services → Library**
2. Enable **Google Sheets API**
3. Enable **Google Drive API**

### 2c. Create a Service Account
1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Give it any name (e.g. "budget-bot"), click **Done**
4. Click on the service account → **Keys tab → Add Key → JSON**
5. Download the JSON file → save it as **`credentials.json`**

### 2d. Share your Google Sheet
1. Open `credentials.json` and copy the `client_email` value
2. In your Google Sheet, click **Share** and share with that email (Editor access)

---

## Step 3 — Deploy to Railway (free)

Railway gives $5 free credit/month. This bot uses ~$0.50/month — effectively free.

### 3a. Push code to GitHub
```bash
cd telegram-budget-bot
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/telegram-budget-bot.git
git push -u origin main
```

> ⚠️ `credentials.json` is in `.gitignore` — never commit it. Use the env var instead (see below).

### 3b. Create a Railway project
1. Go to https://railway.app and sign up with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select your `telegram-budget-bot` repo
4. Railway auto-detects Python and deploys automatically

### 3c. Add environment variables
In Railway → your service → **Variables** tab, add:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Your token from BotFather |
| `GOOGLE_SHEET_NAME` | Exact name of your Google Sheet |
| `CREDENTIALS_JSON` | Contents of credentials.json (see below) |

**To get a safe single-line value for `CREDENTIALS_JSON`, run this locally:**
```bash
cat credentials.json | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)))"
```
Paste the output as the value — no wrapping quotes needed.

---

## Local development

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your_token_here"
export GOOGLE_SHEET_NAME="Monthly_Budget_2025"
# credentials.json must be in the same folder
python bot.py
```

> ⚠️ **Before running locally**, suspend your Railway deployment to avoid conflicts.
> Two instances polling Telegram at the same time causes a 409 Conflict error.
>
> Railway dashboard → your service → **Settings → Suspend**
> Resume it when you're done testing locally.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `409 Conflict` error | Another instance is running — suspend Railway before running locally |
| Bot doesn't respond | Check Railway logs for errors |
| Sheet not found | `GOOGLE_SHEET_NAME` must match exactly (case-sensitive) |
| Permission denied on sheet | Re-share the Sheet with the service account `client_email` |
| `JSONDecodeError` on credentials | Re-generate `CREDENTIALS_JSON` using the python command above |
| Summary shows $0 for all | Check that C14/C15 cells in the Budget sheet are not protected |
| `No transactions found` | Dates in Transactions Log must be in `YYYY-MM-DD` format |
