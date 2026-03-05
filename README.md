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
- 🔺 / 🔻 arrows when using `compare` (hidden if difference is $0)

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

## Step 3 — Deploy to Oracle Cloud (free forever)

### 3a. Create Oracle Cloud account
1. Sign up at https://cloud.oracle.com/free
2. Create a VM instance — shape: **VM.Standard.E2.1.Micro** (Always Free)
3. OS: Ubuntu 20.04, generate and download SSH key

### 3b. SSH into your VM
```bash
chmod 400 ~/Downloads/ssh-key.key
ssh -i ~/Downloads/ssh-key.key ubuntu@YOUR_VM_IP
```

### 3c. Set up the bot on the VM
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git
git clone https://github.com/YOUR_USERNAME/telegram-budget-bot.git
cd telegram-budget-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3d. Copy credentials to the VM
On your **local Mac**:
```bash
scp -i ~/Downloads/ssh-key.key credentials.json ubuntu@YOUR_VM_IP:/home/ubuntu/telegram-budget-bot/credentials.json
```

### 3e. Install the systemd service
```bash
sudo cp telegram-budget-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/telegram-budget-bot.service
# Fill in TELEGRAM_BOT_TOKEN, GOOGLE_SHEET_NAME, and TZ values
sudo systemctl daemon-reload
sudo systemctl enable telegram-budget-bot
sudo systemctl start telegram-budget-bot
sudo systemctl status telegram-budget-bot
```

---

## Step 4 — Auto-deploy on GitHub push (optional)

Every push to `main` automatically pulls and restarts the bot on Oracle.

### 4a. Generate deploy SSH key on the VM
```bash
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions -N ""
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/github_actions  # copy this private key
```

### 4b. Add GitHub secrets
Go to your repo → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|-------|
| `ORACLE_HOST` | Your VM public IP |
| `ORACLE_SSH_KEY` | Private key from above |

### 4c. Allow passwordless restart
On the VM:
```bash
echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart telegram-budget-bot" | sudo tee /etc/sudoers.d/bot
```

Now every `git push origin main` deploys automatically.

---

## Local development

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your_token_here"
export GOOGLE_SHEET_NAME="Monthly_Budget_2025"
# credentials.json must be in the same folder
python bot.py
```

> ⚠️ Suspend the Oracle VM service before running locally to avoid conflicts:
> `sudo systemctl stop telegram-budget-bot`
> Resume with: `sudo systemctl start telegram-budget-bot`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `409 Conflict` error | Another instance is running — stop Oracle service before running locally |
| Bot doesn't respond | Check logs: `sudo journalctl -u telegram-budget-bot -n 50 --no-pager` |
| Sheet not found | `GOOGLE_SHEET_NAME` must match exactly (case-sensitive) |
| Permission denied on sheet | Re-share the Sheet with the service account `client_email` |
| Summary shows $0 for all | Check that C14/C15 cells in the Budget sheet are not protected |
| `No transactions found` | Dates in Transactions Log must be in `YYYY-MM-DD` format |
| Wrong date/timezone | Set `TZ=America/Toronto` in the systemd service file |
