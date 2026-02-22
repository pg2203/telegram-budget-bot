# 💰 Telegram Budget Bot — Setup Guide

A Telegram bot that logs your expenses directly into Google Sheets.

---

## How it works

You message your bot → it parses the expense → appends a row to your Google Sheet.

**Supported formats:**
- `/add Food 25.50 lunch with team`
- `Coffee 4.50`
- `45 Groceries weekly shop`
- `/summary` — shows totals by category

**Sheet columns:** Date | Category | Amount | Description/Notes

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
3. Give it any name (e.g. "budget-bot")
4. Click **Done** (no roles needed)
5. Click on the service account → **Keys tab → Add Key → JSON**
6. Download the JSON file → rename it to **`credentials.json`**
7. Place `credentials.json` in the same folder as `bot.py`

### 2d. Share your Google Sheet
1. Create a new Google Sheet (e.g. named `Budget 2025`)
2. Open `credentials.json` and copy the `client_email` value
3. In your Sheet, click **Share** and share with that email (Editor access)

---

## Step 3 — Deploy to Render (free)

### 3a. Push code to GitHub
```bash
cd telegram-budget-bot
git init
git add .
git commit -m "Initial commit"
# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/telegram-budget-bot.git
git push -u origin main
```

> ⚠️ Make sure `credentials.json` is in `.gitignore` (it already is).
> You'll upload it to Render separately.

### 3b. Create a Render Web Service
1. Go to https://render.com and sign up (free)
2. Click **New → Background Worker**
3. Connect your GitHub repo
4. Set **Build Command:** `pip install -r requirements.txt`
5. Set **Start Command:** `python bot.py`

### 3c. Add Environment Variables in Render dashboard
| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Your token from BotFather |
| `GOOGLE_SHEET_NAME` | Exact name of your Google Sheet |

### 3d. Upload credentials.json as a Secret File
1. In Render → your service → **Environment** tab
2. Under **Secret Files**, add a file:
   - Filename: `credentials.json`
   - Contents: paste the full contents of your `credentials.json`

### 3e. Deploy!
Click **Deploy** — Render will build and start your bot.

---

## Testing

Open Telegram, find your bot, and try:
```
/start
Coffee 4.50
/add Groceries 67.30 weekly shop
/summary
```

Check your Google Sheet — rows should appear instantly! ✅

---

## Local testing (optional)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your_token_here"
export GOOGLE_SHEET_NAME="Budget 2025"
python bot.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot doesn't respond | Check Render logs for errors |
| Sheet not found | Make sure `GOOGLE_SHEET_NAME` matches exactly |
| Permission denied | Re-share the Sheet with the service account email |
| credentials.json not found | Add it as a Secret File in Render |
