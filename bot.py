from datetime import datetime, timedelta
import hashlib
import os
import re
import sqlite3
import threading
import time

# اضافه شدن Flask برای آنلاین نگه‌داشتن ۲۴ ساعته
from flask import Flask
import telebot
from telebot import types
import yt_dlp

# ==================== تنظیمات اولیه ====================
BOT_TOKEN = "8207519315:AAH23dplvIFKX_eu9-i0Ow4ZI-zz5zGb5NM"
MAIN_ADMIN_ID = 8443938939  # آیدی عددی ادمین اصلی
SUPPORT_ID = "AFIX00"  # آیدی پشتیبانی بدون @

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== سرور وب (۲۴ ساعته) ====================
app = Flask("")


@app.route("/")
def home():
  return "Bot is alive and running 24/7! 🚀"


def run_web():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  t = threading.Thread(target=run_web, daemon=True)
  t.start()


# ==================== دیتابیس SQLITE ====================
def init_db():
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY,"
      " usage_count INTEGER DEFAULT 0, join_date TEXT)"
  )

  try:
    cursor.execute("ALTER TABLE users ADD COLUMN join_date TEXT")
  except Exception:
    pass

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS forced_joins (
            chat_id TEXT PRIMARY KEY,
            link TEXT,
            chat_type TEXT,
            target_limit INTEGER DEFAULT -1,
            joined_count INTEGER DEFAULT 0,
            expire_timestamp REAL DEFAULT -1
        )
    """)
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS user_verified (user_id INTEGER,"
      " chat_id TEXT, PRIMARY KEY(user_id, chat_id))"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
  )
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            url_hash TEXT PRIMARY KEY, 
            file_id TEXT, 
            file_type TEXT, 
            caption TEXT
        )
    """)
  try:
    cursor.execute("ALTER TABLE cache ADD COLUMN caption TEXT")
  except Exception:
    pass

  cursor.execute(
      "CREATE TABLE IF NOT EXISTS pending_urls (id TEXT PRIMARY KEY, url TEXT)"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS vip_users (user_id INTEGER PRIMARY KEY,"
      " expire_timestamp REAL)"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)"
  )

  cursor.execute("INSERT OR REPLACE INTO admins VALUES (?)", (MAIN_ADMIN_ID,))

  default_welcome = (
      "🔥 سلام<b> {first_name} </b>عزیز! خوش اومدی! 👋\n\n"
      "🤖 **به ربات هوشمند آلفا دانلودر خوش اومدی.**\n"
      "من اینجام تا کمکت کنم ویدیوها و محتویات دلخواهت رو خیلی سریع و باکیفیت"
      " دانلود کنی:\n\n"
      "📥 **اینستاگرام:** دانلود ریلز، پست و استوری با بالاترین کیفیت\n"
      "📺 **یوتیوب:** دانلود ویدیو با رزولوشن‌های مختلف + تبدیل سریع به صوت"
      " MP3\n"
      "📱 **تیک‌تاک:** دانلود ویدیوها بدون واترمارک\n"
      "📝 **کپشن‌ساز:** ارسال کامل متن و توضیحات ویدیو همراه با فایل\n\n"
      "⚡ **برای شروع، کافیه لینک ویدیوت رو برام بفرستی تا در چند ثانیه تحویلت"
      " بدم!**"
  )
  cursor.execute(
      "INSERT OR IGNORE INTO settings VALUES ('welcome_msg', ?)",
      (default_welcome,),
  )
  cursor.execute(
      "INSERT OR IGNORE INTO settings VALUES ('theme_color', 'blue')"
  )
  cursor.execute(
      "INSERT OR IGNORE INTO settings VALUES ('bot_status', 'active')"
  )
  conn.commit()
  conn.close()


init_db()


# ==================== توابع کمکی ====================
def is_admin(user_id):
  if int(user_id) == int(MAIN_ADMIN_ID):
    return True
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
  res = cursor.fetchone()
  conn.close()
  return res is not None


def is_bot_active():
  return get_setting("bot_status") == "active"


def save_pending_url(url):
  url_id = hashlib.md5(url.encode()).hexdigest()[:10]
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "INSERT OR REPLACE INTO pending_urls VALUES (?, ?)", (url_id, url)
  )
  conn.commit()
  conn.close()
  return url_id


def get_pending_url(url_id):
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT url FROM pending_urls WHERE id=?", (url_id,))
  res = cursor.fetchone()
  conn.close()
  return res[0] if res else None


def get_setting(key):
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
  res = cursor.fetchone()
  conn.close()
  return res[0] if res else ""


def set_setting(key, value):
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
  conn.commit()
  conn.close()


def get_theme_emoji():
  theme = get_setting("theme_color")
  if theme == "green":
    return "🟢", "✅"
  elif theme == "red":
    return "🔴", "❌"
  else:
    return "🔵", "🔹"


def add_user(user_id):
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
  exists = cursor.fetchone()
  now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
  if not exists:
    cursor.execute(
        "INSERT INTO users (user_id, usage_count, join_date) VALUES (?, 1,"
        " ?)",
        (user_id, now_str),
    )
  else:
    cursor.execute(
        "UPDATE users SET usage_count = usage_count + 1, join_date ="
        " COALESCE(join_date, ?) WHERE user_id=?",
        (now_str, user_id),
    )
  conn.commit()
  conn.close()


def is_user_vip(user_id):
  if is_admin(user_id):
    return True
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT expire_timestamp FROM vip_users WHERE user_id=?", (user_id,)
  )
  res = cursor.fetchone()
  conn.close()
  if res:
    if time.time() < res[0]:
      return True
    else:
      c_conn = sqlite3.connect("downloader_bot.db")
      c = c_conn.cursor()
      c.execute("DELETE FROM vip_users WHERE user_id=?", (user_id,))
      c_conn.commit()
      c_conn.close()
  return False


# ==================== مدیریت جوین اجباری ====================
def check_and_clean_forced_joins():
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  now = time.time()
  cursor.execute(
      "SELECT chat_id, target_limit, joined_count, expire_timestamp FROM"
      " forced_joins"
  )
  channels = cursor.fetchall()
  for chat_id, target, joined, expire in channels:
    if (target != -1 and joined >= target) or (expire != -1 and now >= expire):
      cursor.execute("DELETE FROM forced_joins WHERE chat_id=?", (chat_id,))
  conn.commit()
  conn.close()


def auto_cleaner_thread():
  while True:
    try:
      check_and_clean_forced_joins()
    except Exception:
      pass
    time.sleep(60)


threading.Thread(target=auto_cleaner_thread, daemon=True).start()


def get_active_forced_joins():
  check_and_clean_forced_joins()
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT chat_id, link, chat_type, target_limit, joined_count,"
      " expire_timestamp FROM forced_joins LIMIT 5"
  )
  rows = cursor.fetchall()
  conn.close()
  return rows


def check_user_joined(user_id):
  if is_user_vip(user_id):
    return []
  active_list = get_active_forced_joins()
  not_joined = []
  for chat_id, link, chat_type, limit, count, expire in active_list:
    try:
      member = bot.get_chat_member(chat_id=chat_id, user_id=user_id)
      if member.status in ["left", "kicked"]:
        not_joined.append((chat_id, link, chat_type))
    except Exception:
      not_joined.append((chat_id, link, chat_type))
  return not_joined


# ==================== دستور /START ====================
@bot.message_handler(commands=["start"])
def start_cmd(message):
  user_id = message.from_user.id
  first_name = message.from_user.first_name or "دوست"
  add_user(user_id)

  if not is_bot_active() and not is_admin(user_id):
    bot.send_message(
        message.chat.id,
        "🚧 <b>ربات در حال حاضر برای بروزرسانی و تعمیرات موقتاً خاموش است."
        "</b>\nلطفاً بعداً مراجعه کنید.",
    )
    return

  not_joined = check_user_joined(user_id)
  if not_joined:
    icon, _ = get_theme_emoji()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for idx, (ch_id, link, c_type) in enumerate(not_joined, 1):
      title = "کانال" if c_type == "channel" else "گروه"
      kb.add(
          types.InlineKeyboardButton(
              text=f"{icon} عضویت در {title} شماره {idx}", url=link
          )
      )
    kb.add(
        types.InlineKeyboardButton(
            text="🔄 بررسی عضویت", callback_data="check_join"
        )
    )
    kb.add(
        types.InlineKeyboardButton(
            text="⭐ خرید اشتراک VIP (رد شدن از جوین اجباری)",
            callback_data="buy_vip_stars",
        )
    )
    bot.send_message(
        message.chat.id,
        f"⚠️ <b>{first_name} عزیز، برای استفاده از خدمات ربات، ابتدا باید در کانال/گروه‌های زیر عضو شوید یا اشتراک VIP تهیه کنید:</b>",
        reply_markup=kb,
    )
    return

  icon, _ = get_theme_emoji()
  raw_welcome = get_setting("welcome_msg")
  welcome_text = raw_welcome.replace("{first_name}", first_name)

  kb = types.InlineKeyboardMarkup(row_width=2)
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} اینستاگرام", callback_data="ask_link_insta"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} یوتیوب", callback_data="ask_link_yt"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} تیک‌تاک", callback_data="ask_link_tiktok"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="👤 پروفایل و حساب من", callback_data="member_profile"
      ),
      types.InlineKeyboardButton(
          text="❓ راهنمای استفاده", callback_data="member_help"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🚀 استارت مجدد ربات", callback_data="restart_bot_action"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="⭐ خرید اشتراک VIP", callback_data="buy_vip_stars"
      ),
      types.InlineKeyboardButton(
          text="👤 پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      ),
  )

  if is_admin(user_id):
    kb.add(
        types.InlineKeyboardButton(
            text="⚙️ پنل مدیریت ربات (مالک)", callback_data="open_admin_panel"
        )
    )

  bot.send_message(
      message.chat.id, welcome_text, reply_markup=kb, parse_mode="HTML"
  )


@bot.callback_query_handler(func=lambda call: call.data == "restart_bot_action")
def restart_bot_callback(call):
  try:
    bot.answer_callback_query(call.id, "🚀 ربات مجدداً استارت شد!")
  except Exception:
    pass
  try:
    bot.delete_message(call.message.chat.id, call.message.message_id)
  except Exception:
    pass
  start_cmd(call.message)


# ==================== پروفایل و راهنما ====================
@bot.callback_query_handler(func=lambda call: call.data == "member_profile")
def member_profile_callback(call):
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  user_id = call.from_user.id
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT usage_count, join_date FROM users WHERE user_id=?", (user_id,)
  )
  user_data = cursor.fetchone()
  conn.close()

  usage = user_data[0] if user_data else 0
  join_d = user_data[1] if user_data and user_data[1] else "امروز"
  is_vip = is_user_vip(user_id)
  vip_str = (
      "⭐ فعال (کاربر ویژه VIP)"
      if is_vip
      else "🔹 عادی (دارای محدودیت جوین اجباری)"
  )

  text = (
      "👤 <b>پروفایل کاربری شما در آلفا دانلودر</b>\n\n"
      f"🆔 آیدی عددی: <code>{user_id}</code>\n"
      f"📊 تعداد کل دانلودها: <b>{usage}</b> فایل\n"
      f"⏳ وضعیت اشتراک: <b>{vip_str}</b>\n"
      f"📅 تاریخ عضویت: <code>{join_d}</code>"
  )
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 بازگشت به منوی اصلی", callback_data="back_to_home"
      )
  )
  try:
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "member_help")
def member_help_callback(call):
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  text = (
      "❓ <b>راهنمای کامل استفاده از ربات آلفا دانلودر</b>\n\n"
      "1️⃣ لینک ویدیو مورد نظر را از اینستاگرام، یوتیوب یا تیک‌تاک کپی کنید.\n"
      "2️⃣ لینک را در همین چت ارسال نمایید.\n"
      "3️⃣ کیفیت دلخواه (یا صوت MP3) را انتخاب کنید تا دریافتش کنید."
  )
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 بازگشت به منوی اصلی", callback_data="back_to_home"
      )
  )
  try:
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "back_to_home")
def back_to_home_callback(call):
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  try:
    bot.delete_message(call.message.chat.id, call.message.message_id)
  except Exception:
    pass
  start_cmd(call.message)


@bot.callback_query_handler(func=lambda call: call.data == "buy_vip_stars")
def buy_vip_stars_handler(call):
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  prices = [types.LabeledPrice(label="اشتراک VIP ۳۰ روزه ربات", amount=29)]
  try:
    bot.send_invoice(
        chat_id=call.message.chat.id,
        title="اشتراک VIP ربات آلفا دانلودر",
        description="معافیت کامل از جوین اجباری کانال‌ها",
        invoice_payload="vip_subscription_30d",
        provider_token="",
        currency="XTR",
        prices=prices,
    )
  except Exception as e:
    bot.send_message(call.message.chat.id, f"❌ خطا در ایجاد فاکتور: {e}")


@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout_handler(pre_checkout_query):
  bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@bot.message_handler(content_types=["successful_payment"])
def successful_payment_handler(message):
  user_id = message.from_user.id
  expire_timestamp = time.time() + (30 * 24 * 3600)
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "INSERT OR REPLACE INTO vip_users VALUES (?, ?)",
      (user_id, expire_timestamp),
  )
  conn.commit()
  conn.close()
  bot.send_message(
      message.chat.id,
      "🎉 <b>پرداخت موفق!</b> شما کاربر ویژه VIP شدید و محدودیت جوین اجباری از"
      " رویت برداشته شد. ❤️",
  )
  start_cmd(message)


@bot.callback_query_handler(func=lambda call: call.data.startswith("ask_link_"))
def ask_platform_link(call):
  platforms = {
      "ask_link_insta": "اینستاگرام",
      "ask_link_yt": "یوتیوب",
      "ask_link_tiktok": "تیک‌تاک",
  }
  p_name = platforms.get(call.data, "پلتفرم")
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 بازگشت به منوی اصلی", callback_data="back_to_home"
      )
  )
  bot.send_message(
      call.message.chat.id,
      f"📥 لطفاً <b>لینک ویدیو {p_name}</b> مورد نظرت رو ارسال کن:",
      reply_markup=kb,
  )


@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def verify_join_callback(call):
  user_id = call.from_user.id
  if check_user_joined(user_id):
    try:
      bot.answer_callback_query(
          call.id,
          "❌ هنوز در تمام کانال‌ها/گروه‌ها عضو نشده‌اید!",
          show_alert=True,
      )
    except Exception:
      pass
  else:
    try:
      bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد!")
    except Exception:
      pass
    try:
      bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
      pass
    start_cmd(call.message)


# ==================== پنل مدیریت پیشرفته ====================
def show_admin_panel_content(chat_id, message_id=None):
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT COUNT(*) FROM users")
  total_users = cursor.fetchone()[0]
  cursor.execute("SELECT SUM(usage_count) FROM users")
  total_usage = cursor.fetchone()[0] or 0
  cursor.execute("SELECT COUNT(*) FROM admins")
  total_admins = cursor.fetchone()[0]
  cursor.execute("SELECT COUNT(*) FROM vip_users")
  total_vip = cursor.fetchone()[0]
  cursor.execute("SELECT COUNT(*) FROM cache")
  total_cache = cursor.fetchone()[0] or 0
  conn.close()

  status_bot_str = "🟢 روشن و فعال" if is_bot_active() else "🔴 خاموش (تعمیرات)"

  text = (
      "👑 <b>پنل مدیریت پیشرفته آلفا دانلودر</b>\n\n"
      f"👥 کل کاربران: <code>{total_users}</code> نفر\n"
      f"📊 کل دانلودها: <code>{total_usage}</code> بار\n"
      f"⭐ کاربران VIP فعال: <code>{total_vip}</code> نفر\n"
      f"📦 فایل‌های ذخیره شده در کش: <code>{total_cache}</code> عدد\n"
      f"🛡️ تعداد ادمین‌ها: <code>{total_admins}</code> نفر\n"
      f"⚙️ وضعیت ربات: <b>{status_bot_str}</b>\n\n"
      "👇 بخش مورد نظر خود را انتخاب کنید:"
  )

  kb = types.InlineKeyboardMarkup(row_width=2)
  kb.add(
      types.InlineKeyboardButton(
          text="📢 مدیریت جوین اجباری", callback_data="adm_sec_fj"
      ),
      types.InlineKeyboardButton(
          text="🛡️ مدیریت ادمین‌ها", callback_data="adm_manage_admins"
      ),
      types.InlineKeyboardButton(
          text="📢 ارسال پیام همگانی", callback_data="adm_broadcast"
      ),
      types.InlineKeyboardButton(
          text="⭐ مدیریت کاربران VIP", callback_data="adm_sec_vip"
      ),
      types.InlineKeyboardButton(
          text="🧹 پاکسازی حافظه کش", callback_data="adm_clear_cache"
      ),
      types.InlineKeyboardButton(
          text="⚙️ تنظیمات عمومی", callback_data="adm_sec_settings"
      ),
      types.InlineKeyboardButton(
          text="📊 آمار تفصیلی", callback_data="adm_sec_stats"
      ),
      types.InlineKeyboardButton(
          text="🔄 روشن/خاموش ربات", callback_data="adm_toggle_bot"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 خروج و بازگشت به منوی کاربری", callback_data="back_to_home"
      )
  )

  if message_id:
    try:
      bot.edit_message_text(
          text, chat_id, message_id, reply_markup=kb, parse_mode="HTML"
      )
    except Exception:
      bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
  else:
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


@bot.message_handler(
    func=lambda m: m.text in ["⚙️ پنل مدیریت", "/admin"]
    or m.text == "پنل مدیریت"
)
def admin_panel_text(message):
  if not is_admin(message.from_user.id):
    bot.reply_to(message, "⛔ شما به پنل مدیریت دسترسی ندارید.")
    return
  show_admin_panel_content(message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data == "open_admin_panel")
def admin_panel_callback(call):
  if not is_admin(call.from_user.id):
    try:
      bot.answer_callback_query(call.id, "⛔ دسترسی غیرمجاز!", show_alert=True)
    except Exception:
      pass
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  show_admin_panel_content(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "adm_sec_fj")
def admin_section_fj(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  active_fj = get_active_forced_joins()
  fj_status = ""
  if active_fj:
    for idx, (ch_id, link, c_type, limit, count, expire) in enumerate(
        active_fj, 1
    ):
      limit_str = "بی‌نهایت" if limit == -1 else f"{count}/{limit}"
      fj_status += f"\n{idx}. <code>{ch_id}</code> ({c_type}) | سقف: {limit_str}"
  else:
    fj_status = "هیچ کانال/گروهی فعال نیست."

  text = f"📢 <b>مدیریت کانال‌های جوین اجباری</b>\n\nلیست فعال:\n{fj_status}"
  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="➕ افزودن کانال/گروه جوین اجباری", callback_data="adm_add_fj"
      ),
      types.InlineKeyboardButton(
          text="🗑️ حذف کامل جوین‌های اجباری", callback_data="adm_clear_fj"
      ),
      types.InlineKeyboardButton(
          text="🔙 بازگشت به پنل اصلی", callback_data="open_admin_panel"
      ),
  )
  try:
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "adm_sec_vip")
def admin_section_vip(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id, expire_timestamp FROM vip_users")
  vips = cursor.fetchall()
  conn.close()

  vip_list_str = ""
  for v_id, exp in vips:
    date_str = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M")
    vip_list_str += f"⭐ کاربر <code>{v_id}</code> (انقضا: {date_str})\n"

  if not vip_list_str:
    vip_list_str = "هیچ کاربر VIP فعالی وجود ندارد."

  text = (
      "⭐ <b>مدیریت کاربران VIP ربات</b>\n\n"
      f"لیست کاربران ویژه:\n{vip_list_str}"
  )
  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="➕ اعطای VIP دستی به کاربر", callback_data="adm_add_vip_manual"
      ),
      types.InlineKeyboardButton(
          text="🔙 بازگشت به پنل اصلی", callback_data="open_admin_panel"
      ),
  )
  try:
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "adm_add_vip_manual")
def ask_manual_vip_id(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
      )
  )
  msg = bot.send_message(
      call.message.chat.id,
      "⭐ <b>آیدی عددی کاربر</b> مورد نظر را برای اعطای اشتراک VIP ۳۰ روزه"
      " ارسال کنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, process_manual_vip)


def process_manual_vip(message):
  if not is_admin(message.from_user.id):
    return
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return
  try:
    target_id = int(message.text.strip())
    expire_timestamp = time.time() + (30 * 24 * 3600)
    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO vip_users VALUES (?, ?)",
        (target_id, expire_timestamp),
    )
    conn.commit()
    conn.close()
    bot.send_message(
        message.chat.id,
        f"✅ اشتراک VIP ۳۰ روزه با موفقیت برای کاربر <code>{target_id}</code>"
        " ثبت شد!",
    )
    show_admin_panel_content(message.chat.id)
  except Exception:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        message.chat.id,
        "❌ لطفاً فقط یک عدد صحیح (آیدی عددی) بفرستید:",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, process_manual_vip)


@bot.callback_query_handler(func=lambda call: call.data == "adm_clear_cache")
def admin_clear_cache_callback(call):
  if not is_admin(call.from_user.id):
    return
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("DELETE FROM cache")
  conn.commit()
  conn.close()
  try:
    bot.answer_callback_query(
        call.id,
        "✅ حافظه موقت (کش) ویدیوها با موفقیت پاکسازی شد.",
        show_alert=True,
    )
  except Exception:
    pass
  show_admin_panel_content(call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "adm_sec_settings")
def admin_section_settings(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  text = (
      "⚙️ <b>تنظیمات عمومی ربات</b>\n\nبرای نام کاربر در متن خوش‌آمدگویی از"
      " <code>{first_name}</code> استفاده کنید."
  )
  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="💬 تغییر متن خوش‌آمدگویی", callback_data="adm_set_welcome"
      ),
      types.InlineKeyboardButton(
          text="🎨 تغییر رنگ تم دکمه‌ها", callback_data="adm_change_theme"
      ),
      types.InlineKeyboardButton(
          text="🔙 بازگشت به پنل اصلی", callback_data="open_admin_panel"
      ),
  )
  try:
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "adm_sec_stats")
def admin_section_stats(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT COUNT(*) FROM users")
  u_count = cursor.fetchone()[0]
  cursor.execute("SELECT SUM(usage_count) FROM users")
  d_count = cursor.fetchone()[0] or 0
  cursor.execute("SELECT COUNT(*) FROM vip_users")
  v_count = cursor.fetchone()[0]
  conn.close()

  text = (
      "📊 <b>آمار تفصیلی و جامع سیستم</b>\n\n"
      f"👥 کل کاربران ثبت‌شده: <code>{u_count}</code> نفر\n"
      f"📥 مجموع دانلودهای موفق: <code>{d_count}</code> فایل\n"
      f"⭐ تعداد اعضای VIP: <code>{v_count}</code> کاربر\n"
      "📈 وضعیت سرور و ربات: کاملاً پایدار و آنلاین 🟢"
  )
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 بازگشت به پنل اصلی", callback_data="open_admin_panel"
      )
  )
  try:
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "adm_toggle_bot")
def admin_toggle_bot_callback(call):
  if int(call.from_user.id) != int(MAIN_ADMIN_ID):
    try:
      bot.answer_callback_query(
          call.id,
          "❌ فقط ادمین اصلی اجازه تغییر وضعیت ربات را دارد!",
          show_alert=True,
      )
    except Exception:
      pass
    return

  current = get_setting("bot_status")
  new_st = "inactive" if current == "active" else "active"
  set_setting("bot_status", new_st)
  st_name = "روشن و فعال شد 🟢" if new_st == "active" else "خاموش (تعمیرات) 🔴"
  try:
    bot.answer_callback_query(call.id, f"✅ وضعیت ربات به: {st_name}")
  except Exception:
    pass
  show_admin_panel_content(call.message.chat.id, call.message.message_id)


# ==================== مدیریت ادمین‌ها ====================
@bot.callback_query_handler(func=lambda call: call.data == "adm_manage_admins")
def manage_admins_menu(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM admins")
  admins = cursor.fetchall()
  conn.close()
  admins_str = "\n".join([f"👤 <code>{a[0]}</code>" for a in admins])

  kb = types.InlineKeyboardMarkup(row_width=2)
  kb.add(
      types.InlineKeyboardButton(
          text="➕ افزودن ادمین جدید", callback_data="adm_add_admin"
      ),
      types.InlineKeyboardButton(
          text="➖ حذف ادمین", callback_data="adm_del_admin"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 بازگشت به پنل", callback_data="open_admin_panel"
      )
  )
  try:
    bot.edit_message_text(
        f"🛡️ <b>لیست ادمین‌های ربات:</b>\n\n{admins_str}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )
  except Exception:
    pass


@bot.callback_query_handler(func=lambda call: call.data == "adm_add_admin")
def ask_new_admin_id(call):
  if int(call.from_user.id) != int(MAIN_ADMIN_ID):
    try:
      bot.answer_callback_query(
          call.id,
          "❌ فقط ادمین اصلی اجازه افزودن ادمین جدید را دارد!",
          show_alert=True,
      )
    except Exception:
      pass
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
      )
  )
  msg = bot.send_message(
      call.message.chat.id,
      "➕ <b>آیدی عددی (User ID)</b> کاربر مورد نظر را برای اعطای دسترسی ادمین"
      " ارسال کنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, save_new_admin)


def save_new_admin(message):
  if not is_admin(message.from_user.id):
    return
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return
  try:
    new_admin_id = int(message.text.strip())
    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (new_admin_id,))
    conn.commit()
    conn.close()
    bot.send_message(
        message.chat.id,
        f"✅ کاربر <code>{new_admin_id}</code> با موفقیت به عنوان ادمین ربات"
        " اضافه شد!",
    )
    show_admin_panel_content(message.chat.id)
  except Exception:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        message.chat.id,
        "❌ فرمت اشتباه است! لطفاً فقط یک عدد صحیح (آیدی عددی) بفرستید:",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, save_new_admin)


@bot.callback_query_handler(func=lambda call: call.data == "adm_del_admin")
def ask_del_admin_id(call):
  if int(call.from_user.id) != int(MAIN_ADMIN_ID):
    try:
      bot.answer_callback_query(
          call.id,
          "❌ فقط ادمین اصلی اجازه حذف ادمین‌ها را دارد!",
          show_alert=True,
      )
    except Exception:
      pass
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
      )
  )
  msg = bot.send_message(
      call.message.chat.id,
      "➖ <b>آیدی عددی (User ID)</b> ادمینی که می‌خواهید دسترسی‌اش را بگیرید"
      " ارسال کنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, process_del_admin)


def process_del_admin(message):
  if not is_admin(message.from_user.id):
    return
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return
  try:
    target_id = int(message.text.strip())
    if target_id == int(MAIN_ADMIN_ID):
      bot.send_message(
          message.chat.id, "❌ نمی‌توانید ادمین اصلی را حذف کنید!"
      )
      return
    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id=?", (target_id,))
    conn.commit()
    conn.close()
    bot.send_message(
        message.chat.id,
        f"✅ دسترسی ادمین <code>{target_id}</code> با موفقیت حذف شد.",
    )
    show_admin_panel_content(message.chat.id)
  except Exception:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        message.chat.id, "❌ لطفاً فقط یک عدد صحیح بفرستید:", reply_markup=kb
    )
    bot.register_next_step_handler(msg, process_del_admin)


# ==================== ویزارد افزودن جوین اجباری ====================
admin_wizard = {}


@bot.callback_query_handler(func=lambda call: call.data == "adm_add_fj")
def wizard_start(call):
  if not is_admin(call.from_user.id):
    return
  active = get_active_forced_joins()
  if len(active) >= 5:
    try:
      bot.answer_callback_query(
          call.id,
          "❌ حداکثر ۵ کانال/گروه همزمان می‌تواند فعال باشد!",
          show_alert=True,
      )
    except Exception:
      pass
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  admin_wizard[call.from_user.id] = {}

  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
      )
  )

  msg = bot.send_message(
      call.message.chat.id,
      "📌 <b>مرحله ۱ از ۴:</b>\n\nلطفاً <b>آیدی و لینک</b> کانال یا گروه را با"
      " فاصله بفرستید:\nمثال:\n<code>@MyChannel"
      " https://t.me/MyChannel</code>",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, wizard_get_link)


def wizard_get_link(message):
  if not is_admin(message.from_user.id):
    return
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return

  try:
    parts = message.text.strip().split()
    if len(parts) < 2:
      raise ValueError("Invalid format")
    admin_wizard[message.from_user.id]["chat_id"] = parts[0]
    admin_wizard[message.from_user.id]["link"] = parts[1]

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            text="📢 کانال", callback_data="wiz_type_channel"
        ),
        types.InlineKeyboardButton(
            text="👥 گروه", callback_data="wiz_type_group"
        ),
    )
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )

    bot.send_message(
        message.chat.id,
        "📂 <b>مرحله ۲ از ۴:</b>\n\nنوع محیط را انتخاب کنید:",
        reply_markup=kb,
    )
  except Exception:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        message.chat.id,
        "❌ فرمت اشتباه است! لطفاً طبق نمونه بفرستید:\n<code>@MyChannel"
        " https://t.me/MyChannel</code>",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, wizard_get_link)


@bot.callback_query_handler(func=lambda call: call.data.startswith("wiz_type_"))
def wizard_get_type(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  admin_wizard[call.from_user.id]["chat_type"] = call.data.split("_")[2]

  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="♾️ بی‌نهایت (بدون سقف ممبر)", callback_data="wiz_limit_inf"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
      )
  )

  msg = bot.send_message(
      call.message.chat.id,
      "🔢 <b>مرحله ۳ از ۴:</b>\n\nلطفاً <b>سقف تعداد ممبر</b> مورد نیاز را به"
      " صورت عدد وارد کنید (مثلاً <code>50</code>) یا روی دکمه بی‌نهایت بزنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(call.message, wizard_get_limit)


def wizard_get_limit(message):
  if not is_admin(message.from_user.id):
    return
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return

  try:
    limit = int(message.text.strip())
    admin_wizard[message.from_user.id]["limit"] = limit
    wizard_ask_duration(message.chat.id)
  except Exception:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        message.chat.id,
        "❌ لطفاً فقط یک عدد صحیح وارد کنید (مثلاً 50):",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, wizard_get_limit)


@bot.callback_query_handler(func=lambda call: call.data == "wiz_limit_inf")
def wizard_limit_inf(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  admin_wizard[call.from_user.id]["limit"] = -1
  wizard_ask_duration(call.message.chat.id)


def wizard_ask_duration(chat_id):
  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="⏳ دائمی (بدون محدودیت زمانی)", callback_data="wiz_time_perm"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
      )
  )
  msg = bot.send_message(
      chat_id,
      "⏱️ <b>مرحله ۴ از ۴:</b>\n\nلطفاً <b>مدت زمان ماندگاری (به ساعت)</b> را"
      " وارد کنید (مثلاً <code>24</code>) یا روی دکمه دائمی بزنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, wizard_get_hours)


def wizard_get_hours(message):
  if not is_admin(message.from_user.id):
    return
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return

  try:
    hours = float(message.text.strip())
    admin_wizard[message.from_user.id]["hours"] = hours
    save_wizard_complete(message.chat.id, message.from_user.id)
  except Exception:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        message.chat.id,
        "❌ لطفاً فقط یک عدد معتبر برای ساعت وارد کنید:",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, wizard_get_hours)


@bot.callback_query_handler(func=lambda call: call.data == "wiz_time_perm")
def wizard_time_perm(call):
  if not is_admin(call.from_user.id):
    return
  try:
    bot.answer_callback_query(call.id)
  except Exception:
    pass
  admin_wizard[call.from_user.id]["hours"] = -1
  save_wizard_complete(call.message.chat.id, call.message.from_user.id)


def save_wizard_complete(chat_id, user_id):
  data = admin_wizard.get(user_id)
  if not data:
    return
  chat_id_ch = data["chat_id"]
  link = data["link"]
  c_type = data["chat_type"]
  limit = data["limit"]
  hours = data["hours"]
  expire_timestamp = (time.time() + (hours * 3600)) if hours != -1 else -1

  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "INSERT OR REPLACE INTO forced_joins VALUES (?, ?, ?, ?, 0, ?)",
      (chat_id_ch, link, c_type, limit, expire_timestamp),
  )
  conn.commit()
  conn.close()
  if user_id in admin_wizard:
    del admin_wizard[user_id]
  bot.send_message(
      chat_id,
      "✅ <b>کانال/گپ با موفقیت به سیستم جوین اجباری اضافه شد!</b>",
  )
  show_admin_panel_content(chat_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def handle_admin_callbacks(call):
  if not is_admin(call.from_user.id):
    return
  data = call.data

  if data == "adm_clear_fj":
    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM forced_joins")
    conn.commit()
    conn.close()
    try:
      bot.answer_callback_query(
          call.id,
          "✅ تمامی کانال‌های جوین اجباری پاک شدند.",
          show_alert=True,
      )
    except Exception:
      pass
    show_admin_panel_content(call.message.chat.id, call.message.message_id)

  elif data == "adm_broadcast":
    try:
      bot.answer_callback_query(call.id)
    except Exception:
      pass
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        call.message.chat.id,
        "📢 <b>پیام همگانی خود را ارسال کنید:</b>",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, process_broadcast)

  elif data == "adm_set_welcome":
    try:
      bot.answer_callback_query(call.id)
    except Exception:
      pass
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 لغو و بازگشت به پنل", callback_data="open_admin_panel"
        )
    )
    msg = bot.send_message(
        call.message.chat.id,
        "💬 <b>متن خوش‌آمدگویی جدید را ارسال کنید:</b>\n(توجه: برای نمایش"
        " نام کاربر از <code>{first_name}</code> استفاده کنید)",
        reply_markup=kb,
    )
    bot.register_next_step_handler(msg, save_welcome)

  elif data == "adm_change_theme":
    try:
      bot.answer_callback_query(call.id)
    except Exception:
      pass
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton(text="🔵 آبی", callback_data="theme_blue"),
        types.InlineKeyboardButton(text="🟢 سبز", callback_data="theme_green"),
        types.InlineKeyboardButton(text="🔴 قرمز", callback_data="theme_red"),
    )
    kb.add(
        types.InlineKeyboardButton(
            text="🔙 بازگشت به پنل اصلی", callback_data="open_admin_panel"
        )
    )
    bot.send_message(
        call.message.chat.id,
        "🎨 <b>رنگ تم دکمه‌ها را انتخاب کنید:</b>",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("theme_"))
def set_theme_callback(call):
  color = call.data.split("_")[1]
  set_setting("theme_color", color)
  try:
    bot.answer_callback_query(
        call.id,
        f"✅ تم دکمه‌ها به {color.upper()} تغییر یافت.",
        show_alert=True,
    )
  except Exception:
    pass
  show_admin_panel_content(call.message.chat.id, call.message.message_id)


def process_broadcast(message):
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM users")
  users = cursor.fetchall()
  conn.close()
  sent, failed = 0, 0
  for (u_id,) in users:
    try:
      bot.copy_message(u_id, message.chat.id, message.message_id)
      sent += 1
    except Exception:
      failed += 1
  bot.send_message(
      message.chat.id,
      f"✅ <b>ارسال همگانی پایان یافت.</b>\nموفق: {sent} | ناموفق: {failed}",
  )
  show_admin_panel_content(message.chat.id)


def save_welcome(message):
  if message.text and message.text.startswith("/"):
    show_admin_panel_content(message.chat.id)
    return
  set_setting("welcome_msg", message.text)
  bot.send_message(message.chat.id, "✅ متن خوش‌آمدگویی با موفقیت ذخیره شد.")
  show_admin_panel_content(message.chat.id)


# ==================== هندلر دریافت لینک ویدیو ====================
@bot.message_handler(regexp=r"https?://[^\s]+")
def handle_download_links(message):
  user_id = message.from_user.id
  if not is_bot_active() and not is_admin(user_id):
    return

  if check_user_joined(user_id):
    start_cmd(message)
    return

  url = message.text.strip()
  url_id = save_pending_url(url)
  icon, _ = get_theme_emoji()

  kb = types.InlineKeyboardMarkup(row_width=2)
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} کیفیت عالی (Best)", callback_data=f"dl|best|{url_id}"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} کیفیت متوسط", callback_data=f"dl|medium|{url_id}"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🎵 دانلود موزیک (MP3)", callback_data=f"dl|audio|{url_id}"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🔙 بازگشت به منوی اصلی", callback_data="back_to_home"
      ),
      types.InlineKeyboardButton(
          text="👤 پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      ),
  )

  bot.reply_to(
      message,
      "🎬 ویدیوی شما شناسایی شد. کیفیت مورد نظر را انتخاب کنید:",
      reply_markup=kb,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("dl|"))
def process_download_choice(call):
  try:
    bot.answer_callback_query(call.id, "⏳ در حال پردازش...")
  except Exception:
    pass

  _, choice, url_id = call.data.split("|", 2)
  url = get_pending_url(url_id)
  if not url:
    try:
      bot.answer_callback_query(
          call.id, "❌ منقضی شده است! لینک را دوباره بفرستید.", show_alert=True
      )
    except Exception:
      pass
    return

  status_msg = bot.send_message(
      call.message.chat.id, "🔄 <i>در حال پردازش و دریافت ویدیو و کپشن...</i>"
  )

  threading.Thread(
      target=download_and_send_worker,
      args=(call.message.chat.id, status_msg.message_id, choice, url_id, url),
      daemon=True,
  ).start()


def download_and_send_worker(chat_id, status_msg_id, choice, url_id, url):
  cache_key = f"{choice}_{url_id}"
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT file_id, file_type, caption FROM cache WHERE url_hash=?",
      (cache_key,),
  )
  cached = cursor.fetchone()
  conn.close()

  if cached:
    file_id, file_type, saved_caption = cached
    try:
      bot.edit_message_text(
          "⚡ <i>ارسال فوری از حافظه موقت...</i>", chat_id, status_msg_id
      )
      caption_text = (
          saved_caption if saved_caption else "🎬 دانلود شده از آلفا دانلودر"
      )
      if file_type == "audio":
        bot.send_audio(chat_id, file_id, caption=f"🎵 {caption_text}"[:1024])
      else:
        bot.send_video(
            chat_id,
            file_id,
            caption=f"🎬 <b>{caption_text}</b>"[:1024],
            parse_mode="HTML",
        )
      bot.delete_message(chat_id, status_msg_id)
    except Exception:
      pass
    return

  try:
    ydl_opts = {
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }

    if choice == "audio":
      ydl_opts["format"] = "bestaudio/best"
    else:
      ydl_opts["format"] = "best[ext=mp4]/best"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=True)
      filename = ydl.prepare_filename(info)

      raw_caption = (
          info.get("description")
          or info.get("title")
          or "ویدیو بدون کپشن"
      )
      clean_caption = (
          raw_caption.replace("<", "&lt;")
          .replace(">", "&gt;")
          .replace("&", "&amp;")
      )

    bot.edit_message_text(
        "📤 <i>در حال آپلود روی تلگرام به همراه کپشن...</i>",
        chat_id,
        status_msg_id,
    )

    with open(filename, "rb") as f:
      if choice == "audio":
        sent_msg = bot.send_audio(
            chat_id, f, caption=f"🎵 {clean_caption}"[:1024]
        )
        file_id = sent_msg.audio.file_id
        file_type = "audio"
      else:
        sent_msg = bot.send_video(
            chat_id,
            f,
            caption=f"🎬 <b>{clean_caption}</b>"[:1024],
            parse_mode="HTML",
        )
        file_id = sent_msg.video.file_id
        file_type = "video"

    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)",
        (cache_key, file_id, file_type, clean_caption),
    )
    conn.commit()
    conn.close()

    bot.delete_message(chat_id, status_msg_id)
    if os.path.exists(filename):
      os.remove(filename)

  except Exception as e:
    error_message = str(e)
    try:
      bot.edit_message_text(
          f"❌ <b>خطا در پردازش یا دانلود لینک:</b>\n<code>{error_message[:180]}</code>",
          chat_id,
          status_msg_id,
          parse_mode="HTML",
      )
    except Exception:
      pass


# ==================== اجرای ربات ====================
if __name__ == "__main__":
  if not os.path.exists("downloads"):
    os.makedirs("downloads")

  keep_alive()
  print("🤖 ربات آلفا دانلودر با موفقیت روشن شد و آماده به کار است...")

  while True:
    try:
      bot.infinity_polling(
          skip_pending=True, timeout=90, long_polling_timeout=60
      )
    except Exception as e:
      print(f"⚠️ خطای موقت اتصال: {e}")
      time.sleep(5)
