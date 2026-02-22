import os
import re
import logging
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes
)
import json
import gspread
from google.oauth2.service_account import Credentials

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Your sheet's categories (from Setup sheet) ────────────────────────────────
CATEGORIES = {
    "Income": ["Salary", "Rent"],
    "Fixed Expenses": [
        "Condo Maintenance", "Home insurance", "Property Tax Scarborough",
        "Property Tax Oakville", "Water Heater Oakville", "Internet",
        "Praveen Mobile", "Mrudula Mobile", "Car insurance",
        "Swimming", "Karate", "English Tuition", "Math Tuition",
        "Music", "School Fee",
    ],
    "Variable Expenses": [
        "Groceries", "Car Charging", "Condo Hydro", "Dining out",
        "Clothing", "Medications", "School supplies", "Car maintenance",
        "Entertainment", "Gifts", "Salon services", "Donations",
        "Home repairs", "Travel", "Other Activity",
    ],
    "Savings": ["RRSP Praveen", "RRSP Mrudula", "RESP", "India Transfers"],
    "Debts": ["Oakville Mortgage", "Scarborough Mortgage"],
}

CATEGORY_TO_TYPE = {
    cat: type_
    for type_, cats in CATEGORIES.items()
    for cat in cats
}
ALL_CATEGORIES = list(CATEGORY_TO_TYPE.keys())
TYPES = list(CATEGORIES.keys())

CHOOSE_TYPE, CHOOSE_CATEGORY, ENTER_AMOUNT, ENTER_DETAILS, ENTER_DATE = range(5)

# ── Google Sheets ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def load_credentials():
    """Load Google credentials from env var (Railway/cloud) or file (local)."""
    creds_json = os.environ.get("CREDENTIALS_JSON")
    if creds_json:
        logger.info("🔐 Loading credentials from CREDENTIALS_JSON env var...")
        info = json.loads(creds_json)
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        logger.info("🔐 Loading credentials from credentials.json file...")
        return Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
WORKSHEET_NAME = "Transactions Log"
HEADER_ROW = 4

def get_sheet():
    creds = load_credentials()
    logger.info(f"✅ Credentials loaded. Service account: {creds.service_account_email}")

    logger.info("🔗 Authorizing gspread client...")
    client = gspread.authorize(creds)
    logger.info(f"✅ gspread authorized. Version: {gspread.__version__}")

    sheet_name = os.environ["GOOGLE_SHEET_NAME"]
    logger.info(f"📂 Opening workbook: '{sheet_name}'")
    wb = client.open(sheet_name)
    logger.info(f"✅ Workbook opened. Available sheets: {[ws.title for ws in wb.worksheets()]}")

    logger.info(f"📋 Opening worksheet: '{WORKSHEET_NAME}'")
    ws = wb.worksheet(WORKSHEET_NAME)
    logger.info(f"✅ Worksheet opened: '{ws.title}' (id={ws.id}, rows={ws.row_count})")
    return ws

def _read_rows(sheet):
    """Read rows using the raw Sheets API — works in gspread 5.x and 6.x."""
    range_notation = f"'{sheet.title}'!A1:E1000"
    logger.info(f"📖 Reading sheet rows via values_get('{range_notation}')...")
    result = sheet.spreadsheet.values_get(range_notation)
    logger.info(f"✅ values_get() keys: {list(result.keys())}")
    rows = result.get("values", [])
    logger.info(f"✅ Rows returned: {len(rows)}")
    return rows

def append_transaction(date, type_, category, amount, details):
    logger.info(f"💾 append_transaction: date={date}, type={type_}, cat={category}, amt={amount}")
    sheet = get_sheet()
    all_rows = _read_rows(sheet)
    logger.info(f"📊 Total rows read: {len(all_rows)}")

    next_row = len(all_rows) + 1
    for i in range(4, len(all_rows)):
        if not any(str(cell).strip() for cell in all_rows[i]):
            next_row = i + 1
            break
    logger.info(f"📍 Writing to row {next_row}")

    row_data = [date, type_, category, float(amount), details]
    logger.info(f"📝 Row data: {row_data}")
    result = sheet.update(
        values=[row_data],
        range_name=f"A{next_row}:E{next_row}",
        value_input_option="USER_ENTERED"
    )
    logger.info(f"📤 sheet.update() result type={type(result).__name__}, value={result}")
    if isinstance(result, dict):
        updated = result.get("updatedCells", result.get("updated_cells", 0))
        logger.info(f"✅ Updated cells: {updated}")
        if updated == 0:
            raise RuntimeError(f"Sheet update wrote 0 cells: {result}")
    else:
        logger.warning(f"⚠️  Unexpected result type from sheet.update(): {type(result)} — {result}")

def get_budget_sheet():
    """Open the Budget worksheet."""
    logger.info("🔐 Loading credentials for Budget sheet...")
    creds = load_credentials()
    client = gspread.authorize(creds)
    wb = client.open(os.environ["GOOGLE_SHEET_NAME"])
    ws = wb.worksheet("Budget")
    logger.info(f"✅ Budget sheet opened: {ws.title}")
    return ws

def get_summary(year: int, month: int, detailed: bool = False, compare: bool = False):
    import time
    month_name_full = datetime(year, month, 1).strftime("%B")
    month_label = datetime(year, month, 1).strftime("%B %Y")
    logger.info(f"📊 get_summary() for {month_label}, detailed={detailed}, compare={compare}")

    ws = get_budget_sheet()

    def parse_amt(val):
        try:
            return float(str(val).replace(",", "").replace("$", "").strip())
        except:
            return 0.0

    def fmt(val):
        """Format currency: drop .00, keep .50 etc."""
        if val == int(val):
            return f"{int(val):,}"
        return f"{val:,.2f}"

    SKIP = {"DESCRIPTION", "TOTAL", "SUMMARY", "TYPE", "PLANNED", "ACTUAL", ""}

    def fetch_actuals(y, m):
        """Write month/year to Budget sheet, wait, then read all actuals."""
        mn = datetime(y, m, 1).strftime("%B")
        logger.info(f"✏️  Fetching actuals for {mn} {y}")
        ws.update(values=[[mn]], range_name="C14")
        ws.update(values=[[y]], range_name="C15")
        time.sleep(3)

        summary_raw = ws.spreadsheet.values_get("'Budget'!B34:D39")
        summary_rows = summary_raw.get("values", [])

        t_actuals = {}
        bal = 0.0
        for r in summary_rows:
            if not r:
                continue
            label = str(r[0]).strip()
            actual = parse_amt(r[2]) if len(r) > 2 else 0.0
            if label == "TOTAL":
                bal = actual
            elif label in TYPES:
                t_actuals[label] = actual

        def read_cat_block(range_str):
            raw = ws.spreadsheet.values_get(f"'Budget'!{range_str}")
            rows = raw.get("values", [])
            result = {}
            for r in rows:
                desc = str(r[0]).strip() if len(r) > 0 else ""
                amt_raw = str(r[2]).strip() if len(r) > 2 else ""
                if desc.upper() not in SKIP and desc:
                    result[desc] = parse_amt(amt_raw)
            return result

        cat_actuals = {}
        cat_actuals.update(read_cat_block("B19:D30"))
        cat_actuals.update(read_cat_block("F19:H39"))
        cat_actuals.update(read_cat_block("J19:L39"))
        cat_actuals.update(read_cat_block("N19:P27"))
        cat_actuals.update(read_cat_block("N31:P39"))

        return t_actuals, bal, cat_actuals

    # Fetch current month
    type_actuals, balance, cat_actuals = fetch_actuals(year, month)
    logger.info(f"📊 Type actuals: {type_actuals}, balance: {balance}")

    # Fetch previous month if compare requested
    prev_type_actuals = {}
    prev_cat_actuals = {}
    if compare:
        from datetime import timedelta
        first_of_month = datetime(year, month, 1)
        prev_month_last = first_of_month - timedelta(days=1)
        prev_y, prev_m = prev_month_last.year, prev_month_last.month
        prev_label = datetime(prev_y, prev_m, 1).strftime("%B %Y")
        logger.info(f"📊 Fetching previous month: {prev_label}")
        prev_type_actuals, _, prev_cat_actuals = fetch_actuals(prev_y, prev_m)
        # Restore current month in sheet
        ws.update(values=[[month_name_full]], range_name="C14")
        ws.update(values=[[year]], range_name="C15")

    # Short summary
    if not detailed:
        expense_types = ["Fixed Expenses", "Variable Expenses", "Savings", "Debts"]
        total_expenses = sum(type_actuals.get(t, 0.0) for t in expense_types)
        income = type_actuals.get("Income", 0.0)

        def diff_str(curr, prev):
            if prev == 0:
                return ""
            d = curr - prev
            arrow = "🔺" if d > 0 else "🔻"
            return f" {arrow} ${fmt(abs(d))}"

        lines = [f"📊 *{month_label}*\n"]
        for t in TYPES:
            amt = type_actuals.get(t, 0.0)
            suffix = diff_str(amt, prev_type_actuals.get(t, 0.0)) if compare else ""
            lines.append(f"{t}: *${fmt(amt)}*{suffix}")

        prev_total_exp = sum(prev_type_actuals.get(t, 0.0) for t in expense_types)
        exp_suffix = diff_str(total_expenses, prev_total_exp) if compare else ""
        lines.append(f"\n💸 Total Expenses: *${fmt(total_expenses)}*{exp_suffix}")
        if income > 0:
            bal_emoji = "✅" if balance >= 0 else "⚠️"
            lines.append(f"{bal_emoji} Balance: *${fmt(balance)}*")
        if compare:
            lines.append(f"\n_🔺 higher than {prev_label} | 🔻 lower_")
        lines.append(f"\n_Use /summary full for breakdown_")
        return "\n".join(lines)

    # Detailed summary — build cat_map from already-fetched cat_actuals
    cat_map = {}
    for type_, cats in CATEGORIES.items():
        cat_map[type_] = [(c, cat_actuals.get(c, 0.0)) for c in cats]

    expense_types = ["Fixed Expenses", "Variable Expenses", "Savings", "Debts"]
    total_expenses = sum(type_actuals.get(t, 0.0) for t in expense_types)
    income = type_actuals.get("Income", 0.0)

    def diff_str(curr, prev):
        if prev == 0:
            return ""
        d = curr - prev
        arrow = "🔺" if d > 0 else "🔻"
        return f" {arrow} ${fmt(abs(d))}"

    title_suffix = f" vs {prev_label}" if compare else " — Detailed"
    lines = [f"📊 *{month_label}{title_suffix}*"]
    for t in TYPES:
        total = type_actuals.get(t, 0.0)
        type_suffix = diff_str(total, prev_type_actuals.get(t, 0.0)) if compare else ""
        lines.append(f"\n*{t}*: ${fmt(total)}{type_suffix}")
        for cat, amt in cat_map.get(t, []):
            if amt != 0 or (compare and prev_cat_actuals.get(cat, 0.0) != 0):
                cat_suffix = diff_str(amt, prev_cat_actuals.get(cat, 0.0)) if compare else ""
                lines.append(f"  • {cat}: ${fmt(amt)}{cat_suffix}")

    prev_total_exp = sum(prev_type_actuals.get(t, 0.0) for t in expense_types)
    exp_suffix = diff_str(total_expenses, prev_total_exp) if compare else ""
    lines.append(f"\n💸 *Total Expenses: ${fmt(total_expenses)}*{exp_suffix}")
    if income > 0:
        bal_emoji = "✅" if balance >= 0 else "⚠️"
        lines.append(f"{bal_emoji} *Balance: ${fmt(balance)}*")
    if compare:
        lines.append(f"\n_🔺 higher than {prev_label} | 🔻 lower_")
    logger.info("✅ Detailed summary built")
    return "\n".join(lines)


def fuzzy_match_category(text):
    text_lower = text.lower()
    for cat in ALL_CATEGORIES:
        if cat.lower() in text_lower:
            return CATEGORY_TO_TYPE[cat], cat
    return None, None

def parse_amount(text):
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", text)
    return float(m.group(1).replace(",", ".")) if m else None

# ── Commands ──────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Monthly Budget Bot*\n\n"
        "Log a transaction:\n"
        "  • `/add` — guided step-by-step with menus\n"
        "  • Free text: `Groceries 45.50` or `Dining out 32`\n\n"
        "Other commands:\n"
        "  `/summary` — current month totals\n"
        "  `/summary 2025 11` — filter by year & month\n"
        "  `/categories` — list all categories\n"
        "  `/cancel` — cancel current entry\n"
        "  `/help` — show this message"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)

async def categories_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["📋 *Available Categories*\n"]
    for type_, cats in CATEGORIES.items():
        lines.append(f"*{type_}*")
        lines.append("  " + " | ".join(cats))
        lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def summary_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Usage:
      /summary                  → current month, short
      /summary detailed         → current month, full breakdown
      /summary 2025 11          → November 2025, short
      /summary 2025 11 detailed → November 2025, full breakdown
      /summary Nov 2025         → November 2025, short
    """
    now = datetime.now()
    year, month = now.year, now.month
    detailed = False

    args = ctx.args or []

    # Check for modifier keywords
    detailed = False
    compare = False
    clean_args = []
    for a in args:
        if a.lower() in ("detailed", "full"):
            detailed = True
        elif a.lower() == "compare":
            compare = True
        else:
            clean_args.append(a)

    numbers = []
    for a in clean_args:
        for fmt in ("%b", "%B"):
            try:
                m = datetime.strptime(a.capitalize(), fmt).month
                numbers.append(("month", m))
                break
            except ValueError:
                continue
        else:
            try:
                n = int(a)
                if 2000 <= n <= 2100:
                    numbers.append(("year", n))
                elif 1 <= n <= 12:
                    numbers.append(("month_or_year", n))
            except ValueError:
                pass

    for kind, val in numbers:
        if kind == "year":
            year = val
        elif kind == "month":
            month = val
        elif kind == "month_or_year":
            has_year = any(k == "year" for k, _ in numbers)
            if has_year or val <= 12:
                month = val

    try:
        wait_msg = "⏳ Fetching summary..." if not compare else "⏳ Fetching summary + previous month..."
        await update.message.reply_text(wait_msg)
        msg = get_summary(year, month, detailed=detailed, compare=compare)
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Summary error: {e}", exc_info=True)
        await update.message.reply_text("❌ Couldn't fetch summary.")

# ── Guided /add conversation ──────────────────────────────────────────────────
def parse_date_input(text: str):
    """Parse user date input. Accepts: today, yesterday, DD/MM, DD/MM/YYYY, YYYY-MM-DD."""
    text = text.strip().lower()
    today = datetime.now()

    if text in ("today", "t"):
        return today.strftime("%Y-%m-%d")
    if text in ("yesterday", "y"):
        from datetime import timedelta
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m", "%d-%m"):
        try:
            d = datetime.strptime(text, fmt)
            # If no year provided, assume current year
            if fmt in ("%d/%m", "%d-%m"):
                d = d.replace(year=today.year)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

async def add_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().strftime("%Y-%m-%d")
    keyboard = [[t] for t in TYPES]
    await update.message.reply_text(
        "📂 *Step 1 of 5* — Choose the transaction type:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CHOOSE_TYPE

async def choose_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chosen = update.message.text.strip()
    if chosen not in CATEGORIES:
        await update.message.reply_text("Please pick one of the buttons shown.")
        return CHOOSE_TYPE
    ctx.user_data["type"] = chosen
    keyboard = [[c] for c in CATEGORIES[chosen]]
    await update.message.reply_text(
        f"🏷 *Step 2 of 5* — Choose category under _{chosen}_:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CHOOSE_CATEGORY

async def choose_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chosen = update.message.text.strip()
    type_ = ctx.user_data.get("type")
    if chosen not in CATEGORIES.get(type_, []):
        await update.message.reply_text("Please pick one of the buttons shown.")
        return CHOOSE_CATEGORY
    ctx.user_data["category"] = chosen
    await update.message.reply_text(
        "💰 *Step 3 of 5* — Enter the amount (e.g. `45.50`):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    return ENTER_AMOUNT

async def enter_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    amount = parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("❓ Enter a number, e.g. `45.50`:")
        return ENTER_AMOUNT
    ctx.user_data["amount"] = amount
    await update.message.reply_text(
        "📝 *Step 4 of 5* — Any details or notes?\n_(Send `-` to skip)_",
        parse_mode="Markdown"
    )
    return ENTER_DETAILS

async def enter_details(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    details = update.message.text.strip()
    if details == "-":
        details = ""
    ctx.user_data["details"] = details
    today = datetime.now().strftime("%Y-%m-%d")
    keyboard = [["Today"], ["Yesterday"]]
    await update.message.reply_text(
        f"📅 *Step 5 of 5* — Date for this transaction?\n"
        f"_(Tap Today/Yesterday or type: `DD/MM`, `DD/MM/YYYY`, `YYYY-MM-DD`)_",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return ENTER_DATE

async def enter_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    date = parse_date_input(update.message.text)
    if date is None:
        await update.message.reply_text(
            "❓ Couldn't parse that date. Try: `Today`, `Yesterday`, `22/02`, `22/02/2025` or `2025-02-22`:",
            reply_markup=ReplyKeyboardMarkup([["Today"], ["Yesterday"]], one_time_keyboard=True, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return ENTER_DATE

    type_ = ctx.user_data["type"]
    category = ctx.user_data["category"]
    amount = ctx.user_data["amount"]
    details = ctx.user_data["details"]
    try:
        append_transaction(date, type_, category, amount, details)
        await update.message.reply_text(
            f"✅ *Logged to Transactions Log!*\n\n"
            f"📅 {date}\n📂 {type_}\n🏷 {category}\n💰 ${amount:,.2f}\n📝 {details or '—'}",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Sheet write error: {e}")
        await update.message.reply_text("❌ Failed to write to Google Sheets.", reply_markup=ReplyKeyboardRemove())
    ctx.user_data.clear()
    return ConversationHandler.END
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Entry cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel_outside(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handles /cancel when no conversation is active."""
    await update.message.reply_text("Nothing to cancel. Use /add to log an expense.", reply_markup=ReplyKeyboardRemove())

# ── Free-text handler ─────────────────────────────────────────────────────────
async def free_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    amount = parse_amount(text)
    if amount is None:
        await update.message.reply_text(
            "❓ Couldn't parse that. Try `Groceries 45.50` or use /add for guided entry."
        )
        return
    type_, category = fuzzy_match_category(text)
    if not category:
        await update.message.reply_text(
            "❓ Couldn't match a category. Try `Groceries 45.50` or use /add.\nSend /categories to see all options."
        )
        return
    date = datetime.now().strftime("%Y-%m-%d")
    details = re.sub(r"\d+(?:[.,]\d{1,2})?", "", text).replace(category, "").strip(" -")
    try:
        append_transaction(date, type_, category, amount, details)
        await update.message.reply_text(
            f"✅ *Logged to Transactions Log!*\n\n"
            f"📅 {date}\n📂 {type_}\n🏷 {category}\n💰 ${amount:,.2f}\n📝 {details or '—'}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Sheet write error: {e}")
        await update.message.reply_text("❌ Failed to write to Google Sheets.")

# ── Main ──────────────────────────────────────────────────────────────────────
def build_app():
    """Build and return the Application with all handlers registered."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_cmd)],
        states={
            CHOOSE_TYPE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_type)],
            CHOOSE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_category)],
            ENTER_AMOUNT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_DETAILS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_details)],
            ENTER_DATE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("categories", categories_cmd))
    app.add_handler(CommandHandler("cancel", cancel_outside))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text_handler))
    return app


# ── Polling mode (local + Render) ────────────────────────────────────────────
async def run_polling(app):
    logger.info("🤖 Bot starting (polling mode)...")
    async with app:
        await app.initialize()
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.start()
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1.0,     # seconds between polls
            timeout=30,            # long-poll: hold connection 30s before retry
        )
        logger.info("✅ Bot is running. Press Ctrl+C to stop.")
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    application = build_app()
    asyncio.run(run_polling(application))
