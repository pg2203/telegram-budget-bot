import os
import re
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes
)
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

# Flat lookup: category name → type
CATEGORY_TO_TYPE = {
    cat: type_
    for type_, cats in CATEGORIES.items()
    for cat in cats
}

ALL_CATEGORIES = list(CATEGORY_TO_TYPE.keys())
TYPES = list(CATEGORIES.keys())

# Conversation states
CHOOSE_TYPE, CHOOSE_CATEGORY, ENTER_AMOUNT, ENTER_DETAILS = range(4)

# ── Google Sheets ─────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
WORKSHEET_NAME = "Transactions Log"
HEADER_ROW = 4  # Row 4 in the sheet has DATE|TYPE|CATEGORY|AMOUNT|DETAILS

def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    wb = client.open(os.environ["GOOGLE_SHEET_NAME"])
    return wb.worksheet(WORKSHEET_NAME)

def append_transaction(date: str, type_: str, category: str, amount: float, details: str):
    sheet = get_sheet()
    sheet.append_row(
        [date, type_, category, amount, details],
        value_input_option="USER_ENTERED"
    )

def get_summary():
    sheet = get_sheet()
    records = sheet.get_all_values()
    data = [r for r in records[HEADER_ROW:] if any(r)]
    if not data:
        return "No transactions logged yet."

    totals: dict[str, float] = {t: 0.0 for t in TYPES}
    for row in data:
        if len(row) < 4:
            continue
        type_ = row[1].strip()
        try:
            amount = float(str(row[3]).replace(",", "").replace("$", ""))
        except ValueError:
            continue
        if type_ in totals:
            totals[type_] += amount

    lines = ["📊 *Transactions Summary*\n"]
    for type_, total in totals.items():
        lines.append(f"  {type_}: ${total:,.2f}")
    return "\n".join(lines)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fuzzy_match_category(text: str):
    """Return (type, category) if a known category name is found in the text."""
    text_lower = text.lower()
    for cat in ALL_CATEGORIES:
        if cat.lower() in text_lower:
            return CATEGORY_TO_TYPE[cat], cat
    return None, None

def parse_amount(text: str):
    m = re.search(r"(\d+(?:[.,]\d{1,2})?)", text)
    return float(m.group(1).replace(",", ".")) if m else None

# ── Basic commands ────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Monthly Budget Bot*\n\n"
        "Log a transaction:\n"
        "  • `/add` — guided step-by-step with menus\n"
        "  • Free text: `Groceries 45.50` or `Dining out 32`\n\n"
        "Other commands:\n"
        "  `/summary` — totals by type\n"
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
    try:
        msg = get_summary()
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Summary error: {e}")
        await update.message.reply_text("❌ Couldn't fetch summary. Check logs.")

# ── Guided /add conversation ──────────────────────────────────────────────────
async def add_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[t] for t in TYPES]
    await update.message.reply_text(
        "📂 *Step 1 of 4* — Choose the transaction type:",
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
    cats = CATEGORIES[chosen]
    keyboard = [[c] for c in cats]
    await update.message.reply_text(
        f"🏷 *Step 2 of 4* — Choose category under _{chosen}_:",
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
        "💰 *Step 3 of 4* — Enter the amount (e.g. `45.50`):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    return ENTER_AMOUNT

async def enter_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    amount = parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("❓ Couldn't read that. Enter a number, e.g. `45.50`:")
        return ENTER_AMOUNT
    ctx.user_data["amount"] = amount
    await update.message.reply_text(
        "📝 *Step 4 of 4* — Any details or notes?\n_(Send `-` to skip)_",
        parse_mode="Markdown"
    )
    return ENTER_DETAILS

async def enter_details(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    details = update.message.text.strip()
    if details == "-":
        details = ""
    date = datetime.now().strftime("%Y-%m-%d")
    type_ = ctx.user_data["type"]
    category = ctx.user_data["category"]
    amount = ctx.user_data["amount"]
    try:
        append_transaction(date, type_, category, amount, details)
        await update.message.reply_text(
            f"✅ *Logged to Transactions Log!*\n\n"
            f"📅 {date}\n"
            f"📂 {type_}\n"
            f"🏷 {category}\n"
            f"💰 ${amount:,.2f}\n"
            f"📝 {details or '—'}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Sheet write error: {e}")
        await update.message.reply_text(
            "❌ Failed to write to Google Sheets. Check your credentials and sheet sharing."
        )
    ctx.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Entry cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

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
            "❓ Couldn't match a category. Try:\n"
            "`Groceries 45.50` or use /add for guided entry.\n"
            "Send /categories to see all options."
        )
        return

    date = datetime.now().strftime("%Y-%m-%d")
    details = re.sub(r"\d+(?:[.,]\d{1,2})?", "", text).replace(category, "").strip(" -")
    try:
        append_transaction(date, type_, category, amount, details)
        await update.message.reply_text(
            f"✅ *Logged to Transactions Log!*\n\n"
            f"📅 {date}\n"
            f"📂 {type_}\n"
            f"🏷 {category}\n"
            f"💰 ${amount:,.2f}\n"
            f"📝 {details or '—'}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Sheet write error: {e}")
        await update.message.reply_text("❌ Failed to write to Google Sheets.")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_cmd)],
        states={
            CHOOSE_TYPE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_type)],
            CHOOSE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_category)],
            ENTER_AMOUNT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            ENTER_DETAILS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_details)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("categories", categories_cmd))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text_handler))

    logger.info("Budget bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
