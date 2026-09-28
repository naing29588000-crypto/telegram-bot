#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import platform
from pathlib import Path
from threading import Thread

# --- Flask Keep Alive & VPS Stats Endpoint ---
from flask import Flask

flask_app = Flask('')

@flask_app.route('/')
def home():
    return "𝐈'ᴍ ravenboii 𝐇ᴏꜱᴛɪɴɢ 𝐁ᴏᴛ ❤️"

@flask_app.route('/stats')
def stats_endpoint():
    """JSON endpoint for VPS monitoring"""
    stats = get_vps_stats()
    return {
        "status": "online",
        "uptime": time.time() - START_TIME,
        "cpu": stats["cpu"],
        "ram": stats["ram"],
        "disk": stats["disk"],
        "swap": stats["swap"],
        "network": stats["network"],
        "processes": stats["processes"],
        "temperature": stats["temperature"],
        "bot": {
            "users": len(active_users) if 'active_users' in dir() else 0,
            "files": sum(len(f) for f in user_files.values()) if 'user_files' in dir() else 0,
            "running": len(bot_scripts) if 'bot_scripts' in dir() else 0,
            "uptime_hours": stats["bot_uptime_hours"]
        }
    }

@flask_app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")

START_TIME = time.time()

# --- Configuration ---
TOKEN = "8871145288:AAH9qTs9SBbJplA8zrxwjM1YmD_r-0dy6uM"
if not TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN is not configured. Add it as a Replit Secret before starting the bot."
    )
OWNER_ID = 8684031913
ADMIN_ID = 8684031913
YOUR_USERNAME = '@naingpyaekyaw'
UPDATE_CHANNEL = 'https://t.me/ruijine'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
PENDING_UPLOADS_DIR = os.path.join(IROTECH_DIR, 'pending_uploads')

FREE_USER_LIMIT = 10
SUBSCRIBED_USER_LIMIT = 25
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)
os.makedirs(PENDING_UPLOADS_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
broadcast_messages = {}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========================================================================
# VPS SYSTEM MONITORING
# ========================================================================

def get_vps_stats():
    """Get comprehensive VPS system statistics"""
    stats = {
        "cpu": {"percent": 0, "count": 0, "freq": 0, "load": [0, 0, 0]},
        "ram": {"percent": 0, "used_mb": 0, "total_mb": 0, "free_mb": 0},
        "swap": {"percent": 0, "used_mb": 0, "total_mb": 0},
        "disk": {"percent": 0, "used_gb": 0, "total_gb": 0, "free_gb": 0},
        "network": {"sent_mb": 0, "recv_mb": 0, "packets_sent": 0, "packets_recv": 0},
        "processes": 0,
        "temperature": "N/A",
        "uptime_hours": 0,
        "bot_uptime_hours": 0,
        "python_version": sys.version.split()[0],
        "platform": platform.platform()
    }
    
    try:
        stats["cpu"]["percent"] = psutil.cpu_percent(interval=0.5)
        stats["cpu"]["count"] = psutil.cpu_count()
        freq = psutil.cpu_freq()
        if freq:
            stats["cpu"]["freq"] = round(freq.current / 1000, 2)
        
        try:
            stats["cpu"]["load"] = [round(x, 2) for x in os.getloadavg()]
        except:
            pass
        
        mem = psutil.virtual_memory()
        stats["ram"]["percent"] = mem.percent
        stats["ram"]["used_mb"] = round(mem.used / (1024 ** 2), 2)
        stats["ram"]["total_mb"] = round(mem.total / (1024 ** 2), 2)
        stats["ram"]["free_mb"] = round(mem.available / (1024 ** 2), 2)
        
        swap = psutil.swap_memory()
        stats["swap"]["percent"] = swap.percent
        stats["swap"]["used_mb"] = round(swap.used / (1024 ** 2), 2)
        stats["swap"]["total_mb"] = round(swap.total / (1024 ** 2), 2)
        
        disk = psutil.disk_usage('/')
        stats["disk"]["percent"] = disk.percent
        stats["disk"]["used_gb"] = round(disk.used / (1024 ** 3), 2)
        stats["disk"]["total_gb"] = round(disk.total / (1024 ** 3), 2)
        stats["disk"]["free_gb"] = round(disk.free / (1024 ** 3), 2)
        
        net = psutil.net_io_counters()
        stats["network"]["sent_mb"] = round(net.bytes_sent / (1024 ** 2), 2)
        stats["network"]["recv_mb"] = round(net.bytes_recv / (1024 ** 2), 2)
        stats["network"]["packets_sent"] = net.packets_sent
        stats["network"]["packets_recv"] = net.packets_recv
        
        stats["processes"] = len(psutil.pids())
        
        try:
            if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp = int(f.read().strip()) / 1000
                    stats["temperature"] = f"{temp:.1f}°C"
        except:
            pass
        
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                stats["uptime_hours"] = round(uptime_seconds / 3600, 2)
        except:
            stats["uptime_hours"] = round((time.time() - START_TIME) / 3600, 2)
        
        stats["bot_uptime_hours"] = round((time.time() - START_TIME) / 3600, 2)
        
    except Exception as e:
        logger.error(f"Error getting VPS stats: {e}")
    
    return stats

def get_top_processes(n=5):
    """Get top n processes by CPU usage"""
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append(proc.info)
            except:
                pass
        processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        return processes[:n]
    except:
        return []

def create_progress_bar(percent, length=20):
    """Create a progress bar string"""
    filled = min(length, int(percent / (100 / length)))
    return "█" * filled + "░" * (length - filled)

def format_vps_stats():
    """Format VPS stats for display"""
    stats = get_vps_stats()
    top_procs = get_top_processes(5)
    
    uptime = stats["bot_uptime_hours"]
    days = int(uptime // 24)
    hours = int(uptime % 24)
    uptime_str = f"{days}d {hours}h" if days > 0 else f"{uptime:.2f}h"
    
    load = stats["cpu"]["load"]
    load_str = f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}" if load else "N/A"
    
    ram_bar = create_progress_bar(stats["ram"]["percent"])
    disk_bar = create_progress_bar(stats["disk"]["percent"])
    
    proc_text = ""
    for i, p in enumerate(top_procs, 1):
        name = p.get('name', 'Unknown')[:18]
        cpu = p.get('cpu_percent', 0)
        mem = p.get('memory_percent', 0)
        pid = p.get('pid', '?')
        proc_text += f"  {i}. <code>{name}</code> CPU: {cpu:.1f}% RAM: {mem:.1f}%\n"
    
    if not proc_text:
        proc_text = "  No active processes"
    
    text = f"""
╔═══════════════════════════════════════════════════════╗
║              🖥️ <b>VPS MONITOR</b>                      ║
╚═══════════════════════════════════════════════════════╝

📊 <b>CPU</b>
├─ Usage: <code>{stats['cpu']['percent']:.1f}%</code>
├─ Cores: <code>{stats['cpu']['count']}</code>
├─ Freq: <code>{stats['cpu']['freq']:.2f} GHz</code>
└─ Load: <code>{load_str}</code>

💾 <b>RAM</b>
├─ Usage: <code>{stats['ram']['percent']:.1f}%</code>
├─ [{ram_bar}]
├─ Used: <code>{stats['ram']['used_mb']:.0f} MB</code>
├─ Free: <code>{stats['ram']['free_mb']:.0f} MB</code>
├─ Total: <code>{stats['ram']['total_mb']:.0f} MB</code>
└─ Swap: <code>{stats['swap']['percent']:.1f}%</code> ({stats['swap']['used_mb']:.0f}/{stats['swap']['total_mb']:.0f} MB)

💿 <b>DISK</b>
├─ Usage: <code>{stats['disk']['percent']:.1f}%</code>
├─ [{disk_bar}]
├─ Used: <code>{stats['disk']['used_gb']:.2f} GB</code>
├─ Free: <code>{stats['disk']['free_gb']:.2f} GB</code>
└─ Total: <code>{stats['disk']['total_gb']:.2f} GB</code>

🌐 <b>NETWORK</b>
├─ Upload: <code>{stats['network']['sent_mb']:.2f} MB</code>
├─ Download: <code>{stats['network']['recv_mb']:.2f} MB</code>
├─ Packets Out: <code>{stats['network']['packets_sent']:,}</code>
└─ Packets In: <code>{stats['network']['packets_recv']:,}</code>

⚡ <b>BOT</b>
├─ Uptime: <code>{uptime_str}</code>
├─ Temp: <code>{stats['temperature']}</code>
├─ Processes: <code>{stats['processes']}</code>
├─ Users: <code>{len(active_users) if active_users else 0}</code>
├─ Files: <code>{sum(len(f) for f in user_files.values()) if user_files else 0}</code>
├─ Running: <code>{len(bot_scripts) if bot_scripts else 0}</code>
├─ Python: <code>{stats['python_version']}</code>
└─ Platform: <code>{stats['platform']}</code>

🔝 <b>TOP PROCESSES</b>
{proc_text}
"""
    return text

# ========================================================================
# MONITORING THREAD
# ========================================================================

def monitor_loop():
    """Background thread for system monitoring"""
    logger.info("🔄 System monitor thread started")
    
    while True:
        try:
            stats = get_vps_stats()
            
            # Alert on high memory usage
            if stats["ram"]["percent"] > 90:
                try:
                    bot.send_message(
                        OWNER_ID,
                        f"⚠️ <b>High Memory Alert</b>\n\n"
                        f"RAM Usage: <code>{stats['ram']['percent']:.1f}%</code>\n"
                        f"Used: <code>{stats['ram']['used_mb']:.0f} MB</code>\n"
                        f"Total: <code>{stats['ram']['total_mb']:.0f} MB</code>",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            # Log stats every hour
            if int(time.time()) % 3600 == 0:
                logger.info(
                    f"📊 Stats: CPU: {stats['cpu']['percent']:.1f}%, "
                    f"RAM: {stats['ram']['percent']:.1f}%, "
                    f"Disk: {stats['disk']['percent']:.1f}%, "
                    f"Users: {len(active_users)}, "
                    f"Scripts: {len(bot_scripts)}"
                )
            
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(60)

def start_monitor_thread():
    """Start the system monitoring thread"""
    thread = Thread(target=monitor_loop, daemon=True)
    thread.start()
    logger.info("📊 System monitor thread started")

# ========================================================================
# DATABASE SETUP (KEEPING YOUR EXISTING)
# ========================================================================

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pending_uploads
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL, file_name TEXT NOT NULL,
                      file_type TEXT NOT NULL, pending_path TEXT NOT NULL,
                      chat_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                      created_at TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS system_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      event_type TEXT, user_id INTEGER, details TEXT,
                      timestamp TEXT DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry date format for user {user_id}: {expiry}. Skipping.")

        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# ========================================================================
# HELPER FUNCTIONS (YOUR EXISTING)
# ========================================================================

def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except:
                    pass
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"Error checking process status for {script_key}: {e}")
            return False
    return False

def kill_process_tree(process_info):
    try:
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                    except:
                        pass
                parent.kill()
            except psutil.NoSuchProcess:
                pass
    except Exception as e:
        logger.error(f"Error killing process: {e}")
    
    log_file = process_info.get('log_file')
    if log_file and hasattr(log_file, 'close') and not log_file.closed:
        try:
            log_file.close()
        except:
            pass

# ========================================================================
# DATABASE OPERATIONS (YOUR EXISTING)
# ========================================================================

DB_LOCK = threading.Lock()

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
            logger.info(f"Saved file '{file_name}' ({file_type}) for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error saving file for user {user_id}, {file_name}: {e}")
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]:
                    del user_files[user_id]
            logger.info(f"Removed file '{file_name}' for user {user_id} from DB")
        except Exception as e:
            logger.error(f"❌ Error removing file for {user_id}, {file_name}: {e}")
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            logger.info(f"Added/Confirmed active user {user_id} in DB")
        except Exception as e:
            logger.error(f"❌ Error adding active user {user_id}: {e}")
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
            logger.info(f"Saved subscription for {user_id}, expiry {expiry_str}")
        except Exception as e:
            logger.error(f"❌ Error saving subscription for {user_id}: {e}")
        finally:
            conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions:
                del user_subscriptions[user_id]
            logger.info(f"Removed subscription for {user_id} from DB")
        except Exception as e:
            logger.error(f"❌ Error removing subscription for {user_id}: {e}")
        finally:
            conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id)
            logger.info(f"Added admin {admin_id} to DB")
        except Exception as e:
            logger.error(f"❌ Error adding admin {admin_id}: {e}")
        finally:
            conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        logger.warning("Attempted to remove OWNER_ID from admins.")
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('SELECT 1 FROM admins WHERE user_id = ?', (admin_id,))
            if c.fetchone():
                c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
                conn.commit()
                admin_ids.discard(admin_id)
                logger.info(f"Removed admin {admin_id} from DB")
                return True
            else:
                admin_ids.discard(admin_id)
                return False
        except Exception as e:
            logger.error(f"❌ Error removing admin {admin_id}: {e}")
            return False
        finally:
            conn.close()

def create_pending_upload(user_id, file_name, file_type, pending_path, chat_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO pending_uploads
                   (user_id, file_name, file_type, pending_path, chat_id, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)''',
                (user_id, file_name, file_type, pending_path, chat_id, datetime.now().isoformat()),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

def get_pending_upload(upload_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            row = conn.execute(
                '''SELECT id, user_id, file_name, file_type, pending_path, chat_id, status
                   FROM pending_uploads WHERE id = ?''', (upload_id,)
            ).fetchone()
            return row
        finally:
            conn.close()

def update_pending_upload_status(upload_id, status):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('UPDATE pending_uploads SET status = ? WHERE id = ?', (status, upload_id))
            conn.commit()
        finally:
            conn.close()

def list_pending_uploads():
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            return conn.execute(
                '''SELECT id, user_id, file_name, file_type, pending_path, chat_id, status
                   FROM pending_uploads WHERE status = 'pending' ORDER BY id ASC'''
            ).fetchall()
        finally:
            conn.close()

def delete_pending_upload(upload_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        try:
            conn.execute('DELETE FROM pending_uploads WHERE id = ?', (upload_id,))
            conn.commit()
        finally:
            conn.close()

# ========================================================================
# TELEGRAM MODULES MAPPING (YOUR EXISTING)
# ========================================================================

TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'pillow': 'Pillow',
    # GUI libraries are unavailable in the hosting environment. The headless
    # wheel also avoids common cv2 native-loader failures on Python 3.13.
    'cv2': 'opencv-python-headless',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'psutil': 'psutil',
    'asyncio': None,
    'json': None,
    'datetime': None,
    'os': None,
    'sys': None,
    're': None,
    'time': None,
    'math': None,
    'random': None,
    'logging': None,
    'threading': None,
    'subprocess': None,
    'zipfile': None,
    'tempfile': None,
    'shutil': None,
    'sqlite3': None,
    'atexit': None,
}

# ========================================================================
# AUTO-INSTALL & SCRIPT RUNNING (YOUR EXISTING)
# ========================================================================

def _python_candidates():
    candidates = [sys.executable, 'python3', 'python']
    result = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)
    return result

def _pip_command():
    for python_cmd in _python_candidates():
        try:
            check = subprocess.run(
                [python_cmd, '-m', 'pip', '--version'],
                capture_output=True, text=True, timeout=15,
                encoding='utf-8', errors='ignore'
            )
            if check.returncode == 0:
                return [python_cmd, '-m', 'pip']
        except (OSError, subprocess.SubprocessError):
            continue

    for python_cmd in _python_candidates():
        try:
            ensure = subprocess.run(
                [python_cmd, '-m', 'ensurepip', '--upgrade'],
                capture_output=True, text=True, timeout=60,
                encoding='utf-8', errors='ignore'
            )
            if ensure.returncode == 0:
                check = subprocess.run(
                    [python_cmd, '-m', 'pip', '--version'],
                    capture_output=True, text=True, timeout=15,
                    encoding='utf-8', errors='ignore'
                )
                if check.returncode == 0:
                    logger.info("pip bootstrapped successfully for %s", python_cmd)
                    return [python_cmd, '-m', 'pip']
            else:
                logger.warning("ensurepip failed for %s: %s", python_cmd, ensure.stderr[-500:])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Unable to bootstrap pip for %s: %s", python_cmd, exc)

    for pip_cmd in ('pip3', 'pip'):
        try:
            check = subprocess.run(
                [pip_cmd, '--python', sys.executable, '--version'],
                capture_output=True, text=True,
                timeout=15, encoding='utf-8', errors='ignore'
            )
            if check.returncode == 0:
                return [pip_cmd, '--python', sys.executable]
        except (OSError, subprocess.SubprocessError):
            continue
    return None

def pip_install(requirements_or_package, message=None):
    pip_cmd = _pip_command()
    if not pip_cmd:
        return False, "No working pip was found."
    command = pip_cmd + ['install'] + list(requirements_or_package)
    logger.info("Running pip install: %s", ' '.join(command))
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False,
            timeout=600, encoding='utf-8', errors='ignore'
        )
        output = (result.stderr or result.stdout or '').strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "pip install timed out."
    except Exception as exc:
        return False, str(exc)

def pip_uninstall(packages):
    """Remove conflicting packages from the shared Python runtime."""
    pip_cmd = _pip_command()
    if not pip_cmd:
        return False, "No working pip was found."
    command = pip_cmd + ['uninstall', '-y'] + list(packages)
    logger.info("Running pip uninstall for conflicting packages.")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False,
            timeout=600, encoding='utf-8', errors='ignore'
        )
        output = (result.stderr or result.stdout or '').strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "pip uninstall timed out."
    except Exception as exc:
        return False, str(exc)

def verify_cv2_import():
    """Verify cv2 in the exact interpreter used to run uploaded scripts."""
    try:
        result = subprocess.run(
            [sys.executable, '-c', 'import cv2; print(cv2.__version__)'],
            capture_output=True, text=True, check=False,
            timeout=30, encoding='utf-8', errors='ignore'
        )
        output = (result.stdout or result.stderr or '').strip()
        return result.returncode == 0, output
    except Exception as exc:
        return False, str(exc)

def repair_cv2_runtime(message=None):
    """Replace GUI OpenCV wheels with a server-compatible headless wheel."""
    if message:
        bot.reply_to(
            message,
            "🔧 OpenCV import failed. Repairing the server-compatible headless package..."
        )

    # All of these distributions install the same `cv2` module and can leave
    # mixed native files behind when more than one is installed.
    pip_uninstall([
        'opencv-python',
        'opencv-contrib-python',
        'opencv-python-headless',
        'opencv-contrib-python-headless',
    ])
    success, output = pip_install(
        ['--upgrade', '--force-reinstall', 'opencv-python-headless'],
        message
    )
    if not success:
        logger.error("Failed to repair cv2 runtime: %s", output)
        return False

    verified, version_or_error = verify_cv2_import()
    if verified:
        logger.info("cv2 repaired successfully: %s", version_or_error)
        if message:
            bot.reply_to(message, f"✅ OpenCV repaired ({version_or_error}). Retrying script...")
        return True

    logger.error("cv2 is still unavailable after repair: %s", version_or_error)
    if message:
        bot.reply_to(
            message,
            "❌ OpenCV repair failed. Please use opencv-python-headless in requirements.txt."
        )
    return False

def is_cv2_import_error(stdout, stderr):
    """Detect both missing-cv2 and broken-native-loader tracebacks."""
    combined = f"{stdout}\n{stderr}".lower()
    if 'cv2' not in combined:
        return False
    return any(
        marker in combined
        for marker in (
            'import cv2',
            'from cv2',
            'cv2/__init__.py',
            "no module named 'cv2'",
            'no module named "cv2"',
        )
    )

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        logger.info(f"Module '{module_name}' is core. Skipping pip install.")
        return False
    try:
        if module_name.lower() == 'cv2':
            return repair_cv2_runtime(message)
        bot.reply_to(message, f"🐍 Module `{module_name}` not found. Installing `{package_name}`...", parse_mode='Markdown')
        success, output = pip_install([package_name], message)
        if success:
            logger.info(f"Installed {package_name}. Output:\n{output}")
            bot.reply_to(message, f"✅ Package `{package_name}` (for `{module_name}`) installed.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ Failed to install `{package_name}` for `{module_name}`.\nLog:\n```\n{output}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000:
                error_msg = error_msg[:4000] + "\n... (Log truncated)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except Exception as e:
        error_msg = f"❌ Error installing `{package_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"🟠 Node package `{module_name}` not found. Installing locally...", parse_mode='Markdown')
        command = ['npm', 'install', module_name]
        logger.info(f"Running npm install: {' '.join(command)} in {user_folder}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            logger.info(f"Installed {module_name}. Output:\n{result.stdout}")
            bot.reply_to(message, f"✅ Node package `{module_name}` installed locally.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ Failed to install Node package `{module_name}`.\nLog:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000:
                error_msg = error_msg[:4000] + "\n... (Log truncated)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except FileNotFoundError:
        error_msg = "❌ Error: 'npm' not found. Ensure Node.js/npm are installed and in PATH."
        logger.error(error_msg)
        bot.reply_to(message, error_msg)
        return False
    except Exception as e:
        error_msg = f"❌ Error installing Node package `{module_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts. Check logs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run Python script: {script_path} (Key: {script_key})")

    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Error: Script '{file_name}' not found!")
            logger.error(f"Script not found: {script_path}")
            if script_owner_id in user_files:
                user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
            remove_user_file_db(script_owner_id, file_name)
            return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            logger.info(f"Running Python pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            bot.reply_to(message_obj_for_reply, f"🔄 Install successful. Retrying '{file_name}'...")
                            time.sleep(0.5)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Install failed. Cannot run '{file_name}'.")
                            return
                    elif is_cv2_import_error(stdout, stderr) and repair_cv2_runtime(message_obj_for_reply):
                        bot.reply_to(message_obj_for_reply, f"🔄 OpenCV repair successful. Retrying '{file_name}'...")
                        time.sleep(0.5)
                        threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                        return
                    else:
                        error_summary = stderr[:500]
                        bot.reply_to(message_obj_for_reply, f"❌ Error in script pre-check:\n```\n{error_summary}\n```\nFix the script.", parse_mode='Markdown')
                        return
            except subprocess.TimeoutExpired:
                logger.info("Python Pre-check timed out, proceeding to long run.")
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except Exception as e:
                logger.error(f"Error in Python pre-check: {e}")
                bot.reply_to(message_obj_for_reply, f"❌ Unexpected error in script pre-check: {e}")
                return
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Failed to open log file '{log_file_path}': {e}")
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return

        process = None
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, encoding='utf-8', errors='ignore'
            )
            
            bot_scripts[script_key] = {
                'process': process,
                'log_file': log_file,
                'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(),
                'user_folder': user_folder,
                'type': 'py',
                'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ Python script '{file_name}' started! (PID: {process.pid})")
            
        except Exception as e:
            if log_file and not log_file.closed:
                log_file.close()
            error_msg = f"❌ Error starting Python script '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts:
                del bot_scripts[script_key]
                
    except Exception as e:
        error_msg = f"❌ Unexpected error running Python script '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ Failed to run '{file_name}' after {max_attempts} attempts. Check logs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run JS script: {script_path}")

    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj_for_reply, f"❌ Error: Script '{file_name}' not found!")
            logger.error(f"JS Script not found: {script_path}")
            if script_owner_id in user_files:
                user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
            remove_user_file_db(script_owner_id, file_name)
            return

        if attempt == 1:
            check_command = ['node', script_path]
            logger.info(f"Running JS pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                            if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                                bot.reply_to(message_obj_for_reply, f"🔄 NPM Install successful. Retrying '{file_name}'...")
                                time.sleep(0.5)
                                threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                return
                            else:
                                bot.reply_to(message_obj_for_reply, f"❌ NPM Install failed. Cannot run '{file_name}'.")
                                return
                    error_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ Error in JS script pre-check:\n```\n{error_summary}\n```\nFix the script.", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                logger.info("JS Pre-check timed out, proceeding to long run.")
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()
            except FileNotFoundError:
                error_msg = "❌ Error: 'node' not found. Ensure Node.js is installed."
                logger.error(error_msg)
                bot.reply_to(message_obj_for_reply, error_msg)
                return
            except Exception as e:
                logger.error(f"Error in JS pre-check: {e}")
                bot.reply_to(message_obj_for_reply, f"❌ Unexpected error in JS pre-check: {e}")
                return
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill()
                    check_proc.communicate()

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        try:
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"Failed to open log file '{log_file_path}': {e}")
            bot.reply_to(message_obj_for_reply, f"❌ Failed to open log file: {e}")
            return

        process = None
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, encoding='utf-8', errors='ignore'
            )
            
            bot_scripts[script_key] = {
                'process': process,
                'log_file': log_file,
                'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(),
                'user_folder': user_folder,
                'type': 'js',
                'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ JS script '{file_name}' started! (PID: {process.pid})")
            
        except Exception as e:
            if log_file and not log_file.closed:
                log_file.close()
            error_msg = f"❌ Error starting JS script '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts:
                del bot_scripts[script_key]
                
    except Exception as e:
        error_msg = f"❌ Unexpected error running JS script '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])
            del bot_scripts[script_key]

# ========================================================================
# FILE HANDLING (YOUR EXISTING)
# ========================================================================

def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        logger.info(f"Temp dir for zip: {temp_dir}")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file_content)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
            logger.info(f"Extracted zip to {temp_dir}")

        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            logger.info(f"requirements.txt found, installing: {req_path}")
            bot.reply_to(message, f"🔄 Installing Python deps from `{req_file}`...")
            try:
                success, output = pip_install(['-r', req_path], message)
                if not success:
                    raise RuntimeError(output)
                logger.info(f"pip install from requirements.txt OK. Output:\n{output}")
                bot.reply_to(message, f"✅ Python deps from `{req_file}` installed.")
            except Exception as e:
                error_msg = f"❌ Failed to install Python deps from `{req_file}`.\nLog:\n```\n{e}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000:
                    error_msg = error_msg[:4000] + "\n... (Log truncated)"
                bot.reply_to(message, error_msg, parse_mode='Markdown')
                return

        if pkg_json:
            logger.info(f"package.json found, npm install in: {temp_dir}")
            bot.reply_to(message, f"🔄 Installing Node deps from `{pkg_json}`...")
            try:
                command = ['npm', 'install']
                result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=temp_dir, encoding='utf-8', errors='ignore')
                logger.info(f"npm install OK. Output:\n{result.stdout}")
                bot.reply_to(message, f"✅ Node deps from `{pkg_json}` installed.")
            except FileNotFoundError:
                bot.reply_to(message, "❌ 'npm' not found. Cannot install Node deps.")
                return
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ Failed to install Node deps from `{pkg_json}`.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000:
                    error_msg = error_msg[:4000] + "\n... (Log truncated)"
                bot.reply_to(message, error_msg, parse_mode='Markdown')
                return
            except Exception as e:
                error_msg = f"❌ Unexpected error installing Node deps: {e}"
                logger.error(error_msg, exc_info=True)
                bot.reply_to(message, error_msg)
                return

        main_script_name = None
        file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']
        preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        for p in preferred_py:
            if p in py_files:
                main_script_name = p
                file_type = 'py'
                break
        if not main_script_name:
            for p in preferred_js:
                if p in js_files:
                    main_script_name = p
                    file_type = 'js'
                    break
        if not main_script_name:
            if py_files:
                main_script_name = py_files[0]
                file_type = 'py'
            elif js_files:
                main_script_name = js_files[0]
                file_type = 'js'
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` script found in archive!")
            return

        logger.info(f"Moving extracted files from {temp_dir} to {user_folder}")
        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path):
                shutil.rmtree(dest_path)
            elif os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(src_path, dest_path)

        save_user_file(user_id, main_script_name, file_type)
        logger.info(f"Saved main script '{main_script_name}' ({file_type}) for {user_id} from zip.")
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Files extracted. Starting main script: `{main_script_name}`...", parse_mode='Markdown')

        if file_type == 'py':
            threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()

    except zipfile.BadZipFile as e:
        logger.error(f"Bad zip file from {user_id}: {e}")
        bot.reply_to(message, f"❌ Error: Invalid/corrupted ZIP. {e}")
    except Exception as e:
        logger.error(f"❌ Error processing zip for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned temp dir: {temp_dir}")
            except Exception as e:
                logger.error(f"Failed to clean temp dir {temp_dir}: {e}", exc_info=True)

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Error processing JS file {file_name} for {script_owner_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing JS file: {str(e)}")

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ Error processing Python file {file_name} for {script_owner_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing Python file: {str(e)}")

# ========================================================================
# MENU CREATION (YOUR EXISTING)
# ========================================================================

def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]

    if user_id in admin_ids:
        admin_buttons = [
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot',
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All User Scripts', callback_data='run_all_scripts'),
            types.InlineKeyboardButton('🖥️ VPS Monitor', callback_data='vps_monitor')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(admin_buttons[1], admin_buttons[3])
        markup.add(admin_buttons[2], admin_buttons[5])
        markup.add(admin_buttons[6])
        markup.add(admin_buttons[4])
        markup.add(buttons[4])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3])
        markup.add(types.InlineKeyboardButton('📊 Statistics', callback_data='stats'))
        markup.add(buttons[4])
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('📥 Pending Files', callback_data='pending_uploads'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_upload_review_markup(upload_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ Approve & Run", callback_data=f"approve_upload_{upload_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_upload_{upload_id}"),
    )
    return markup

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner"]
]
ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["🖥️ VPS Monitor"]
]

# ========================================================================
# LOGIC FUNCTIONS (YOUR EXISTING)
# ========================================================================

def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked by admin. Try later.")
        return

    user_bio = "Could not fetch bio"
    photo_file_id = None
    try:
        user_bio = bot.get_chat(user_id).bio or "No bio"
    except:
        pass
    try:
        user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)
        if user_profile_photos.photos:
            photo_file_id = user_profile_photos.photos[0][-1].file_id
    except:
        pass

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = (f"🎉 New user!\n👤 Name: {user_name}\n✳️ User: @{user_username or 'N/A'}\n"
                                  f"🆔 ID: `{user_id}`\n📝 Bio: {user_bio}")
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
            if photo_file_id:
                bot.send_photo(OWNER_ID, photo_file_id, caption=f"Pic of new user {user_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to notify owner about new user {user_id}: {e}")

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"
            days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Subscription expires in: {days_left} days"
        else:
            user_status = "🆓 Free User (Expired Sub)"
            remove_subscription_db(user_id)
    else:
        user_status = "🆓 Free User"

    welcome_msg_text = (f"〽️ Welcome, {user_name}!\n\n🆔 Your User ID: `{user_id}`\n"
                        f"✳️ Username: `@{user_username or 'Not set'}`\n"
                        f"🔰 Your Status: {user_status}{expiry_info}\n"
                        f"📁 Files Uploaded: {current_files} / {limit_str}\n\n"
                        f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                        f"   Upload single scripts or `.zip` archives.\n\n"
                        f"👇 Use buttons or type commands.")
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    try:
        if photo_file_id:
            bot.send_photo(chat_id, photo_file_id)
        bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error sending welcome to {user_id}: {e}", exc_info=True)
        try:
            bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
        except Exception as fallback_e:
            logger.error(f"Fallback send_message failed for {user_id}: {fallback_e}")

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=UPDATE_CHANNEL))
    bot.reply_to(message, "Visit our Updates Channel:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked by admin, cannot accept files.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached. Delete files first.")
        return
    bot.reply_to(message, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, "📂 Your files:\n\n(No files uploaded yet)")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    bot.reply_to(message, "📂 Your files:\nClick to manage.", reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time_ping = time.time()
    wait_msg = bot.reply_to(message, "🏃 Testing speed...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_time_ping) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID:
            user_level = "👑 Owner"
        elif user_id in admin_ids:
            user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
            user_level = "⭐ Premium"
        else:
            user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"👤 Your Level: {user_level}")
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"Error during speed test: {e}", exc_info=True)
        bot.edit_message_text("❌ Error during speed test.", chat_id, wait_msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact Owner:", reply_markup=markup)

def _logic_vps_monitor(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    
    stats_text = format_vps_stats()
    try:
        bot.reply_to(message, stats_text, parse_mode='HTML')
    except Exception as e:
        # Send as file if too long
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(stats_text)
                f.flush()
                with open(f.name, 'rb') as doc:
                    bot.send_document(message.chat.id, doc, caption="📊 VPS System Stats")
                os.unlink(f.name)
        except:
            bot.reply_to(message, f"❌ Error: {str(e)}")

# --- Admin Logic Functions ---
def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "💳 Subscription Management\nUse inline buttons from /start or admin command menu.", reply_markup=create_subscription_menu())

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files_records = sum(len(files) for files in user_files.values())

    running_bots_count = 0
    user_running_bots = 0

    for script_key_iter, script_info_iter in list(bot_scripts.items()):
        s_owner_id, _ = script_key_iter.split('_', 1)
        if is_bot_running(int(s_owner_id), script_info_iter['file_name']):
            running_bots_count += 1
            if int(s_owner_id) == user_id:
                user_running_bots += 1

    stats_msg_base = (f"📊 Bot Statistics:\n\n"
                      f"👥 Total Users: {total_users}\n"
                      f"📂 Total File Records: {total_files_records}\n"
                      f"🟢 Total Active Bots: {running_bots_count}\n")

    if user_id in admin_ids:
        stats_msg_admin = (f"🔒 Bot Status: {'🔴 Locked' if bot_locked else '🟢 Unlocked'}\n"
                           f"🤖 Your Running Bots: {user_running_bots}")
        stats_msg = stats_msg_base + stats_msg_admin
    else:
        stats_msg = stats_msg_base + f"🤖 Your Running Bots: {user_running_bots}"

    bot.reply_to(message, stats_msg)

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    msg = bot.reply_to(message, "📢 Send message to broadcast to all active users.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    logger.warning(f"Bot {status} by Admin {message.from_user.id} via command/button.")
    bot.reply_to(message, f"🔒 Bot has been {status}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    bot.reply_to(message, "👑 Admin Panel\nManage admins. Use inline buttons from /start or admin menu.",
                 reply_markup=create_admin_panel())

def _logic_run_all_scripts(message_or_call):
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.chat.id
        reply_func = lambda text, **kwargs: bot.reply_to(message_or_call, text, **kwargs)
        admin_message_obj_for_script_runner = message_or_call
    elif isinstance(message_or_call, telebot.types.CallbackQuery):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kwargs: bot.send_message(admin_chat_id, text, **kwargs)
        admin_message_obj_for_script_runner = message_or_call.message
    else:
        logger.error("Invalid argument for _logic_run_all_scripts")
        return

    if admin_user_id not in admin_ids:
        reply_func("⚠️ Admin permissions required.")
        return

    reply_func("⏳ Starting process to run all user scripts. This may take a while...")
    logger.info(f"Admin {admin_user_id} initiated 'run all scripts' from chat {admin_chat_id}.")

    started_count = 0
    attempted_users = 0
    skipped_files = 0
    error_files_details = []

    all_user_files_snapshot = dict(user_files)

    for target_user_id, files_for_user in all_user_files_snapshot.items():
        if not files_for_user:
            continue
        attempted_users += 1
        logger.info(f"Processing scripts for user {target_user_id}...")
        user_folder = get_user_folder(target_user_id)

        for file_name, file_type in files_for_user:
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    logger.info(f"Admin {admin_user_id} attempting to start '{file_name}' ({file_type}) for user {target_user_id}.")
                    try:
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj_for_script_runner)).start()
                            started_count += 1
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj_for_script_runner)).start()
                            started_count += 1
                        else:
                            logger.warning(f"Unknown file type '{file_type}' for {file_name} (user {target_user_id}). Skipping.")
                            error_files_details.append(f"`{file_name}` (User {target_user_id}) - Unknown type")
                            skipped_files += 1
                        time.sleep(0.2)
                    except Exception as e:
                        logger.error(f"Error queueing start for '{file_name}' (user {target_user_id}): {e}")
                        error_files_details.append(f"`{file_name}` (User {target_user_id}) - Start error")
                        skipped_files += 1
                else:
                    logger.warning(f"File '{file_name}' for user {target_user_id} not found at '{file_path}'. Skipping.")
                    error_files_details.append(f"`{file_name}` (User {target_user_id}) - File not found")
                    skipped_files += 1

    summary_msg = (f"✅ All Users' Scripts - Processing Complete:\n\n"
                   f"▶️ Attempted to start: {started_count} scripts.\n"
                   f"👥 Users processed: {attempted_users}.\n")
    if skipped_files > 0:
        summary_msg += f"⚠️ Skipped/Error files: {skipped_files}\n"
        if error_files_details:
            summary_msg += "Details (first 5):\n" + "\n".join([f"  - {err}" for err in error_files_details[:5]])
            if len(error_files_details) > 5:
                summary_msg += "\n  ... and more (check logs)."

    reply_func(summary_msg, parse_mode='Markdown')
    logger.info(f"Run all scripts finished. Admin: {admin_user_id}. Started: {started_count}. Skipped/Errors: {skipped_files}")

# ========================================================================
# COMMAND HANDLERS
# ========================================================================

@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_show_status(message):
    _logic_statistics(message)

@bot.message_handler(commands=['vps'])
def command_vps_monitor(message):
    _logic_vps_monitor(message)

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "🖥️ VPS Monitor": _logic_vps_monitor,
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func:
        logic_func(message)
    else:
        logger.warning(f"Button text '{message.text}' matched but no logic func.")

@bot.message_handler(commands=['updateschannel'])
def command_updates_channel(message):
    _logic_updates_channel(message)

@bot.message_handler(commands=['uploadfile'])
def command_upload_file(message):
    _logic_upload_file(message)

@bot.message_handler(commands=['checkfiles'])
def command_check_files(message):
    _logic_check_files(message)

@bot.message_handler(commands=['botspeed'])
def command_bot_speed(message):
    _logic_bot_speed(message)

@bot.message_handler(commands=['contactowner'])
def command_contact_owner(message):
    _logic_contact_owner(message)

@bot.message_handler(commands=['subscriptions'])
def command_subscriptions(message):
    _logic_subscriptions_panel(message)

@bot.message_handler(commands=['statistics'])
def command_statistics(message):
    _logic_statistics(message)

@bot.message_handler(commands=['broadcast'])
def command_broadcast(message):
    _logic_broadcast_init(message)

@bot.message_handler(commands=['lockbot'])
def command_lock_bot(message):
    _logic_toggle_lock_bot(message)

@bot.message_handler(commands=['adminpanel'])
def command_admin_panel(message):
    _logic_admin_panel(message)

@bot.message_handler(commands=['pending'])
def command_pending_uploads(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin permissions required.")
        return
    pending_items = list_pending_uploads()
    if not pending_items:
        bot.reply_to(message, "📥 Pending uploads မရှိပါ။")
        return
    for row in pending_items[:30]:
        bot.send_message(
            message.chat.id,
            f"📥 Request #{row[0]}\nUser: `{row[1]}`\nFile: `{row[2]}` ({row[3]})",
            reply_markup=create_upload_review_markup(row[0]),
            parse_mode='Markdown',
        )

@bot.message_handler(commands=['runningallcode'])
def command_run_all_code(message):
    _logic_run_all_scripts(message)

@bot.message_handler(commands=['ping'])
def ping(message):
    start_ping_time = time.time()
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start_ping_time) * 1000, 2)
    bot.edit_message_text(f"Pong! Latency: {latency} ms", message.chat.id, msg.message_id)

# ========================================================================
# DOCUMENT HANDLER (YOUR EXISTING)
# ========================================================================

@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    doc = message.document
    logger.info(f"Doc from {user_id}: {doc.file_name} ({doc.mime_type}), Size: {doc.file_size}")

    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked, cannot accept files.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached. Delete files via /checkfiles.")
        return

    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "⚠️ No file name. Ensure file has a name.")
        return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Unsupported type! Only `.py`, `.js`, `.zip` allowed.")
        return
    max_file_size = 20 * 1024 * 1024
    if doc.file_size > max_file_size:
        bot.reply_to(message, f"⚠️ File too large (Max: {max_file_size // 1024 // 1024} MB).")
        return

    try:
        download_wait_msg = bot.reply_to(message, f"⏳ Downloading `{file_name}` for admin review...")
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)
        pending_name = f"{user_id}_{int(time.time() * 1000)}_{os.path.basename(file_name)}"
        pending_path = os.path.join(PENDING_UPLOADS_DIR, pending_name)
        with open(pending_path, 'wb') as pending_file:
            pending_file.write(downloaded_file_content)
        file_type = file_ext.lstrip('.')
        upload_id = create_pending_upload(user_id, file_name, file_type, pending_path, chat_id)
        bot.delete_message(chat_id, download_wait_msg.message_id)
        _send_upload_for_admin_review(upload_id, user_id, file_name, file_type, pending_path, message)
        logger.info("Upload %s from user %s is pending admin approval.", upload_id, user_id)
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API Error handling file for {user_id}: {e}", exc_info=True)
        if "file is too big" in str(e).lower():
            bot.reply_to(message, f"❌ Telegram API Error: File too large to download (~20MB limit).")
        else:
            bot.reply_to(message, f"❌ Telegram API Error: {str(e)}. Try later.")
    except Exception as e:
        logger.error(f"❌ General error handling file for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Unexpected error: {str(e)}")

def _send_upload_for_admin_review(upload_id, user_id, file_name, file_type, pending_path, message):
    caption = (
        f"📥 New file approval request\n"
        f"👤 User: `{user_id}`\n"
        f"📄 File: `{file_name}` ({file_type})\n"
        f"🆔 Request: `{upload_id}`\n\n"
        "Approve လုပ်ပြီးမှသာ file ကို install/run လုပ်ပါမယ်။"
    )
    with open(pending_path, 'rb') as upload_file:
        bot.send_document(
            OWNER_ID,
            upload_file,
            caption=caption,
            parse_mode='Markdown',
            reply_markup=create_upload_review_markup(upload_id),
        )
    if ADMIN_ID != OWNER_ID:
        with open(pending_path, 'rb') as upload_file:
            bot.send_document(
                ADMIN_ID,
                upload_file,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=create_upload_review_markup(upload_id),
            )
    bot.reply_to(message, f"⏳ `{file_name}` ကို admin approval စောင့်နေပါတယ်။", parse_mode='Markdown')

def process_approved_upload(upload_id, reviewer_id):
    pending = get_pending_upload(upload_id)
    if not pending:
        return False, "Pending upload not found."
    _, user_id, file_name, file_type, pending_path, chat_id, status = pending
    if status != 'pending':
        return False, f"This upload is already {status}."
    if not os.path.exists(pending_path):
        update_pending_upload_status(upload_id, 'missing')
        return False, "Pending file is missing from storage."
    if get_user_file_count(user_id) >= get_user_file_limit(user_id):
        update_pending_upload_status(upload_id, 'rejected')
        try:
            os.remove(pending_path)
        except OSError:
            pass
        return False, f"User `{user_id}` has reached the file limit."

    update_pending_upload_status(upload_id, 'approved')
    user_folder = get_user_folder(user_id)
    try:
        with open(pending_path, 'rb') as pending_file:
            content = pending_file.read()
        if file_type == 'zip':
            source_message = bot.send_message(
                chat_id,
                f"✅ Admin approved `{file_name}`. Processing your ZIP now.",
                parse_mode='Markdown',
            )
            handle_zip_file(content, file_name, source_message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as target_file:
                target_file.write(content)
            source_message = bot.send_message(
                chat_id,
                f"✅ Admin approved `{file_name}`. Starting it now.",
                parse_mode='Markdown',
            )
            if file_type == 'js':
                handle_js_file(file_path, user_id, user_folder, file_name, source_message)
            else:
                handle_py_file(file_path, user_id, user_folder, file_name, source_message)
        os.remove(pending_path)
        return True, f"Approved `{file_name}` for user `{user_id}`."
    except Exception as exc:
        update_pending_upload_status(upload_id, 'failed')
        logger.error("Error processing approved upload %s: %s", upload_id, exc, exc_info=True)
        return False, f"Approved, but processing failed: {exc}"

# ========================================================================
# CALLBACK HANDLERS (YOUR EXISTING + VPS)
# ========================================================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: User={user_id}, Data='{data}'")

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked by admin.", show_alert=True)
        return
    try:
        if data == 'upload':
            upload_callback(call)
        elif data == 'check_files':
            check_files_callback(call)
        elif data.startswith('file_'):
            file_control_callback(call)
        elif data.startswith('start_'):
            start_bot_callback(call)
        elif data.startswith('stop_'):
            stop_bot_callback(call)
        elif data.startswith('restart_'):
            restart_bot_callback(call)
        elif data.startswith('delete_'):
            delete_bot_callback(call)
        elif data.startswith('logs_'):
            logs_bot_callback(call)
        elif data == 'speed':
            speed_callback(call)
        elif data == 'back_to_main':
            back_to_main_callback(call)
        elif data.startswith('confirm_broadcast_'):
            handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast':
            handle_cancel_broadcast(call)
        elif data == 'vps_monitor':
            vps_monitor_callback(call)
        elif data == 'subscription':
            admin_required_callback(call, subscription_management_callback)
        elif data == 'stats':
            stats_callback(call)
        elif data == 'lock_bot':
            admin_required_callback(call, lock_bot_callback)
        elif data == 'unlock_bot':
            admin_required_callback(call, unlock_bot_callback)
        elif data == 'run_all_scripts':
            admin_required_callback(call, run_all_scripts_callback)
        elif data == 'broadcast':
            admin_required_callback(call, broadcast_init_callback)
        elif data == 'admin_panel':
            admin_required_callback(call, admin_panel_callback)
        elif data == 'pending_uploads':
            admin_required_callback(call, pending_uploads_callback)
        elif data.startswith('review_upload_'):
            admin_required_callback(call, review_upload_callback)
        elif data.startswith('approve_upload_'):
            admin_required_callback(call, approve_upload_callback)
        elif data.startswith('reject_upload_'):
            admin_required_callback(call, reject_upload_callback)
        elif data == 'add_admin':
            owner_required_callback(call, add_admin_init_callback)
        elif data == 'remove_admin':
            owner_required_callback(call, remove_admin_init_callback)
        elif data == 'list_admins':
            admin_required_callback(call, list_admins_callback)
        elif data == 'add_subscription':
            admin_required_callback(call, add_subscription_init_callback)
        elif data == 'remove_subscription':
            admin_required_callback(call, remove_subscription_init_callback)
        elif data == 'check_subscription':
            admin_required_callback(call, check_subscription_init_callback)
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
            logger.warning(f"Unhandled callback data: {data} from user {user_id}")
    except Exception as e:
        logger.error(f"Error handling callback '{data}' for {user_id}: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "Error processing request.", show_alert=True)
        except:
            pass

def admin_required_callback(call, func_to_run):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True)
        return
    func_to_run(call)

def owner_required_callback(call, func_to_run):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner permissions required.", show_alert=True)
        return
    func_to_run(call)

def upload_callback(call):
    user_id = call.from_user.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.answer_callback_query(call.id, f"⚠️ File limit ({current_files}/{limit_str}) reached.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def check_files_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.answer_callback_query(call.id, "⚠️ No files uploaded.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
            bot.edit_message_text("📂 Your files:\n\n(No files uploaded)", chat_id, call.message.message_id, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error editing msg for empty file list: {e}")
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 Your files:\nClick to manage.", chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error editing msg for file list: {e}")

def file_control_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            logger.warning(f"User {requesting_user_id} tried to access file '{file_name}' of user {script_owner_id} without permission.")
            bot.answer_callback_query(call.id, "⚠️ You can only manage your own files.", show_alert=True)
            check_files_callback(call)
            return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            logger.warning(f"File '{file_name}' not found for user {script_owner_id} during control.")
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call)
            return

        bot.answer_callback_query(call.id)
        is_running = is_bot_running(script_owner_id, file_name)
        status_text = '🟢 Running' if is_running else '🔴 Stopped'
        file_type = next((f[1] for f in user_files_list if f[0] == file_name), '?')
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_running),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error updating controls: {e}")
    except Exception as e:
        logger.error(f"Error in file_control_callback: {e}")
        bot.answer_callback_query(call.id, "An error occurred.", show_alert=True)

def start_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
            return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call)
            return

        file_type = file_info[1]
        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Error: File `{file_name}` missing!", show_alert=True)
            remove_user_file_db(script_owner_id, file_name)
            check_files_callback(call)
            return

        if is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, f"⚠️ Script '{file_name}' already running.", show_alert=True)
            return

        bot.answer_callback_query(call.id, f"⏳ Attempting to start {file_name}...")

        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
            bot.send_message(chat_id_for_reply, f"❌ Error: Unknown file type '{file_type}' for '{file_name}'.")
            return

        time.sleep(0.5)
        is_now_running = is_bot_running(script_owner_id, file_name)
        status_text = '🟢 Running' if is_now_running else '🟡 Starting (or failed)'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` ({file_type}) of User `{script_owner_id}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error updating start status: {e}")
    except Exception as e:
        logger.error(f"Error in start_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error starting script.", show_alert=True)

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
            return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call)
            return

        if not is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, f"⚠️ Script '{file_name}' already stopped.", show_alert=True)
            return

        script_key = f"{script_owner_id}_{file_name}"
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts:
                del bot_scripts[script_key]

        bot.answer_callback_query(call.id, f"⏹️ Stopped {file_name}")
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` of User `{script_owner_id}`\nStatus: 🔴 Stopped",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, False),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error updating stop status: {e}")
    except Exception as e:
        logger.error(f"Error in stop_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error stopping script.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
            return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call)
            return

        script_key = f"{script_owner_id}_{file_name}"
        if is_bot_running(script_owner_id, file_name):
            process_info = bot_scripts.get(script_key)
            if process_info:
                kill_process_tree(process_info)
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            time.sleep(0.5)

        file_type = file_info[1]
        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Error: File `{file_name}` missing!", show_alert=True)
            remove_user_file_db(script_owner_id, file_name)
            check_files_callback(call)
            return

        bot.answer_callback_query(call.id, f"🔄 Restarting {file_name}...")

        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
            bot.send_message(chat_id_for_reply, f"❌ Unknown type '{file_type}' for '{file_name}'.")
            return

        time.sleep(0.5)
        is_now_running = is_bot_running(script_owner_id, file_name)
        status_text = '🟢 Running' if is_now_running else '🟡 Starting (or failed)'
        try:
            bot.edit_message_text(
                f"⚙️ Controls for: `{file_name}` of User `{script_owner_id}`\nStatus: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error updating restart status: {e}")
    except Exception as e:
        logger.error(f"Error in restart_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error restarting.", show_alert=True)

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
            return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call)
            return

        bot.answer_callback_query(call.id, f"🗑️ Deleting {file_name}...")

        script_key = f"{script_owner_id}_{file_name}"
        if is_bot_running(script_owner_id, file_name):
            process_info = bot_scripts.get(script_key)
            if process_info:
                kill_process_tree(process_info)
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            time.sleep(0.5)

        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")

        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting {file_path}: {e}")

        if os.path.exists(log_path):
            try:
                os.remove(log_path)
                logger.info(f"Deleted log: {log_path}")
            except Exception as e:
                logger.error(f"Error deleting log {log_path}: {e}")

        remove_user_file_db(script_owner_id, file_name)

        try:
            bot.edit_message_text(
                f"🗑️ File `{file_name}` deleted!",
                chat_id_for_reply, call.message.message_id,
                reply_markup=None,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing delete message: {e}")
            bot.send_message(chat_id_for_reply, f"🗑️ File `{file_name}` deleted.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in delete_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error deleting.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
            return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True)
            check_files_callback(call)
            return

        user_folder = get_user_folder(script_owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")

        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, f"⚠️ No logs for '{file_name}'.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()

            if len(log_content) > 4096:
                log_content = log_content[-4096:]
                log_content = "...\n" + log_content

            if not log_content.strip():
                log_content = "(Log empty)"

            bot.send_message(
                chat_id_for_reply,
                f"📜 Logs for `{file_name}` (User `{script_owner_id}`):\n```\n{log_content}\n```",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error reading log: {e}")
            bot.send_message(chat_id_for_reply, f"❌ Error reading log for `{file_name}`.")
    except Exception as e:
        logger.error(f"Error in logs_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error fetching logs.", show_alert=True)

def speed_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    start_cb_ping_time = time.time()
    try:
        bot.edit_message_text("🏃 Testing speed...", chat_id, call.message.message_id)
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_cb_ping_time) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID:
            user_level = "👑 Owner"
        elif user_id in admin_ids:
            user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
            user_level = "⭐ Premium"
        else:
            user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"👤 Your Level: {user_level}")
        bot.answer_callback_query(call.id)
        bot.edit_message_text(speed_msg, chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
    except Exception as e:
        logger.error(f"Error during speed test (cb): {e}")
        bot.answer_callback_query(call.id, "Error in speed test.", show_alert=True)

def back_to_main_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    expiry_info = ""
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"
            days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Subscription expires in: {days_left} days"
        else:
            user_status = "🆓 Free User (Expired Sub)"
    else:
        user_status = "🆓 Free User"
    main_menu_text = (f"〽️ Welcome back, {call.from_user.first_name}!\n\n🆔 ID: `{user_id}`\n"
                      f"🔰 Status: {user_status}{expiry_info}\n📁 Files: {current_files} / {limit_str}\n\n"
                      f"👇 Use buttons or type commands.")
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(main_menu_text, chat_id, call.message.message_id,
                              reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error handling back_to_main: {e}")

def vps_monitor_callback(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin permissions required.", show_alert=True)
        return
    stats_text = format_vps_stats()
    bot.answer_callback_query(call.id)
    try:
        bot.send_message(call.message.chat.id, stats_text, parse_mode='HTML')
    except Exception as e:
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(stats_text)
                f.flush()
                with open(f.name, 'rb') as doc:
                    bot.send_document(call.message.chat.id, doc, caption="📊 VPS System Stats")
                os.unlink(f.name)
        except:
            bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}")

# ========================================================================
# ADMIN CALLBACKS (YOUR EXISTING)
# ========================================================================

def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 Subscription Management\nSelect action:",
                              call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
    except Exception as e:
        logger.error(f"Error showing sub menu: {e}")

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e:
        logger.error(f"Error updating menu after stats_callback: {e}")

def lock_bot_callback(call):
    global bot_locked
    bot_locked = True
    logger.warning(f"Bot locked by Admin {call.from_user.id}")
    bot.answer_callback_query(call.id, "🔒 Bot locked.")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e:
        logger.error(f"Error updating menu (lock): {e}")

def unlock_bot_callback(call):
    global bot_locked
    bot_locked = False
    logger.warning(f"Bot unlocked by Admin {call.from_user.id}")
    bot.answer_callback_query(call.id, "🔓 Bot unlocked.")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e:
        logger.error(f"Error updating menu (unlock): {e}")

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call)

def pending_uploads_callback(call):
    pending_items = list_pending_uploads()
    bot.answer_callback_query(call.id)
    if not pending_items:
        text = "📥 Pending uploads\n\nမရှိပါ။"
        markup = create_admin_panel()
    else:
        text = "📥 Pending uploads:\n\n" + "\n".join(
            f"• `{row[0]}` — `{row[2]}` from `{row[1]}`" for row in pending_items[:30]
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        for row in pending_items[:30]:
            markup.add(types.InlineKeyboardButton(
                f"Review #{row[0]}: {row[2][:30]}",
                callback_data=f"review_upload_{row[0]}",
            ))
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    except Exception as exc:
        logger.error("Could not show pending uploads: %s", exc)

def review_upload_callback(call):
    try:
        upload_id = int(call.data.rsplit('_', 1)[1])
        pending = get_pending_upload(upload_id)
        if not pending or pending[6] != 'pending':
            bot.answer_callback_query(call.id, "This request is no longer pending.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        _, user_id, file_name, file_type, pending_path, _, _ = pending
        bot.send_message(
            call.message.chat.id,
            f"📥 Request #{upload_id}\nUser: `{user_id}`\nFile: `{file_name}` ({file_type})",
            reply_markup=create_upload_review_markup(upload_id),
            parse_mode='Markdown',
        )
    except Exception as e:
        logger.error(f"Review upload error: {e}")
        bot.answer_callback_query(call.id, "Invalid upload request.", show_alert=True)

def approve_upload_callback(call):
    try:
        upload_id = int(call.data.rsplit('_', 1)[1])
        bot.answer_callback_query(call.id, "Approving and processing...")
        success, result = process_approved_upload(upload_id, call.from_user.id)
        try:
            bot.edit_message_caption(result, call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            bot.edit_message_text(result, call.message.chat.id, call.message.message_id, reply_markup=None)
        if not success:
            logger.warning("Upload approval %s failed: %s", upload_id, result)
    except Exception as exc:
        logger.error("Approve upload callback failed: %s", exc)
        bot.answer_callback_query(call.id, "Approval failed.", show_alert=True)

def reject_upload_callback(call):
    try:
        upload_id = int(call.data.rsplit('_', 1)[1])
        pending = get_pending_upload(upload_id)
        if not pending or pending[6] != 'pending':
            bot.answer_callback_query(call.id, "This request is no longer pending.", show_alert=True)
            return
        update_pending_upload_status(upload_id, 'rejected')
        if os.path.exists(pending[4]):
            os.remove(pending[4])
        bot.answer_callback_query(call.id, "Rejected.")
        rejection_text = f"❌ Rejected `{pending[2]}` from user `{pending[1]}`."
        try:
            bot.edit_message_caption(rejection_text, call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            bot.edit_message_text(rejection_text, call.message.chat.id, call.message.message_id, reply_markup=None)
        try:
            bot.send_message(pending[5], f"❌ Admin က `{pending[2]}` ကို reject လုပ်လိုက်ပါတယ်။")
        except Exception as exc:
            logger.warning("Could not notify rejected upload owner: %s", exc)
    except Exception as exc:
        logger.error("Reject upload callback failed: %s", exc)
        bot.answer_callback_query(call.id, "Reject failed.", show_alert=True)

def broadcast_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Send message to broadcast.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Broadcast cancelled.")
        return

    broadcast_content = message.text
    if not broadcast_content:
        bot.reply_to(message, "⚠️ Cannot broadcast empty message.")
        return

    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Confirm & Send", callback_data=f"confirm_broadcast_{message.message_id}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast"))

    preview_text = broadcast_content[:1000].strip() if broadcast_content else "(Media message)"
    bot.reply_to(message, f"⚠️ Confirm Broadcast:\n\n```\n{preview_text}\n```\n"
                          f"To **{target_count}** users. Sure?", reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if user_id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    try:
        original_message = call.message.reply_to_message
        if not original_message:
            raise ValueError("Could not retrieve original message.")

        broadcast_text = original_message.text
        if not broadcast_text:
            raise ValueError("Message has no text.")

        bot.answer_callback_query(call.id, "🚀 Starting broadcast...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...",
                              chat_id, call.message.message_id, reply_markup=None)

        thread = Thread(target=execute_broadcast, args=(broadcast_text, chat_id))
        thread.start()
    except ValueError as ve:
        logger.error(f"Error retrieving msg for broadcast confirm: {ve}")
        bot.edit_message_text(f"❌ Error starting broadcast: {ve}", chat_id, call.message.message_id, reply_markup=None)
    except Exception as e:
        logger.error(f"Error in handle_confirm_broadcast: {e}")
        bot.edit_message_text("❌ Unexpected error during broadcast confirm.", chat_id, call.message.message_id, reply_markup=None)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Broadcast cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

def execute_broadcast(broadcast_text, admin_chat_id):
    sent_count = 0
    failed_count = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid, broadcast_text, parse_mode='HTML')
            sent_count += 1
            time.sleep(0.05)
        except:
            failed_count += 1

    result_msg = f"📢 Broadcast Complete!\n\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}\n👥 Targets: {len(active_users)}"
    logger.info(result_msg)
    try:
        bot.send_message(admin_chat_id, result_msg)
    except Exception as e:
        logger.error(f"Failed to send broadcast result to admin {admin_chat_id}: {e}")

def admin_panel_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👑 Admin Panel\nManage admins (Owner actions may be restricted).",
                              call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
    except Exception as e:
        logger.error(f"Error showing admin panel: {e}")

def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter User ID to promote to Admin.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    owner_id_check = message.from_user.id
    if owner_id_check != OWNER_ID:
        bot.reply_to(message, "⚠️ Owner only.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Admin promotion cancelled.")
        return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id <= 0:
            raise ValueError("ID must be positive")
        if new_admin_id == OWNER_ID:
            bot.reply_to(message, "⚠️ Owner is already Owner.")
            return
        if new_admin_id in admin_ids:
            bot.reply_to(message, f"⚠️ User `{new_admin_id}` already Admin.")
            return
        add_admin_db(new_admin_id)
        logger.warning(f"Admin {new_admin_id} added by Owner {owner_id_check}.")
        bot.reply_to(message, f"✅ User `{new_admin_id}` promoted to Admin.")
        try:
            bot.send_message(new_admin_id, "🎉 Congrats! You are now an Admin.")
        except Exception as e:
            logger.error(f"Failed to notify new admin {new_admin_id}: {e}")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "👑 Enter User ID to promote or /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)
    except Exception as e:
        logger.error(f"Error processing add admin: {e}")
        bot.reply_to(message, "Error.")

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter User ID of Admin to remove.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    owner_id_check = message.from_user.id
    if owner_id_check != OWNER_ID:
        bot.reply_to(message, "⚠️ Owner only.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Admin removal cancelled.")
        return
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove <= 0:
            raise ValueError("ID must be positive")
        if admin_id_remove == OWNER_ID:
            bot.reply_to(message, "⚠️ Owner cannot remove self.")
            return
        if admin_id_remove not in admin_ids:
            bot.reply_to(message, f"⚠️ User `{admin_id_remove}` not Admin.")
            return
        if remove_admin_db(admin_id_remove):
            logger.warning(f"Admin {admin_id_remove} removed by Owner {owner_id_check}.")
            bot.reply_to(message, f"✅ Admin `{admin_id_remove}` removed.")
            try:
                bot.send_message(admin_id_remove, "ℹ️ You are no longer an Admin.")
            except Exception as e:
                logger.error(f"Failed to notify removed admin {admin_id_remove}: {e}")
        else:
            bot.reply_to(message, f"❌ Failed to remove admin `{admin_id_remove}`.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "👑 Enter Admin ID to remove or /cancel.")
        bot.register_next_step_handler(msg, process_remove_admin_id)
    except Exception as e:
        logger.error(f"Error processing remove admin: {e}")
        bot.reply_to(message, "Error.")

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    try:
        admin_list_str = "\n".join(f"- `{aid}` {'(Owner)' if aid == OWNER_ID else ''}" for aid in sorted(list(admin_ids)))
        if not admin_list_str:
            admin_list_str = "(No Owner/Admins configured!)"
        bot.edit_message_text(f"👑 Current Admins:\n\n{admin_list_str}", call.message.chat.id,
                              call.message.message_id, reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error listing admins: {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID & days (e.g., `12345678 30`).\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Sub add cancelled.")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError("Incorrect format")
        sub_user_id = int(parts[0].strip())
        days = int(parts[1].strip())
        if sub_user_id <= 0 or days <= 0:
            raise ValueError("User ID/days must be positive")

        current_expiry = user_subscriptions.get(sub_user_id, {}).get('expiry')
        start_date_new_sub = datetime.now()
        if current_expiry and current_expiry > start_date_new_sub:
            start_date_new_sub = current_expiry
        new_expiry = start_date_new_sub + timedelta(days=days)
        save_subscription(sub_user_id, new_expiry)

        logger.info(f"Sub for {sub_user_id} by admin {admin_id_check}. Expiry: {new_expiry:%Y-%m-%d}")
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` by {days} days.\nNew expiry: {new_expiry:%Y-%m-%d}")
        try:
            bot.send_message(sub_user_id, f"🎉 Sub activated/extended by {days} days! Expires: {new_expiry:%Y-%m-%d}.")
        except Exception as e:
            logger.error(f"Failed to notify {sub_user_id} of new sub: {e}")
    except ValueError as e:
        bot.reply_to(message, f"⚠️ Invalid: {e}. Format: `ID days` or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID & days, or /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription_details)
    except Exception as e:
        logger.error(f"Error processing add sub: {e}")
        bot.reply_to(message, "Error.")

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to remove sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Sub removal cancelled.")
        return
    try:
        sub_user_id_remove = int(message.text.strip())
        if sub_user_id_remove <= 0:
            raise ValueError("ID must be positive")
        if sub_user_id_remove not in user_subscriptions:
            bot.reply_to(message, f"⚠️ User `{sub_user_id_remove}` no active sub in memory.")
            return
        remove_subscription_db(sub_user_id_remove)
        logger.warning(f"Sub removed for {sub_user_id_remove} by admin {admin_id_check}.")
        bot.reply_to(message, f"✅ Sub for `{sub_user_id_remove}` removed.")
        try:
            bot.send_message(sub_user_id_remove, "ℹ️ Your subscription removed by admin.")
        except Exception as e:
            logger.error(f"Failed to notify {sub_user_id_remove} of sub removal: {e}")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID to remove sub from, or /cancel.")
        bot.register_next_step_handler(msg, process_remove_subscription_id)
    except Exception as e:
        logger.error(f"Error processing remove sub: {e}")
        bot.reply_to(message, "Error.")

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to check sub.\n/cancel to abort.")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "Sub check cancelled.")
        return
    try:
        sub_user_id_check = int(message.text.strip())
        if sub_user_id_check <= 0:
            raise ValueError("ID must be positive")
        if sub_user_id_check in user_subscriptions:
            expiry_dt = user_subscriptions[sub_user_id_check].get('expiry')
            if expiry_dt:
                if expiry_dt > datetime.now():
                    days_left = (expiry_dt - datetime.now()).days
                    bot.reply_to(message, f"✅ User `{sub_user_id_check}` active sub.\nExpires: {expiry_dt:%Y-%m-%d %H:%M:%S} ({days_left} days left).")
                else:
                    bot.reply_to(message, f"⚠️ User `{sub_user_id_check}` expired sub (On: {expiry_dt:%Y-%m-%d %H:%M:%S}).")
                    remove_subscription_db(sub_user_id_check)
            else:
                bot.reply_to(message, f"⚠️ User `{sub_user_id_check}` in sub list, but expiry missing.")
        else:
            bot.reply_to(message, f"ℹ️ User `{sub_user_id_check}` no active sub record.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID. Send numerical ID or /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Enter User ID to check, or /cancel.")
        bot.register_next_step_handler(msg, process_check_subscription_id)
    except Exception as e:
        logger.error(f"Error processing check sub: {e}")
        bot.reply_to(message, "Error.")

# ========================================================================
# CLEANUP
# ========================================================================

def cleanup():
    logger.warning("Shutdown. Cleaning up processes...")
    script_keys_to_stop = list(bot_scripts.keys())
    if not script_keys_to_stop:
        logger.info("No scripts running. Exiting.")
        return
    logger.info(f"Stopping {len(script_keys_to_stop)} scripts...")
    for key in script_keys_to_stop:
        if key in bot_scripts:
            logger.info(f"Stopping: {key}")
            kill_process_tree(bot_scripts[key])
        else:
            logger.info(f"Script {key} already removed.")
    logger.warning("Cleanup finished.")

atexit.register(cleanup)

# ========================================================================
# MAIN
# ========================================================================

if __name__ == '__main__':
    logger.info("="*40 + "\n🤖 Bot Starting Up...\n" + f"🐍 Python: {sys.version.split()[0]}\n" +
                f"🔧 Base Dir: {BASE_DIR}\n📁 Upload Dir: {UPLOAD_BOTS_DIR}\n" +
                f"📊 Data Dir: {IROTECH_DIR}\n🔑 Owner ID: {OWNER_ID}\n🛡️ Admins: {admin_ids}\n" + "="*40)
    
    keep_alive()
    start_monitor_thread()
    
    logger.info("🚀 Starting polling...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("Polling ReadTimeout. Restarting in 5s...")
            time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Polling ConnectionError: {ce}. Retrying in 15s...")
            time.sleep(15)
        except Exception as e:
            logger.critical(f"💥 Unrecoverable polling error: {e}", exc_info=True)
            logger.info("Restarting polling in 30s due to critical error...")
            time.sleep(30)
        finally:
            logger.warning("Polling attempt finished. Will restart if in loop.")
            time.sleep(1)
