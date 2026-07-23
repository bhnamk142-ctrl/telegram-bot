from datetime import datetime
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
BOT_TOKEN = "8474467810:AAFKVRgB2l-z9NxGUCNnxI0WJOvfnY-NkXM"
ADMIN_ID = 8443938939  # آیدی عددی ادمین
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
  t = threading.Thread(target=run_web)
  t.start()


# ==================== دیتابیس SQLITE ====================
def init_db():
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY,"
      " usage_count INTEGER DEFAULT 0)"
  )
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
      "CREATE TABLE IF NOT EXISTS user_verified (user_id INTEGER, chat_id"
      " TEXT, PRIMARY KEY(user_id, chat_id))"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS cache (url_hash TEXT PRIMARY KEY, file_id"
      " TEXT, file_type TEXT)"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS pending_urls (id TEXT PRIMARY KEY, url TEXT)"
  )

  cursor.execute(
      "INSERT OR IGNORE INTO settings VALUES ('welcome_msg', 'به ربات هوشمند"
      " دانلودر خوش آمدید! 🎉')"
  )
  cursor.execute(
      "INSERT OR IGNORE INTO settings VALUES ('theme_color', 'blue')"
  )
  conn.commit()
  conn.close()


init_db()


# ==================== مدیریت لینک‌های کوتاه دیتابیس ====================
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


# ==================== توابع کمکی ====================
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
  cursor.execute(
      "INSERT OR IGNORE INTO users (user_id, usage_count) VALUES (?, 0)",
      (user_id,),
  )
  cursor.execute(
      "UPDATE users SET usage_count = usage_count + 1 WHERE user_id=?",
      (user_id,),
  )
  conn.commit()
  conn.close()


# ==================== مدیریت جوین اجباری و پاکسازی ====================
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
    if target != -1 and joined >= target:
      cursor.execute("DELETE FROM forced_joins WHERE chat_id=?", (chat_id,))
    elif expire != -1 and now >= expire:
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


def register_user_joins(user_id):
  active_list = get_active_forced_joins()
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()

  for chat_id, link, chat_type, limit, count, expire in active_list:
    try:
      member = bot.get_chat_member(chat_id=chat_id, user_id=user_id)
      if member.status not in ["left", "kicked"]:
        cursor.execute(
            "SELECT 1 FROM user_verified WHERE user_id=? AND chat_id=?",
            (user_id, chat_id),
        )
        if not cursor.fetchone():
          cursor.execute(
              "INSERT INTO user_verified VALUES (?, ?)", (user_id, chat_id)
          )
          cursor.execute(
              "UPDATE forced_joins SET joined_count = joined_count + 1 WHERE"
              " chat_id=?",
              (chat_id,),
          )
    except Exception:
      pass

  conn.commit()
  conn.close()


# ==================== دستور /START ====================
@bot.message_handler(commands=["start"])
def start_cmd(message):
  user_id = message.from_user.id
  first_name = message.from_user.first_name or "دوست من"
  add_user(user_id)

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

    bot.send_message(
        message.chat.id,
        "⚠️ <b>برای استفاده از خدمات ربات، ابتدا باید در کانال/گروه‌های زیر"
        " عضو شوید:</b>",
        reply_markup=kb,
    )
    return

  icon, _ = get_theme_emoji()
  welcome_text = (
      f"سلام <b>{first_name}</b> عزیز! ❤️ خوش آمدی!\n\n"
      "با این ربات می‌تونی ویدیوهای <b>اینستاگرام، یوتیوب و تیک‌تاک</b> رو با"
      " بالاترین کیفیت همراه با کپشن دانلود کنی!\n\n"
      "👇 لطفاً یکی از گزینه‌های زیر را انتخاب کن یا مستقیماً <b>لینک ویدیو</b>"
      " رو برام بفرست:"
  )

  kb = types.InlineKeyboardMarkup(row_width=2)
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} دانلود از اینستاگرام", callback_data="ask_link_insta"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} دانلود از یوتیوب", callback_data="ask_link_yt"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} دانلود از تیک‌تاک", callback_data="ask_link_tiktok"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="👤 پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      )
  )

  bot.send_message(
      message.chat.id, welcome_text, reply_markup=kb, parse_mode="HTML"
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith("ask_link_"))
def ask_platform_link(call):
  platforms = {
      "ask_link_insta": "اینستاگرام",
      "ask_link_yt": "یوتیوب",
      "ask_link_tiktok": "تیک‌تاک",
  }
  p_name = platforms.get(call.data, "پلتفرم")
  bot.answer_callback_query(call.id)
  bot.send_message(
      call.message.chat.id,
      f"📥 لطفاً <b>لینک ویدیو {p_name}</b> مورد نظرت رو ارسال کن:",
  )


@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def verify_join_callback(call):
  user_id = call.from_user.id
  not_joined = check_user_joined(user_id)

  if not_joined:
    bot.answer_callback_query(
        call.id,
        "❌ هنوز در تمام کانال‌ها/گروه‌ها عضو نشده‌اید!",
        show_alert=True,
    )
  else:
    register_user_joins(user_id)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    start_cmd(call.message)


# ==================== دکمه‌های عمومی ====================
@bot.message_handler(func=lambda m: m.text == "📥 راهنمای ربات")
def help_cmd(message):
  icon, _ = get_theme_emoji()
  text = (
      f"{icon} <b>راهنمای دانلود:</b>\n\n"
      "1️⃣ لینک ویدیو از <b>اینستاگرام</b>، <b>یوتیوب</b> یا <b>تیک‌تاک</b> را"
      " فرستید.\n"
      "2️⃣ کیفیت مورد نظر (1080p تا 240p) یا فایل صوتی را انتخاب کنید.\n"
      "3️⃣ ویدیو به همراه کپشن کامل براتون ارسال میشه!"
  )
  bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "📊 آمار من")
def stats_cmd(message):
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT usage_count FROM users WHERE user_id=?", (message.from_user.id,)
  )
  res = cursor.fetchone()
  conn.close()
  count = res[0] if res else 0
  bot.send_message(
      message.chat.id, f"📈 <b>تعداد دانلودهای شما:</b> <code>{count}</code> بار"
  )


@bot.message_handler(func=lambda m: m.text == "👤 پشتیبانی")
def support_cmd(message):
  kb = types.InlineKeyboardMarkup()
  kb.add(
      types.InlineKeyboardButton(
          text="👤 ارتباط با پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      )
  )
  bot.send_message(
      message.chat.id,
      "📞 جهت ارتباط با پشتیبانی روی دکمه زیر کلیک کنید:",
      reply_markup=kb,
  )


# ==================== پنل مدیریت اختصاصی ====================
@bot.message_handler(
    func=lambda m: m.text == "⚙️ پنل مدیریت" or m.text == "/admin"
)
def admin_panel(message):
  if message.from_user.id != ADMIN_ID:
    return

  icon, _ = get_theme_emoji()
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT COUNT(*) FROM users")
  total_users = cursor.fetchone()[0]
  cursor.execute("SELECT SUM(usage_count) FROM users")
  total_usage = cursor.fetchone()[0] or 0

  active_fj = get_active_forced_joins()
  conn.close()

  fj_status = ""
  if active_fj:
    for idx, (ch_id, link, c_type, limit, count, expire) in enumerate(
        active_fj, 1
    ):
      limit_str = "بی‌نهایت" if limit == -1 else f"{count}/{limit}"
      time_str = (
          "دائمی"
          if expire == -1
          else f"{round((expire - time.time())/3600, 1)} ساعت ماندگار"
      )
      fj_status += (
          f"\n{idx}. <code>{ch_id}</code> ({c_type})\n └ سقف: {limit_str} |"
          f" زمان: {time_str}\n"
      )
  else:
    fj_status = "هیچ مورد فعال نیست (حداکثر ۵ تا)"

  text = (
      "👑 <b>پنل مدیریت اختصاصی ربات</b>\n\n"
      f"👥 کل کاربران: <code>{total_users}</code> نفر\n"
      f"📊 کل دانلودها: <code>{total_usage}</code> بار\n"
      "🎨 رنگ کنونی دکمه‌ها:"
      f" <b>{get_setting('theme_color').upper()}</b>\n\n"
      f"📢 <b>لیست جوین اجباری فعلی:</b>\n{fj_status}"
  )

  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} افزودن کانال/گپ (مرحله‌به‌مرحله دستی)",
          callback_data="adm_add_fj",
      ),
      types.InlineKeyboardButton(
          text=f"{icon} حذف کامل موارد جوین اجباری", callback_data="adm_clear_fj"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} ارسال پیام همگانی", callback_data="adm_broadcast"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} تغییر متن خوش‌آمدگویی", callback_data="adm_set_welcome"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} تغییر رنگ دکمه‌های شیشه‌ای",
          callback_data="adm_change_theme",
      ),
  )
  bot.send_message(message.chat.id, text, reply_markup=kb)


# ==================== ویزارد دستی افزودن جوین اجباری ====================
admin_wizard = {}


@bot.callback_query_handler(func=lambda call: call.data == "adm_add_fj")
def wizard_start(call):
  if call.from_user.id != ADMIN_ID:
    return
  active = get_active_forced_joins()
  if len(active) >= 5:
    bot.answer_callback_query(
        call.id, "❌ سقف ۵ کانال/گپ پر شده است!", show_alert=True
    )
    return

  admin_wizard[call.from_user.id] = {}
  msg = bot.send_message(
      call.message.chat.id,
      "📌 <b>مرحله ۱ از ۴:</b>\n\nلطفاً <b>آیدی و لینک</b> کانال یا گروه را با"
      " فاصله بفرستید:\nمثال:\n<code>@MyChannel https://t.me/MyChannel</code>",
  )
  bot.register_next_step_handler(msg, wizard_get_link)


def wizard_get_link(message):
  if message.from_user.id != ADMIN_ID:
    return
  try:
    parts = message.text.strip().split()
    chat_id, link = parts[0], parts[1]
    admin_wizard[message.from_user.id]["chat_id"] = chat_id
    admin_wizard[message.from_user.id]["link"] = link

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(
            text="📢 کانال", callback_data="wiz_type_channel"
        ),
        types.InlineKeyboardButton(
            text="👥 گروه", callback_data="wiz_type_group"
        ),
    )
    bot.send_message(
        message.chat.id,
        "📂 <b>مرحله ۲ از ۴:</b>\n\nنوع محیط را انتخاب کنید:",
        reply_markup=kb,
    )
  except Exception:
    msg = bot.send_message(
        message.chat.id,
        "❌ فرمت اشتباه است! لطفاً دوباره طبق نمونه بفرستید:\n<code>@MyChannel"
        " https://t.me/MyChannel</code>",
    )
    bot.register_next_step_handler(msg, wizard_get_link)


@bot.callback_query_handler(func=lambda call: call.data.startswith("wiz_type_"))
def wizard_get_type(call):
  if call.from_user.id != ADMIN_ID:
    return
  c_type = call.data.split("_")[2]
  admin_wizard[call.from_user.id]["chat_type"] = c_type

  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="♾️ بی‌نهایت (بدون سقف ممبر)", callback_data="wiz_limit_inf"
      )
  )

  msg = bot.send_message(
      call.message.chat.id,
      "🔢 <b>مرحله ۳ از ۴:</b>\n\nلطفاً <b>سقف تعداد ممبر</b> مورد نیاز را به"
      " صورت دستی وارد کنید (مثلاً عدد <code>22</code>) یا روی دکمه بی‌نهایت"
      " بزنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(call.message, wizard_get_limit)


def wizard_get_limit(message):
  if message.from_user.id != ADMIN_ID:
    return
  try:
    limit = int(message.text.strip())
    admin_wizard[message.from_user.id]["limit"] = limit
    wizard_ask_duration(message.chat.id)
  except Exception:
    msg = bot.send_message(
        message.chat.id, "❌ لطفاً فقط یک عدد صحیح وارد کنید (مثلاً 22):"
    )
    bot.register_next_step_handler(msg, wizard_get_limit)


@bot.callback_query_handler(func=lambda call: call.data == "wiz_limit_inf")
def wizard_limit_inf(call):
  if call.from_user.id != ADMIN_ID:
    return
  admin_wizard[call.from_user.id]["limit"] = -1
  wizard_ask_duration(call.message.chat.id)


def wizard_ask_duration(chat_id):
  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="⏳ دائمی (بدون محدودیت زمانی)", callback_data="wiz_time_perm"
      )
  )

  msg = bot.send_message(
      chat_id,
      "⏱️ <b>مرحله ۴ از ۴:</b>\n\nلطفاً <b>مدت زمان ماندگاری (به ساعت)</b> را"
      " به صورت دستی وارد کنید (مثلاً <code>24</code>) یا روی دکمه دائمی"
      " بزنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, wizard_get_hours)


def wizard_get_hours(message):
  if message.from_user.id != ADMIN_ID:
    return
  try:
    hours = float(message.text.strip())
    admin_wizard[message.from_user.id]["hours"] = hours
    save_wizard_complete(message.chat.id, message.from_user.id)
  except Exception:
    msg = bot.send_message(
        message.chat.id, "❌ لطفاً فقط یک عدد معتبر برای ساعت وارد کنید:"
    )
    bot.register_next_step_handler(msg, wizard_get_hours)


@bot.callback_query_handler(func=lambda call: call.data == "wiz_time_perm")
def wizard_time_perm(call):
  if call.from_user.id != ADMIN_ID:
    return
  admin_wizard[call.from_user.id]["hours"] = -1
  save_wizard_complete(call.message.chat.id, call.from_user.id)


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

  del admin_wizard[user_id]

  limit_str = f"{limit} نفر" if limit != -1 else "بی‌نهایت"
  time_str = f"{hours} ساعت" if hours != -1 else "دائمی"
  bot.send_message(
      chat_id,
      "✅ <b>کانال/گپ با موفقیت ثبت شد!</b>\n\n"
      f"🔹 آیدی: <code>{chat_id_ch}</code>\n"
      f"🔢 سقف ممبر دستی: <b>{limit_str}</b>\n"
      f"⏳ زمان ماندگاری: <b>{time_str}</b>",
  )


# ==================== سایر تنظیمات ادمین ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def handle_admin_callbacks(call):
  if call.from_user.id != ADMIN_ID:
    return
  data = call.data

  if data == "adm_clear_fj":
    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM forced_joins")
    conn.commit()
    conn.close()
    bot.answer_callback_query(
        call.id, "✅ تمام موارد پاک شدند.", show_alert=True
    )
    admin_panel(call.message)

  elif data == "adm_broadcast":
    msg = bot.send_message(
        call.message.chat.id, "📢 <b>پیام همگانی خود را ارسال کنید:</b>"
    )
    bot.register_next_step_handler(msg, process_broadcast)

  elif data == "adm_set_welcome":
    msg = bot.send_message(
        call.message.chat.id, "💬 <b>متن خوش‌آمدگویی جدید را ارسال کنید:</b>"
    )
    bot.register_next_step_handler(msg, save_welcome)

  elif data == "adm_change_theme":
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton(text="🔵 آبی", callback_data="theme_blue"),
        types.InlineKeyboardButton(text="🟢 سبز", callback_data="theme_green"),
        types.InlineKeyboardButton(text="🔴 قرمز", callback_data="theme_red"),
    )
    bot.send_message(
        call.message.chat.id,
        "🎨 <b>رنگ دکمه‌های شیشه‌ای را انتخاب کنید:</b>",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("theme_"))
def set_theme_callback(call):
  color = call.data.split("_")[1]
  set_setting("theme_color", color)
  bot.answer_callback_query(
      call.id,
      f"✅ تم رنگی دکمه‌ها به {color.upper()} تغییر یافت.",
      show_alert=True,
  )
  admin_panel(call.message)


def process_broadcast(message):
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


def save_welcome(message):
  set_setting("welcome_msg", message.text)
  bot.send_message(message.chat.id, "✅ متن خوش‌آمدگویی ذخیره شد.")


# ==================== دریافت لینک و نمایش کیفیت‌های شیشه‌ای ====================
@bot.message_handler(regexp=r"https?://[^\s]+")
def handle_download_links(message):
  user_id = message.from_user.id
  not_joined = check_user_joined(user_id)
  if not_joined:
    start_cmd(message)
    return

  url = message.text.strip()
  url_id = save_pending_url(url)
  icon, _ = get_theme_emoji()

  kb = types.InlineKeyboardMarkup(row_width=2)
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} 1080p", callback_data=f"dl|1080|{url_id}"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} 720p", callback_data=f"dl|720|{url_id}"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} 480p", callback_data=f"dl|480|{url_id}"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} 360p", callback_data=f"dl|360|{url_id}"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} 240p", callback_data=f"dl|240|{url_id}"
      ),
  )
  kb.add(
      types.InlineKeyboardButton(
          text="🎵 دانلود مستقیم موزیک (MP3)",
          callback_data=f"dl|audio|{url_id}",
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="👤 پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      )
  )

  bot.reply_to(
      message,
      "🎬 <b>کیفیت مورد نظر خود جهت دانلود را انتخاب کنید:</b>",
      reply_markup=kb,
  )


# ==================== پردازش دانلود و ارسال ویدیو با کپشن ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("dl|"))
def process_download_choice(call):
  _, choice, url_id = call.data.split("|", 2)
  url = get_pending_url(url_id)

  if not url:
    bot.answer_callback_query(
        call.id,
        "❌ منقضی شده است! لطفاً لینک را دوباره ارسال کنید.",
        show_alert=True,
    )
    return

  bot.answer_callback_query(call.id, "⏳ درخواست ثبت شد. در حال دانلود...")
  status_msg = bot.send_message(
      call.message.chat.id, "🔄 <i>در حال بررسی سرور و دریافت ویدیو...</i>"
  )

  # بررسی کش دیتابیس
  cache_key = f"{choice}_{url_id}"
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT file_id, file_type FROM cache WHERE url_hash=?", (cache_key,)
  )
  cached = cursor.fetchone()
  conn.close()

  kb_audio = types.InlineKeyboardMarkup()
  kb_audio.add(
      types.InlineKeyboardButton(
          text="🎵 دانلود آهنگ این ویدیو", callback_data=f"dl|audio|{url_id}"
      )
  )

  if cached:
    file_id, file_type = cached
    bot.edit_message_text(
        "⚡ <i>ارسال فوری از سرور...</i>",
        call.message.chat.id,
        status_msg.message_id,
    )
    if file_type == "audio":
      bot.send_audio(
          call.message.chat.id,
          file_id,
          caption="🎵 فایل صوتی با موفقیت ارسال شد.",
      )
    else:
      bot.send_video(
          call.message.chat.id,
          file_id,
          caption="🎬 دانلود ویدیو با موفقیت انجام شد.",
          reply_markup=kb_audio,
      )
    bot.delete_message(call.message.chat.id, status_msg.message_id)
    return

  # دانلود با yt-dlp (تنظیم شده بدون نیاز به ffmpeg)
  try:
    ydl_opts = {
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }

    if choice == "audio":
      ydl_opts["format"] = "bestaudio/best"
    else:
      ydl_opts["format"] = (
          f"best[height<={choice}][vcodec!=none][acodec!=none]/best[height<={choice}]/best"
      )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=True)
      filename = ydl.prepare_filename(info)

      title = info.get("title", "ویدیو دانلود شده")
      description = info.get("description", "") or info.get("caption", "")

    bot.edit_message_text(
        "📤 <i>در حال آپلود روی تلگرام...</i>",
        call.message.chat.id,
        status_msg.message_id,
    )

    # ساخت کپشن کامل ویدیو
    caption_text = f"🎬 <b>{title}</b>\n\n"
    if description:
      desc_clean = description[:600]
      caption_text += f"📝 <b>کپشن:</b>\n{desc_clean}\n\n"
    caption_text += f"👤 پشتیبانی: @{SUPPORT_ID}"

    sent_msg = None
    with open(filename, "rb") as f:
      if choice == "audio":
        sent_msg = bot.send_audio(
            call.message.chat.id,
            f,
            caption=f"🎵 آهنگ استخراج شده:\n\n{title}",
        )
        file_id = sent_msg.audio.file_id
        file_type = "audio"
      else:
        sent_msg = bot.send_video(
            call.message.chat.id,
            f,
            caption=caption_text,
            reply_markup=kb_audio,
        )
        file_id = sent_msg.video.file_id
        file_type = "video"

    # ذخیره در کش
    conn = sqlite3.connect("downloader_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
        (cache_key, file_id, file_type),
    )
    conn.commit()
    conn.close()

    bot.delete_message(call.message.chat.id, status_msg.message_id)
    if os.path.exists(filename):
      os.remove(filename)

  except Exception as e:
    bot.edit_message_text(
        f"❌ <b>خطا در دانلود ویدیو:</b>\n<code>{str(e)[:150]}</code>",
        call.message.chat.id,
        status_msg.message_id,
    )


# ==================== اجرای ربات ====================
if __name__ == "__main__":
  if not os.path.exists("downloads"):
    os.makedirs("downloads")

  # راه اندازی سرور وب برای هاست آنلاین (Render)
  keep_alive()

  print("🤖 ربات پیشرفته به‌همراه سرور وب روشن شد...")
  bot.infinity_polling()
