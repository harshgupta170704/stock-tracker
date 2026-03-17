#!/usr/bin/env python3
"""
Stock Price Tracker — Telegram Bot
Uses Yahoo Finance (yfinance) for reliable NSE/BSE stock data
Checks every 15 mins during market hours (IST)
Alerts: target price low/high, % day change, daily summary
"""

import os
import json
import time
import logging
import smtplib
import schedule
import threading
import yfinance as yf
from typing import Optional, Dict, Any
from datetime import datetime, time as dtime
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
    handlers=[
        logging.FileHandler("stock_tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

CONFIG_FILE         = "config.json"
STOCKS_FILE         = "tracked_stocks.json"
IST                 = pytz.timezone("Asia/Kolkata")
MARKET_OPEN         = dtime(9, 15)
MARKET_CLOSE        = dtime(15, 30)
CHECK_INTERVAL_MINS = 15
DAILY_SUMMARY_TIME  = "15:35"

# Conversation states
AWAITING_EMAIL    = 1
AWAITING_PASSWORD = 2

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
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE

def now_ist_str() -> str:
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")

def to_yf_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return symbol + ".NS"

def groww_url(symbol: str) -> str:
    clean = symbol.upper().replace(".NS", "").replace(".BO", "")
    return f"https://groww.in/stocks/{clean.lower()}"

def fetch_stock_price(symbol: str) -> Optional[Dict[str, Any]]:
    yf_sym = to_yf_symbol(symbol)
    try:
        ticker = yf.Ticker(yf_sym)
        info   = ticker.fast_info
        price  = getattr(info, "last_price", None)
        prev_close = getattr(info, "previous_close", None)

        company_name = symbol
        try:
            full_info    = ticker.info
            company_name = full_info.get("longName") or full_info.get("shortName") or symbol
        except Exception:
            pass

        if price is None or price == 0:
            logger.warning("No price data for %s", yf_sym)
            return None

        change = None
        change_pct = None
        if prev_close and prev_close > 0:
            change     = round(price - prev_close, 2)
            change_pct = round(((price - prev_close) / prev_close) * 100, 2)

        return {
            "company_name": company_name,
            "price":        round(float(price), 2),
            "change":       change,
            "change_pct":   change_pct,
            "prev_close":   prev_close,
            "url":          groww_url(symbol),
            "fetched_at":   datetime.now(IST).isoformat(),
        }
    except Exception as e:
        logger.error("Error fetching %s: %s", yf_sym, e)
        return None

async def tg_alert(bot, chat_id: str, text: str, url: str = None):
    kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if url:
        kb = [[InlineKeyboardButton("📈 View on Groww", url=url)]]
        kwargs["reply_markup"] = InlineKeyboardMarkup(kb)
    await bot.send_message(**kwargs)

def email_alert(cfg: dict, subject: str, html: str):
    if not cfg.get("email_enabled"):
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["email_sender"]
        msg["To"]      = cfg["email_recipient"]
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(cfg["email_sender"], cfg["email_password"])
            s.sendmail(cfg["email_sender"], cfg["email_recipient"], msg.as_string())
    except Exception as e:
        logger.error("Email failed: %s", e)

def desktop_alert(title: str, message: str):
    if not DESKTOP_AVAILABLE:
        return
    try:
        desktop_notify.notify(title=title, message=message, app_name="Stock Tracker", timeout=8)
    except Exception:
        pass

async def evaluate_alerts(bot, cfg: dict, symbol: str, stock: dict, info: dict):
    price      = info["price"]
    change_pct = info.get("change_pct")
    name       = info["company_name"]
    url        = info["url"]
    chat_id    = cfg.get("chat_id")

    if stock.get("target_low") and price <= stock["target_low"]:
        msg = (
            f"🟢 *Buy Alert — Target Hit!*\n\n"
            f"📊 *{name}* (`{symbol}`)\n"
            f"💰 Current: *₹{price:,.2f}*\n"
            f"🎯 Your target: ₹{stock['target_low']:,.2f}\n"
            f"📉 Price dropped to your buy target!\n"
            f"🕐 {now_ist_str()}"
        )
        if chat_id:
            await tg_alert(bot, chat_id, msg, url)
        email_alert(cfg, f"🟢 Buy Alert: {name} hit ₹{price:,.2f}", f"<p>{msg.replace(chr(10), '<br>')}</p>")
        desktop_alert(f"Buy Alert: {name}", f"₹{price:,.2f} <= target ₹{stock['target_low']:,.2f}")

    if stock.get("target_high") and price >= stock["target_high"]:
        msg = (
            f"🔴 *Sell Alert — Target Hit!*\n\n"
            f"📊 *{name}* (`{symbol}`)\n"
            f"💰 Current: *₹{price:,.2f}*\n"
            f"🎯 Your target: ₹{stock['target_high']:,.2f}\n"
            f"📈 Price rose to your sell target!\n"
            f"🕐 {now_ist_str()}"
        )
        if chat_id:
            await tg_alert(bot, chat_id, msg, url)
        email_alert(cfg, f"🔴 Sell Alert: {name} hit ₹{price:,.2f}", f"<p>{msg.replace(chr(10), '<br>')}</p>")
        desktop_alert(f"Sell Alert: {name}", f"₹{price:,.2f} >= target ₹{stock['target_high']:,.2f}")

    alert_pct = stock.get("alert_pct_change")
    if alert_pct and change_pct is not None and abs(change_pct) >= abs(alert_pct):
        arrow     = "📉" if change_pct < 0 else "📈"
        direction = "fell" if change_pct < 0 else "rose"
        msg = (
            f"{arrow} *Big Move Alert!*\n\n"
            f"📊 *{name}* (`{symbol}`)\n"
            f"💰 Current: *₹{price:,.2f}*\n"
            f"📊 Today's change: *{change_pct:+.2f}%*\n"
            f"⚡ Stock {direction} more than {abs(alert_pct)}% today!\n"
            f"🕐 {now_ist_str()}"
        )
        if chat_id:
            await tg_alert(bot, chat_id, msg, url)
        email_alert(cfg, f"{arrow} Big Move: {name} {change_pct:+.2f}%", f"<p>{msg.replace(chr(10), '<br>')}</p>")
        desktop_alert(f"Big Move: {name}", f"{change_pct:+.2f}% today — ₹{price:,.2f}")

async def check_all_stocks(bot, cfg: dict):
    if not is_market_open():
        logger.info("Market closed — skipping check.")
        return
    stocks = load_stocks()
    if not stocks:
        return
    logger.info("Checking %d stocks...", len(stocks))
    for symbol, stock in stocks.items():
        info = fetch_stock_price(symbol)
        if not info:
            continue
        stocks[symbol]["current_price"] = info["price"]
        stocks[symbol]["company_name"]  = info["company_name"]
        stocks[symbol]["last_checked"]  = info["fetched_at"]
        stocks[symbol]["change_pct"]    = info.get("change_pct")
        if "price_history" not in stocks[symbol]:
            stocks[symbol]["price_history"] = []
        stocks[symbol]["price_history"].append({"price": info["price"], "change_pct": info.get("change_pct"), "ts": info["fetched_at"]})
        stocks[symbol]["price_history"] = stocks[symbol]["price_history"][-50:]
        await evaluate_alerts(bot, cfg, symbol, stock, info)
    save_stocks(stocks)
    logger.info("Stock check complete.")

async def send_daily_summary(bot, cfg: dict):
    stocks  = load_stocks()
    chat_id = cfg.get("chat_id")
    if not stocks or not chat_id:
        return
    lines = [f"📋 *Daily Market Summary* — {datetime.now(IST).strftime('%d %b %Y')}\n"]
    for symbol, s in stocks.items():
        price = s.get("current_price")
        pct   = s.get("change_pct")
        name  = s.get("company_name", symbol)
        if price:
            arrow   = "📈" if (pct or 0) >= 0 else "📉"
            pct_str = f"{pct:+.2f}%" if pct is not None else "N/A"
            lines.append(f"{arrow} *{name}* (`{symbol}`): ₹{price:,.2f}  `{pct_str}`")
        else:
            lines.append(f"⚪ *{name}* (`{symbol}`): Data unavailable")
    await tg_alert(bot, chat_id, "\n".join(lines))

def send_hourly_email(cfg: dict):
    """Send a clean hourly price summary email during market hours."""
    if not cfg.get("email_enabled"):
        return
    if not is_market_open():
        return
    stocks = load_stocks()
    if not stocks:
        return

    now_str   = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    html_rows = ""
    for symbol, s in stocks.items():
        price    = s.get("current_price")
        pct      = s.get("change_pct")
        name     = s.get("company_name", symbol)
        tgt_low  = s.get("target_low")
        tgt_high = s.get("target_high")
        if price is None:
            continue
        color   = "#27ae60" if (pct or 0) >= 0 else "#e74c3c"
        arrow   = "▲" if (pct or 0) >= 0 else "▼"
        pct_str = f"{arrow} {abs(pct):.2f}%" if pct is not None else "N/A"
        tgt_str = ""
        if tgt_low:  tgt_str += f"Buy: ₹{tgt_low:,.2f}  "
        if tgt_high: tgt_str += f"Sell: ₹{tgt_high:,.2f}"
        row_bg = "#fff"
        if tgt_low  and price <= tgt_low  * 1.02: row_bg = "#e8f5e9"
        if tgt_high and price >= tgt_high * 0.98: row_bg = "#fce4ec"
        html_rows += (
            f"<tr style=\'background:{row_bg}\'>"
            f"<td style=\'padding:10px\'><b>{name}</b><br><small style=\'color:#888\'>{symbol}</small></td>"
            f"<td style=\'padding:10px;font-size:1.1em\'><b>₹{price:,.2f}</b></td>"
            f"<td style=\'padding:10px;color:{color}\'><b>{pct_str}</b></td>"
            f"<td style=\'padding:10px;color:#666;font-size:0.9em\'>{tgt_str or chr(8212)}</td>"
            f"</tr>"
        )
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:650px;margin:auto;padding:20px">
      <div style="background:#1a237e;color:white;padding:16px 20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">📊 Hourly Stock Update</h2>
        <p style="margin:4px 0 0;opacity:0.8;font-size:0.9em">{now_str}</p>
      </div>
      <table width="100%" border="0" cellpadding="0" cellspacing="0"
             style="border:1px solid #ddd;border-top:none">
        <tr style="background:#f5f5f5">
          <th style="padding:10px;text-align:left">Stock</th>
          <th style="padding:10px;text-align:left">Price</th>
          <th style="padding:10px;text-align:left">Today</th>
          <th style="padding:10px;text-align:left">Your Targets</th>
        </tr>
        {html_rows}
      </table>
      <p style="color:#888;font-size:0.8em;margin-top:12px">
        🟢 Green = near buy target | 🔴 Red = near sell target
      </p>
    </body></html>"""
    email_alert(cfg, f"📊 Hourly Stock Update — {datetime.now(IST).strftime('%I:%M %p IST')}", html)
    import logging
    logging.getLogger(__name__).info("Hourly email sent.")


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

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    cfg["chat_id"] = str(update.effective_chat.id)
    save_config(cfg)
    await update.message.reply_text(
        "📈 *Welcome to Stock Price Tracker!*\n\n"
        "I monitor NSE stocks and alert you instantly.\n\n"
        "📋 *Commands:*\n"
        "/track `RELIANCE` — Add stock to watchlist\n"
        "/setlow `RELIANCE 1400` — Alert when price drops below\n"
        "/sethigh `RELIANCE 1600` — Alert when price rises above\n"
        "/setpct `RELIANCE 5` — Alert on ±5% day move\n"
        "/list — View your watchlist\n"
        "/remove `RELIANCE` — Remove from watchlist\n"
        "/check — Check prices now\n"
        "/summary — Today's summary\n"        "/setemail — Set up email alerts\n"        "/emailstatus — Check email status\n\n"
        "💡 *Example stocks:* RELIANCE, TCS, INFY, HDFCBANK, WIPRO, SBIN",
        parse_mode="Markdown",
    )

async def cmd_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /track RELIANCE\nExamples: RELIANCE, TCS, INFY, HDFCBANK, WIPRO")
        return
    symbol = ctx.args[0].upper().replace(".NS", "").replace(".BO", "")
    msg    = await update.message.reply_text(f"🔍 Fetching {symbol} data...")
    info   = fetch_stock_price(symbol)
    if not info:
        await msg.edit_text(
            f"❌ Could not find *{symbol}*.\n\nMake sure you're using the correct NSE symbol.\nExamples: RELIANCE, TCS, INFY, WIPRO, HDFCBANK",
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
        f"✅ *Now tracking {symbol}!*\n\n"
        f"🏢 {info['company_name']}\n"
        f"💰 Current price: *₹{info['price']:,.2f}*{pct_str}\n\n"
        f"Set alerts:\n"
        f"• `/setlow {symbol} <price>` — buy alert\n"
        f"• `/sethigh {symbol} <price>` — sell alert\n"
        f"• `/setpct {symbol} 5` — alert on 5%+ move",
        parse_mode="Markdown",
    )

async def cmd_setlow(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /setlow RELIANCE 1400")
        return
    symbol = ctx.args[0].upper()
    try:
        target = float(ctx.args[1].replace(",", ""))
    except ValueError:
        await update.message.reply_text("Invalid price.")
        return
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"{symbol} not tracked. Use /track {symbol} first.")
        return
    stocks[symbol]["target_low"] = target
    save_stocks(stocks)
    await update.message.reply_text(f"🟢 *Buy alert set!*\n\n📊 {symbol}\n🎯 Alert below *₹{target:,.2f}*", parse_mode="Markdown")

async def cmd_sethigh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /sethigh RELIANCE 1600")
        return
    symbol = ctx.args[0].upper()
    try:
        target = float(ctx.args[1].replace(",", ""))
    except ValueError:
        await update.message.reply_text("Invalid price.")
        return
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"{symbol} not tracked. Use /track {symbol} first.")
        return
    stocks[symbol]["target_high"] = target
    save_stocks(stocks)
    await update.message.reply_text(f"🔴 *Sell alert set!*\n\n📊 {symbol}\n🎯 Alert above *₹{target:,.2f}*", parse_mode="Markdown")

async def cmd_setpct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /setpct RELIANCE 5")
        return
    symbol = ctx.args[0].upper()
    try:
        pct = float(ctx.args[1].replace("%", ""))
    except ValueError:
        await update.message.reply_text("Invalid percentage.")
        return
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"{symbol} not tracked. Use /track {symbol} first.")
        return
    stocks[symbol]["alert_pct_change"] = pct
    save_stocks(stocks)
    await update.message.reply_text(f"⚡ *% Move alert set!*\n\n📊 {symbol}\n🎯 Alert when move exceeds *±{pct}%*", parse_mode="Markdown")

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stocks = load_stocks()
    if not stocks:
        await update.message.reply_text("Watchlist is empty.\nUse /track RELIANCE to add stocks.")
        return
    lines = ["📋 *Your Watchlist:*\n"]
    for sym, s in stocks.items():
        price     = s.get("current_price")
        pct       = s.get("change_pct")
        price_str = f"₹{price:,.2f}" if price else "N/A"
        pct_str   = f" ({pct:+.2f}%)" if pct is not None else ""
        alerts    = []
        if s.get("target_low"):       alerts.append(f"⬇️₹{s['target_low']:,.0f}")
        if s.get("target_high"):      alerts.append(f"⬆️₹{s['target_high']:,.0f}")
        if s.get("alert_pct_change"): alerts.append(f"±{s['alert_pct_change']}%")
        alert_str = "  |  " + " ".join(alerts) if alerts else ""
        lines.append(f"• *{sym}* — {price_str}{pct_str}{alert_str}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /remove RELIANCE")
        return
    symbol = ctx.args[0].upper()
    stocks = load_stocks()
    if symbol not in stocks:
        await update.message.reply_text(f"{symbol} is not in your watchlist.")
        return
    del stocks[symbol]
    save_stocks(stocks)
    await update.message.reply_text(f"✅ Removed *{symbol}* from watchlist.", parse_mode="Markdown")

async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_market_open():
        await update.message.reply_text("⚠️ Market is closed right now. Checking anyway...")
    msg    = await update.message.reply_text("🔄 Checking all stocks...")
    stocks = load_stocks()
    if not stocks:
        await msg.edit_text("Watchlist is empty. Use /track to add stocks.")
        return
    lines = [f"📊 *Live Prices* — {now_ist_str()}\n"]
    for symbol in stocks:
        info = fetch_stock_price(symbol)
        if info:
            pct_str = f" ({info['change_pct']:+.2f}%)" if info.get("change_pct") is not None else ""
            arrow   = "📈" if (info.get("change_pct") or 0) >= 0 else "📉"
            lines.append(f"{arrow} *{symbol}*: ₹{info['price']:,.2f}{pct_str}")
            stocks[symbol]["current_price"] = info["price"]
            stocks[symbol]["change_pct"]    = info.get("change_pct")
        else:
            lines.append(f"⚪ *{symbol}*: Could not fetch")
    save_stocks(stocks)
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")

async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    await send_daily_summary(ctx.bot, cfg)


async def cmd_setemail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Start conversation to collect email address."""
    await update.message.reply_text(
        "📧 *Email Setup*\n\n"
        "Please send me the *Gmail address* you want alerts sent to:\n\n"
        "Example: `yourname@gmail.com`\n\n"
        "Send /cancel to stop.",
        parse_mode="Markdown"
    )
    return AWAITING_EMAIL

async def email_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Store email and ask for Gmail App Password."""
    import re
    email = update.message.text.strip()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text(
            "⚠️ That doesn't look like a valid email. Please try again or send /cancel."
        )
        return AWAITING_EMAIL

    ctx.user_data["pending_email"] = email
    await update.message.reply_text(
        "✅ Email saved!\n\n"
        "Now I need your *Gmail App Password* to send emails.\n\n"
        "📌 *How to get it:*\n"
        "1. Go to myaccount.google.com\n"
        "2. Security → 2-Step Verification → turn ON\n"
        "3. Search *App Passwords*\n"
        "4. Create one for \'Mail\'\n"
        "5. Copy the 16-character password and send it here\n\n"
        "Send /cancel to stop.",
        parse_mode="Markdown"
    )
    return AWAITING_PASSWORD

async def password_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Store app password, save config, confirm."""
    password = update.message.text.strip().replace(" ", "")
    email    = ctx.user_data.get("pending_email")

    cfg = load_config()
    cfg["email_enabled"]   = True
    cfg["email_sender"]    = email
    cfg["email_password"]  = password
    cfg["email_recipient"] = email
    save_config(cfg)

    # Delete the password message for security
    try:
        await update.message.delete()
    except Exception:
        pass

    # Send test email
    try:
        import smtplib
        from email.mime.text import MIMEText
        test_msg = MIMEText(
            "<h2>✅ Email alerts are working!</h2>"
            "<p>Your Stock Price Tracker will now send you:</p>"
            "<ul><li>⚡ Instant alerts when your target price is hit</li>"
            "<li>📊 Hourly price summary during market hours</li></ul>",
            "html"
        )
        test_msg["Subject"] = "✅ Stock Tracker Email Connected!"
        test_msg["From"]    = email
        test_msg["To"]      = email
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(email, password)
            s.sendmail(email, email, test_msg.as_string())
        await update.message.reply_text(
            "🎉 *Email alerts enabled!*\n\n"
            f"📧 Sending to: `{email}`\n\n"
            "A test email has been sent to confirm it\'s working.\n\n"
            "You will now receive:\n"
            "• ⚡ Instant email when target price is hit\n"
            "• 📊 Hourly price summary (market hours only)",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Could not send test email: {e}\n\n"
            "Please check your App Password and try /setemail again."
        )
        cfg["email_enabled"] = False
        save_config(cfg)

    return ConversationHandler.END

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Email setup cancelled.")
    return ConversationHandler.END

async def cmd_emailstatus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    if cfg.get("email_enabled") and cfg.get("email_recipient"):
        await update.message.reply_text(
            f"📧 *Email alerts: ON*\n\nSending to: `{cfg['email_recipient']}`\n\n"
            "Use /setemail to change the address.\n"
            "Use /disableemail to turn off.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "📧 *Email alerts: OFF*\n\nUse /setemail to enable email alerts.",
            parse_mode="Markdown"
        )

async def cmd_disableemail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    cfg["email_enabled"] = False
    save_config(cfg)
    await update.message.reply_text("🔕 Email alerts disabled. Use /setemail to re-enable.")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)

def main():
    cfg   = load_config()
    token = cfg.get("telegram_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("No Telegram bot token found. Add telegram_token to config.json")
        return
    app = Application.builder().token(token).build()

    # Email setup conversation
    email_conv = ConversationHandler(
        entry_points=[CommandHandler("setemail", cmd_setemail)],
        states={
            AWAITING_EMAIL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, email_received)],
            AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, password_received)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )
    app.add_handler(email_conv)

    for cmd, handler in [
        ("start",        cmd_start),   ("track",        cmd_track),
        ("setlow",       cmd_setlow),  ("sethigh",      cmd_sethigh),
        ("setpct",       cmd_setpct),  ("list",         cmd_list),
        ("remove",       cmd_remove),  ("check",        cmd_check),
        ("summary",      cmd_summary), ("help",         cmd_help),
        ("emailstatus",  cmd_emailstatus), ("disableemail", cmd_disableemail),
    ]:
        app.add_handler(CommandHandler(cmd, handler))
    run_scheduler(app.bot, cfg)
    print("📈 Stock Price Tracker Bot running...")
    print(f"⏱  Checking every {CHECK_INTERVAL_MINS} mins during market hours (9:15-3:30 IST)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
