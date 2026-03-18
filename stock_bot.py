#!/usr/bin/env python3
"""
Stock Price Tracker — Telegram Bot
Uses yfinance with history() method — reliable for NSE stocks
"""

import os
import json
import time
import logging
import schedule
import threading
import requests
import yfinance as yf
from typing import Optional, Dict, Any
from datetime import datetime, time as dtime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

try:
    from plyer import notification as desktop_notify
    DESKTOP_AVAILABLE = True
except ImportError:
    DESKTOP_AVAILABLE = False

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("stock_tracker.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

CONFIG_FILE         = "config.json"
STOCKS_FILE         = "tracked_stocks.json"
IST                 = pytz.timezone("Asia/Kolkata")
MARKET_OPEN         = dtime(9, 15)
MARKET_CLOSE        = dtime(15, 30)
CHECK_INTERVAL_MINS = 15
DAILY_SUMMARY_TIME  = "15:35"
AWAITING_EMAIL      = 1
AWAITING_PASSWORD   = 2

def load_config() -> dict:
    return json.load(open(CONFIG_FILE)) if os.path.exists(CONFIG_FILE) else {}

def save_config(cfg: dict):
    json.dump(cfg, open(CONFIG_FILE, "w"), indent=2)

def load_stocks() -> dict:
    return json.load(open(STOCKS_FILE)) if os.path.exists(STOCKS_FILE) else {}

def save_stocks(s: dict):
    json.dump(s, open(STOCKS_FILE, "w"), indent=2)

def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE

def now_ist_str() -> str:
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")

def groww_url(symbol: str) -> str:
    return f"https://groww.in/stocks/{symbol.lower()}"

# ── Stock price fetcher ───────────────────────────────────────────────────────

def fetch_stock_price(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch NSE stock price using yfinance history() method.
    history() is far more reliable than fast_info for Indian stocks.
    """
    clean  = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    yf_sym = clean + ".NS"

    try:
        ticker = yf.Ticker(yf_sym)

        # Use history — most reliable method for NSE
        hist = ticker.history(period="5d")

        if hist.empty:
            logger.warning("No history data for %s", yf_sym)
            return None

        price      = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None

        if price == 0:
            return None

        # Get company name
        company_name = clean
        try:
            info = ticker.fast_info
            company_name = getattr(info, "long_name", clean) or clean
        except Exception:
            pass

        change     = None
        change_pct = None
        if prev_close and prev_close > 0:
            change     = round(price - prev_close, 2)
            change_pct = round(((price - prev_close) / prev_close) * 100, 2)

        logger.info("Fetched %s: ₹%s (%s%%)", yf_sym, price, change_pct)
        return {
            "company_name": company_name,
            "price":        round(price, 2),
            "change":       change,
            "change_pct":   change_pct,
            "prev_close":   round(prev_close, 2) if prev_close else None,
            "url":          groww_url(clean),
            "fetched_at":   datetime.now(IST).isoformat(),
        }

    except Exception as e:
        logger.error("fetch_stock_price failed for %s: %s", yf_sym, e)
        return None

# ── Notifications ─────────────────────────────────────────────────────────────

async def tg_alert(bot, chat_id: str, text: str, url: str = None):
    kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if url:
        kwargs["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton("📈 View on Groww", url=url)]])
    await bot.send_message(**kwargs)

def email_alert(cfg: dict, subject: str, html: str):
    if not cfg.get("email_enabled"):
        return
    try:
        api_key   = cfg.get("resend_api_key")
        recipient = cfg.get("email_recipient")
        if not api_key or not recipient:
            return
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": "Stock Tracker <onboarding@resend.dev>", "to": [recipient], "subject": subject, "html": html},
            timeout=10,
        )
    except Exception as e:
        logger.error("Email failed: %s", e)

def desktop_alert(title: str, message: str):
    if not DESKTOP_AVAILABLE:
        return
    try:
        desktop_notify.notify(title=title, message=message, app_name="Stock Tracker", timeout=8)
    except Exception:
        pass

# ── Alert evaluation ──────────────────────────────────────────────────────────

async def evaluate_alerts(bot, cfg: dict, symbol: str, stock: dict, info: dict):
    price      = info["price"]
    change_pct = info.get("change_pct")
    name       = info["company_name"]
    url        = info["url"]
    chat_id    = cfg.get("chat_id")

    if stock.get("target_low") and price <= stock["target_low"]:
        msg = (f"🟢 *Buy Alert — Target Hit!*\n\n📊 *{name}* (`{symbol}`)\n"
               f"💰 Current: *₹{price:,.2f}*\n🎯 Target: ₹{stock['target_low']:,.2f}\n🕐 {now_ist_str()}")
        if chat_id: await tg_alert(bot, chat_id, msg, url)
        email_alert(cfg, f"🟢 Buy Alert: {name}", f"<p>{msg}</p>")
        desktop_alert(f"Buy Alert: {name}", f"₹{price:,.2f}")

    if stock.get("target_high") and price >= stock["target_high"]:
        msg = (f"🔴 *Sell Alert — Target Hit!*\n\n📊 *{name}* (`{symbol}`)\n"
               f"💰 Current: *₹{price:,.2f}*\n🎯 Target: ₹{stock['target_high']:,.2f}\n🕐 {now_ist_str()}")
        if chat_id: await tg_alert(bot, chat_id, msg, url)
        email_alert(cfg, f"🔴 Sell Alert: {name}", f"<p>{msg}</p>")
        desktop_alert(f"Sell Alert: {name}", f"₹{price:,.2f}")

    alert_pct = stock.get("alert_pct_change")
    if alert_pct and change_pct is not None and abs(change_pct) >= abs(alert_pct):
        arrow = "📉" if change_pct < 0 else "📈"
        msg   = (f"{arrow} *Big Move!*\n\n📊 *{name}* (`{symbol}`)\n"
                 f"💰 ₹{price:,.2f}  {change_pct:+.2f}% today\n🕐 {now_ist_str()}")
        if chat_id: await tg_alert(bot, chat_id, msg, url)
        email_alert(cfg, f"{arrow} {name} moved {change_pct:+.2f}%", f"<p>{msg}</p>")
        desktop_alert(f"Big Move: {name}", f"{change_pct:+.2f}%")

# ── Scheduler ─────────────────────────────────────────────────────────────────

async def check_all_stocks(bot, cfg: dict):
    if not is_market_open():
        logger.info("Market closed — skipping.")
        return
    stocks = load_stocks()
    if not stocks:
        return
    for symbol, stock in stocks.items():
        info = fetch_stock_price(symbol)
        if not info:
            continue
        stocks[symbol]["current_price"] = info["price"]
        stocks[symbol]["company_name"]  = info["company_name"]
        stocks[symbol]["last_checked"]  = info["fetched_at"]
        stocks[symbol]["change_pct"]    = info.get("change_pct")
        ph = stocks[symbol].setdefault("price_history", [])
        ph.append({"price": info["price"], "ts": info["fetched_at"]})
        stocks[symbol]["price_history"] = ph[-50:]
        await evaluate_alerts(bot, cfg, symbol, stock, info)
        time.sleep(2)
    save_stocks(stocks)

async def send_daily_summary(bot, cfg: dict):
    stocks  = load_stocks()
    chat_id = cfg.get("chat_id")
    if not stocks or not chat_id:
        return
    lines = [f"📋 *Daily Summary* — {datetime.now(IST).strftime('%d %b %Y')}\n"]
    for symbol, s in stocks.items():
        price = s.get("current_price")
        pct   = s.get("change_pct")
        name  = s.get("company_name", symbol)
        if price:
            arrow   = "📈" if (pct or 0) >= 0 else "📉"
            pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
            lines.append(f"{arrow} *{name}*: ₹{price:,.2f}  `{pct_str}`")
        else:
            lines.append(f"⚪ *{name}*: N/A")
    await tg_alert(bot, chat_id, "\n".join(lines))

def send_hourly_email(cfg: dict):
    if not cfg.get("email_enabled") or not is_market_open():
        return
    stocks = load_stocks()
    if not stocks:
        return
    rows = ""
    for sym, s in stocks.items():
        price = s.get("current_price")
        pct   = s.get("change_pct")
        name  = s.get("company_name", sym)
        if not price:
            continue
        color = "#27ae60" if (pct or 0) >= 0 else "#e74c3c"
        pct_s = f"{pct:+.2f}%" if pct is not None else "N/A"
        tgts  = ""
        if s.get("target_low"):  tgts += f"Buy: ₹{s['target_low']:,.0f} "
        if s.get("target_high"): tgts += f"Sell: ₹{s['target_high']:,.0f}"
        bg = "#e8f5e9" if (s.get("target_low") and price <= s["target_low"]*1.02) else \
             "#fce4ec" if (s.get("target_high") and price >= s["target_high"]*0.98) else "#fff"
        rows += (f"<tr style='background:{bg}'><td style='padding:8px'><b>{name}</b><br><small>{sym}</small></td>"
                 f"<td style='padding:8px'><b>₹{price:,.2f}</b></td>"
                 f"<td style='padding:8px;color:{color}'>{pct_s}</td>"
                 f"<td style='padding:8px;font-size:0.85em'>{tgts or '-'}</td></tr>")
    html = (f"<html><body style='font-family:Arial,sans-serif;max-width:600px;margin:auto'>"
            f"<div style='background:#1a237e;color:#fff;padding:14px;border-radius:8px 8px 0 0'>"
            f"<h2 style='margin:0'>📊 Hourly Stock Update</h2>"
            f"<p style='margin:4px 0 0;opacity:.8'>{now_ist_str()}</p></div>"
            f"<table width='100%' cellpadding='0' cellspacing='0' style='border:1px solid #ddd'>"
            f"<tr style='background:#f5f5f5'><th style='padding:8px;text-align:left'>Stock</th>"
            f"<th style='padding:8px;text-align:left'>Price</th>"
            f"<th style='padding:8px;text-align:left'>Change</th>"
            f"<th style='padding:8px;text-align:left'>Targets</th></tr>{rows}</table>"
            f"<p style='color:#999;font-size:.8em;padding:8px'>🟢 Green = near buy | 🔴 Red = near sell</p>"
            f"</body></html>")
    email_alert(cfg, f"📊 Stock Update — {datetime.now(IST).strftime('%I:%M %p')}", html)

def run_scheduler(bot, cfg: dict):
    import asyncio
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        schedule.every(CHECK_INTERVAL_MINS).minutes.do(lambda: loop.run_until_complete(check_all_stocks(bot, cfg)))
        schedule.every().day.at(DAILY_SUMMARY_TIME).do(lambda: loop.run_until_complete(send_daily_summary(bot, cfg)))
        schedule.every(1).hours.do(lambda: send_hourly_email(cfg))
        while True:
            schedule.run_pending()
            time.sleep(30)
    threading.Thread(target=_run, daemon=True).start()

# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    cfg["chat_id"] = str(update.effective_chat.id)
    save_config(cfg)
    await update.message.reply_text(
        "📈 *Welcome to Stock Price Tracker!*\n\n"
        "📋 *Commands:*\n"
        "/track `RELIANCE` — Add stock\n"
        "/setlow `RELIANCE 1400` — Buy alert\n"
        "/sethigh `RELIANCE 1600` — Sell alert\n"
        "/setpct `RELIANCE 5` — ±% move alert\n"
        "/list — View watchlist\n"
        "/remove `RELIANCE` — Remove stock\n"
        "/check — Check prices now\n"
        "/summary — Today's summary\n"
        "/setemail — Set up email alerts\n"
        "/emailstatus — Email status\n"
        "/disableemail — Turn off email\n\n"
        "💡 Examples: RELIANCE, TCS, INFY, HDFCBANK, WIPRO, SBIN",
        parse_mode="Markdown",
    )

async def cmd_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /track RELIANCE")
        return
    symbol = ctx.args[0].upper().replace(".NS","").replace(".BO","").strip()
    msg    = await update.message.reply_text(f"🔍 Fetching {symbol}...")
    info   = fetch_stock_price(symbol)
    if not info:
        await msg.edit_text(
            f"❌ Could not fetch *{symbol}*.\n\n"
            "Possible reasons:\n"
            "• Wrong symbol — try RELIANCE not Reliance Industries\n"
            "• Market closed — try during 9:15 AM–3:30 PM IST\n"
            "• Yahoo Finance temporarily down — try again in a minute\n\n"
            "Examples: RELIANCE, TCS, INFY, HDFCBANK, WIPRO, SBIN, ITC",
            parse_mode="Markdown"
        )
        return
    stocks = load_stocks()
    stocks[symbol] = {
        "symbol": symbol, "company_name": info["company_name"],
        "current_price": info["price"], "added_price": info["price"],
        "target_low": None, "target_high": None, "alert_pct_change": None,
        "added_at": datetime.now(IST).isoformat(), "last_checked": info["fetched_at"],
        "change_pct": info.get("change_pct"),
        "price_history": [{"price": info["price"], "ts": info["fetched_at"]}],
    }
    save_stocks(stocks)
    pct_str = f" ({info['change_pct']:+.2f}% today)" if info.get("change_pct") is not None else ""
    await msg.edit_text(
        f"✅ *Tracking {symbol}!*\n\n"
        f"🏢 {info['company_name']}\n"
        f"💰 Price: *₹{info['price']:,.2f}*{pct_str}\n\n"
        f"• `/setlow {symbol} <price>` — buy alert\n"
        f"• `/sethigh {symbol} <price>` — sell alert\n"
        f"• `/setpct {symbol} 5` — 5% move alert",
        parse_mode="Markdown",
    )

async def cmd_setlow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /setlow RELIANCE 1400")
        return
    symbol = ctx.args[0].upper()
    try:    target = float(ctx.args[1].replace(",",""))
    except: await update.message.reply_text("Invalid price."); return
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"Track {symbol} first with /track {symbol}")
        return
    stocks[symbol]["target_low"] = target
    save_stocks(stocks)
    await update.message.reply_text(f"🟢 Alert set — will notify when {symbol} drops below *₹{target:,.2f}*", parse_mode="Markdown")

async def cmd_sethigh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /sethigh RELIANCE 1600")
        return
    symbol = ctx.args[0].upper()
    try:    target = float(ctx.args[1].replace(",",""))
    except: await update.message.reply_text("Invalid price."); return
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"Track {symbol} first with /track {symbol}")
        return
    stocks[symbol]["target_high"] = target
    save_stocks(stocks)
    await update.message.reply_text(f"🔴 Alert set — will notify when {symbol} rises above *₹{target:,.2f}*", parse_mode="Markdown")

async def cmd_setpct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /setpct RELIANCE 5")
        return
    symbol = ctx.args[0].upper()
    try:    pct = float(ctx.args[1].replace("%",""))
    except: await update.message.reply_text("Invalid %."); return
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"Track {symbol} first with /track {symbol}")
        return
    stocks[symbol]["alert_pct_change"] = pct
    save_stocks(stocks)
    await update.message.reply_text(f"⚡ Alert set — will notify when {symbol} moves *±{pct}%* in a day", parse_mode="Markdown")

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stocks = load_stocks()
    if not stocks:
        await update.message.reply_text("Watchlist empty. Use /track RELIANCE to start.")
        return
    lines = ["📋 *Your Watchlist:*\n"]
    for sym, s in stocks.items():
        price = s.get("current_price")
        pct   = s.get("change_pct")
        p_str = f"₹{price:,.2f}" if price else "N/A"
        c_str = f" ({pct:+.2f}%)" if pct is not None else ""
        alts  = []
        if s.get("target_low"):       alts.append(f"⬇️₹{s['target_low']:,.0f}")
        if s.get("target_high"):      alts.append(f"⬆️₹{s['target_high']:,.0f}")
        if s.get("alert_pct_change"): alts.append(f"±{s['alert_pct_change']}%")
        lines.append(f"• *{sym}* — {p_str}{c_str}" + (f"  |  {' '.join(alts)}" if alts else ""))
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /remove RELIANCE")
        return
    symbol = ctx.args[0].upper()
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"{symbol} not in watchlist.")
        return
    del stocks[symbol]
    save_stocks(stocks)
    await update.message.reply_text(f"✅ Removed *{symbol}*", parse_mode="Markdown")

async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_market_open():
        await update.message.reply_text("⚠️ Market closed. Fetching last known prices...")
    msg    = await update.message.reply_text("🔄 Fetching prices...")
    stocks = load_stocks()
    if not stocks:
        await msg.edit_text("Watchlist empty. Use /track to add stocks.")
        return
    lines = [f"📊 *Prices* — {now_ist_str()}\n"]
    for symbol in stocks:
        info = fetch_stock_price(symbol)
        if info:
            pct_s = f" ({info['change_pct']:+.2f}%)" if info.get("change_pct") is not None else ""
            arrow = "📈" if (info.get("change_pct") or 0) >= 0 else "📉"
            lines.append(f"{arrow} *{symbol}*: ₹{info['price']:,.2f}{pct_s}")
            stocks[symbol]["current_price"] = info["price"]
            stocks[symbol]["change_pct"]    = info.get("change_pct")
        else:
            lines.append(f"⚪ *{symbol}*: Could not fetch")
        time.sleep(2)
    save_stocks(stocks)
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send_daily_summary(ctx.bot, load_config())

async def cmd_setemail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📧 *Email Setup*\n\nSend me your Gmail address:\n\nExample: `yourname@gmail.com`\n\nSend /cancel to stop.",
        parse_mode="Markdown"
    )
    return AWAITING_EMAIL

async def email_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import re
    email = update.message.text.strip()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("Invalid email. Try again or /cancel.")
        return AWAITING_EMAIL
    ctx.user_data["pending_email"] = email
    await update.message.reply_text(
        "✅ Got it!\n\nNow send your *Resend API Key*\n\n"
        "📌 Get it free at *resend.com*:\n"
        "1. Sign up → verify email\n"
        "2. Click API Keys → Create API Key\n"
        "3. Copy key (starts with `re_`) and paste here\n\n"
        "Send /cancel to stop.",
        parse_mode="Markdown"
    )
    return AWAITING_PASSWORD

async def password_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    api_key = update.message.text.strip().replace(" ", "")
    email   = ctx.user_data.get("pending_email")
    cfg     = load_config()
    cfg["email_enabled"]   = True
    cfg["resend_api_key"]  = api_key
    cfg["email_recipient"] = email
    save_config(cfg)
    try:
        await update.message.delete()
    except Exception:
        pass
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": "Stock Tracker <onboarding@resend.dev>", "to": [email],
                  "subject": "✅ Stock Tracker Email Connected!",
                  "html": "<h2>✅ Emails working!</h2><p>You'll get instant alerts when targets are hit and hourly summaries during market hours.</p>"},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            await update.message.reply_text(
                f"🎉 *Email enabled!*\n\n📧 Alerts → `{email}`\n\nTest email sent — check inbox!",
                parse_mode="Markdown"
            )
        else:
            raise Exception(resp.text)
    except Exception as e:
        cfg["email_enabled"] = False
        save_config(cfg)
        await update.message.reply_text(f"⚠️ Failed: {e}\n\nCheck your Resend key and try /setemail again.")
    return ConversationHandler.END

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

async def cmd_emailstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    if cfg.get("email_enabled") and cfg.get("email_recipient"):
        await update.message.reply_text(f"📧 *Email ON* → `{cfg['email_recipient']}`\n\n/disableemail to turn off.", parse_mode="Markdown")
    else:
        await update.message.reply_text("📧 *Email OFF*\n\n/setemail to enable.", parse_mode="Markdown")

async def cmd_disableemail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    cfg["email_enabled"] = False
    save_config(cfg)
    await update.message.reply_text("🔕 Email disabled. /setemail to re-enable.")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cfg   = load_config()
    token = cfg.get("telegram_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("No token. Add TELEGRAM_BOT_TOKEN to Railway Variables.")
        return

    app = Application.builder().token(token).build()

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("setemail", cmd_setemail)],
        states={
            AWAITING_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, email_received)],
            AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_received)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    ))

    for cmd, fn in [
        ("start","cmd_start"),("track","cmd_track"),("setlow","cmd_setlow"),
        ("sethigh","cmd_sethigh"),("setpct","cmd_setpct"),("list","cmd_list"),
        ("remove","cmd_remove"),("check","cmd_check"),("summary","cmd_summary"),
        ("emailstatus","cmd_emailstatus"),("disableemail","cmd_disableemail"),("help","cmd_help"),
    ]:
        app.add_handler(CommandHandler(cmd, eval(fn)))

    run_scheduler(app.bot, cfg)
    print("📈 Stock Tracker running — yfinance history() method")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
