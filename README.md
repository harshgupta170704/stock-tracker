# stock-tracker
📊 Real-time NSE stock price tracker bot built with Python &amp; Yahoo Finance — Telegram + Email alerts, deployable on Railway

# 📈 Stock Price Tracker — Telegram Bot

> **Track NSE/BSE stocks in real time. Get instant Telegram + Email alerts when your target price is hit. Powered by Yahoo Finance. Deployable on Railway in minutes.**

---

## 📋 Table of Contents

- [What This Bot Does](#-what-this-bot-does)
- [Features](#-features)
- [Files in This Project](#-files-in-this-project)
- [Quick Start - Run Locally](#-quick-start-run-locally)
- [Deploy on Railway 24/7 Free](#-deploy-on-railway-247-free)
- [All Bot Commands](#-all-bot-commands)
- [How Alerts Work](#-how-alerts-work)
- [Email Setup Inside Telegram](#-email-setup-inside-telegram)
- [Supported Stocks](#-supported-stocks)
- [Troubleshooting](#-troubleshooting)
- [FAQ](#-faq)

---

## 🤖 What This Bot Does

This is a **Telegram bot** that monitors Indian stock prices (NSE/BSE) every **15 minutes during market hours** and instantly alerts you when:

- A stock hits your **buy target** (price drops to your level)
- A stock hits your **sell target** (price rises to your level)
- A stock makes a **big move** (e.g. ±5% in a day)
- Every **hour** — sends a clean email summary of all your stocks

All you need to do is:
1. Add a stock → `/track RELIANCE`
2. Set a target → `/setlow RELIANCE 1400`
3. Relax — the bot watches it for you 24/7

---

## ✨ Features

| Feature | Details |
|---|---|
| 📊 Live Prices | Fetches real-time NSE prices via Yahoo Finance |
| 🔔 Telegram Alerts | Instant message when target is hit |
| 📧 Email Alerts | Set up email directly inside Telegram with /setemail |
| ⏰ Hourly Email | Clean price summary email every hour during market hours |
| 🎯 Target Prices | Set buy price (low) and sell price (high) per stock |
| ⚡ % Move Alerts | Get alerted if a stock moves ±X% in a single day |
| 📋 Daily Summary | Full watchlist summary sent at 3:35 PM every market day |
| 🕐 Market Hours Only | Only checks Mon–Fri, 9:15 AM – 3:30 PM IST |
| 💾 Price History | Stores last 50 price points per stock |
| 🖥️ Desktop Notifications | Pop-up alerts on your PC when running locally |
| ☁️ Cloud Deployable | One-click deploy on Railway — runs 24/7 for free |

---

## 📁 Files in This Project

```
stock_tracker/
│
├── stock_bot.py          ← Main bot code (all logic lives here)
├── requirements.txt      ← Python packages needed
├── config.json           ← Your bot token + email settings
│                           (DO NOT upload this to GitHub!)
├── Procfile              ← Tells Railway how to start the bot
├── runtime.txt           ← Tells Railway to use Python 3.11
│
├── tracked_stocks.json   ← Auto-created when you add first stock
├── stock_tracker.log     ← Auto-created activity log
└── README.md             ← This file
```

---

## ⚡ Quick Start — Run Locally

### Step 1 — Install Python 3.11

Download: https://www.python.org/ftp/python/3.11.15/python-3.11.15-amd64.exe

During installation: tick "Add Python to PATH" ✅

---

### Step 2 — Set up your folder

Create a folder called `stock_tracker` on your Desktop.
Put all 5 files inside it:
```
stock_tracker/
    stock_bot.py
    requirements.txt
    config.json
    Procfile
    runtime.txt
```

---

### Step 3 — Create your Telegram Bot

1. Open Telegram → search @BotFather (blue tick)
2. Send /newbot
3. Give it a name: e.g. My Stock Tracker
4. Give it a username: e.g. mystocktracker_bot (must end in bot)
5. BotFather sends you a token like: 7123456789:AAFxyzABCDEF...
6. Copy this token

---

### Step 4 — Add token to config.json

Open config.json in Notepad and paste your token:
```json
{
  "telegram_token": "7123456789:AAFxyzABCDEF...",
  "chat_id": ""
}
```
Save and close.

---

### Step 5 — Open CMD in your folder

1. Open the stock_tracker folder in File Explorer
2. Click the address bar at the top
3. Type cmd and press Enter

---

### Step 6 — Install packages and run

Paste this entire command and press Enter:
```
py -3.11 -m pip install python-telegram-bot==21.3 yfinance requests schedule plyer pytz && py -3.11 stock_bot.py
```

You should see:
```
📈 Stock Price Tracker Bot running...
⏱  Checking every 15 mins during market hours (9:15-3:30 IST)
```

---

### Every time after first setup

Just run these 2 commands:
```
cd "C:\Users\YourName\OneDrive\Desktop\stock_tracker"
py -3.11 stock_bot.py
```

---

## 🚂 Deploy on Railway (24/7 Free)

Railway runs your bot in the cloud — works even when your PC is off.

---

### Step 1 — Upload to GitHub

1. Go to github.com → create a free account
2. Click "+" → "New repository"
3. Name it stock-tracker → click "Create repository"
4. Click "uploading an existing file"
5. Drag and drop ONLY these 4 files:
   - stock_bot.py
   - requirements.txt
   - Procfile
   - runtime.txt

   WARNING: Do NOT upload config.json — it has your secret token!

6. Click "Commit changes"

---

### Step 2 — Sign up on Railway

1. Go to railway.app
2. Click "Login" → "Login with GitHub"
3. Authorize Railway

---

### Step 3 — Create project

1. Click "New Project"
2. Click "Deploy from GitHub repo"
3. Select your stock-tracker repo
4. Railway starts building — wait 1-2 minutes

---

### Step 4 — Add your bot token

1. Click on your project
2. Click the "Variables" tab
3. Click "New Variable" and add:
   Name:   TELEGRAM_BOT_TOKEN
   Value:  your_bot_token_here
4. Click "Add" — Railway restarts automatically

---

### Step 5 — Verify it's running

1. Click "Deployments" tab
2. You should see Active status
3. Click the deployment → "View Logs"
4. You should see:
   📈 Stock Price Tracker Bot running...

---

### Step 6 — Test it

Open Telegram → send /start to your bot → it should reply instantly!

---

## 📋 All Bot Commands

| Command | Example | What it does |
|---|---|---|
| /start | /start | Welcome message + all commands |
| /track | /track RELIANCE | Add a stock to your watchlist |
| /setlow | /setlow RELIANCE 1400 | Alert when price drops BELOW 1400 |
| /sethigh | /sethigh RELIANCE 1600 | Alert when price rises ABOVE 1600 |
| /setpct | /setpct RELIANCE 5 | Alert when stock moves +/-5% in a day |
| /list | /list | View all tracked stocks with prices |
| /remove | /remove RELIANCE | Remove stock from watchlist |
| /check | /check | Manually check all prices right now |
| /summary | /summary | Get today's full watchlist summary |
| /setemail | /setemail | Set up email alerts step by step |
| /emailstatus | /emailstatus | Check if email is on and which address |
| /disableemail | /disableemail | Turn off email alerts |
| /help | /help | Show all commands |

---

## 🔔 How Alerts Work

### Buy Alert — Price drops below target
```
/setlow RELIANCE 1400
```
You get alerted when RELIANCE drops to 1400 or below.
Good for: "Tell me when it is cheap enough to buy"

---

### Sell Alert — Price rises above target
```
/sethigh RELIANCE 1700
```
You get alerted when RELIANCE rises to 1700 or above.
Good for: "Tell me when it is high enough to sell"

---

### Big Move Alert — % change in a day
```
/setpct RELIANCE 5
```
You get alerted when RELIANCE moves +/-5% or more in a single day.
Good for: "Tell me if something big happens"

---

### Daily Summary
Automatically sent every day at 3:35 PM IST after market close.
Shows all your stocks, prices, and day changes.

---

### Hourly Email
Sent every hour during market hours (9:15 AM to 3:30 PM IST) showing:
- Current price of each stock
- Day change percentage
- Your buy and sell targets
- Green rows = stock is near your buy target
- Red rows = stock is near your sell target

---

## 📧 Email Setup Inside Telegram

No need to edit any files. Just send /setemail to your bot:

```
You:  /setemail
Bot:  Please send me your Gmail address
You:  yourname@gmail.com
Bot:  Now send me your Gmail App Password
You:  abcd efgh ijkl mnop
Bot:  Email enabled! Test email sent!
```

The bot automatically deletes your password message for security.

---

### How to get Gmail App Password

1. Go to myaccount.google.com
2. Click "Security"
3. Turn on "2-Step Verification" if not already on
4. In the search bar type "App Passwords"
5. Select "Mail" and click "Generate"
6. Copy the 16-character password shown
7. Send it to the bot when asked

---

## 🏢 Supported Stocks

Use standard NSE symbols — same as on Groww or Zerodha:

| Company | Symbol |
|---|---|
| Reliance Industries | RELIANCE |
| Tata Consultancy Services | TCS |
| Infosys | INFY |
| HDFC Bank | HDFCBANK |
| Wipro | WIPRO |
| State Bank of India | SBIN |
| Bajaj Finance | BAJFINANCE |
| Adani Enterprises | ADANIENT |
| ITC | ITC |
| Tata Motors | TATAMOTORS |
| Asian Paints | ASIANPAINT |
| Maruti Suzuki | MARUTI |
| Hindustan Unilever | HINDUNILVR |
| Axis Bank | AXISBANK |
| Kotak Mahindra Bank | KOTAKBANK |

Find any symbol at groww.in/stocks or nseindia.com

---

## 🔧 Troubleshooting

### "No module named schedule" or similar error
Run this:
```
py -3.11 -m pip install python-telegram-bot==21.3 yfinance requests schedule plyer pytz
```

---

### Bot not replying on Telegram
- Make sure CMD window is open (local) or Railway shows Active (cloud)
- Make sure you sent /start to the bot first
- Check your token in config.json or Railway Variables is correct

---

### /track RELIANCE shows "Could not find"
- Make sure you are using the correct NSE symbol
- Try /track TCS or /track INFY to test
- Yahoo Finance works outside market hours too

---

### Email not sending
- Make sure you used Gmail App Password, not your normal Gmail password
- Make sure 2-Step Verification is ON in your Google account
- Try /disableemail then /setemail again

---

### Railway deployment fails
- Make sure all 4 files are uploaded to GitHub
- Make sure TELEGRAM_BOT_TOKEN is added in Railway Variables
- Check the deployment logs for the specific error

---

### "The system cannot find the path specified" in CMD
Your folder path has spaces. Use quotes:
```
cd "C:\Users\YourName\OneDrive\Desktop\stock_tracker"
```

---

## ❓ FAQ

Q: Do I need to install Python and packages every time?
A: No. Install once. After that just run:
   py -3.11 stock_bot.py

Q: Can I track multiple stocks?
A: Yes! Track as many as you want using /track for each one.

Q: Can I set both buy and sell targets for same stock?
A: Yes! Use /setlow for buy target and /sethigh for sell target on same stock.

Q: What happens if I close CMD window?
A: The bot stops. Use Railway deployment to run 24/7 without keeping PC on.

Q: How do I make a shortcut to run the bot?
A: Create a file called run.bat in the folder with this inside:
   py -3.11 stock_bot.py
   Double-click it anytime to start.

Q: Is my Gmail password safe?
A: Yes. Stored only in local config.json which is never uploaded to GitHub.
   The bot also deletes your password message from Telegram after reading it.

Q: Does it work on weekends?
A: Price checks are skipped on weekends but the bot responds to commands anytime.

Q: Railway says I used my free credits. What now?
A: Railway gives $5 free per month. This bot uses about $0.50 per month.
   Should easily last the whole month.

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Bot Framework | python-telegram-bot 21.3 |
| Stock Data | Yahoo Finance (yfinance) |
| Scheduling | schedule library |
| Email | Gmail SMTP |
| Timezone | pytz (Asia/Kolkata IST) |
| Deployment | Railway.app |
| Language | Python 3.11 |

