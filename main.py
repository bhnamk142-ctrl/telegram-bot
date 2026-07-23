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
MAIN_ADMIN_ID = 8443938939  # آیدی عددی ادمین اصلی (شما)
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
      "CREATE TABLE IF NOT EXISTS vip_users (user_id INTEGER PRIMARY KEY,"
      " expire_timestamp REAL)"
  )
  # جدول جدید برای ذخیره آیدی ادمین‌های ربات
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)"
  )

  # ثبت ادمین اصلی در جدول ادمین‌ها به صورت پیش‌فرض
  cursor.execute(
      "INSERT OR IGNORE INTO admins VALUES (?)", (MAIN_ADMIN_ID,)
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


# ==================== توابع بررسی ادمین ====================
def is_admin(user_id):
  if int(user_id) == int(MAIN_ADMIN_ID):
    return True
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
  res = cursor.fetchone()
  conn.close()
  return res is not None


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
    expire_time = res[0]
    if time.time() < expire_time:
      return True
    else:
      conn = sqlite3.connect("downloader_bot.db")
      c = conn.cursor()
      c.execute("DELETE FROM vip_users WHERE user_id=?", (user_id,))
      conn.commit()
      conn.close()
  return False


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
    kb.add(
        types.InlineKeyboardButton(
            text="⭐ خرید اشتراک VIP (رد شدن از جوین اجباری)",
            callback_data="buy_vip_stars",
        )
    )

    bot.send_message(
        message.chat.id,
        "⚠️ <b>برای استفاده از خدمات ربات، ابتدا باید در کانال/گروه‌های زیر"
        " عضو شوید یا اشتراک VIP تهیه کنید:</b>",
        reply_markup=kb,
    )
    return

  icon, _ = get_theme_emoji()
  welcome_text = get_setting("welcome_msg")
  welcome_text = (
      f"سلام <b>{first_name}</b> عزیز! ❤️ خوش آمدی!\n\n{welcome_text}\n\n"
      "با این ربات می‌تونی ویدیوهای <b>اینستاگرام، یوتیوب و تیک‌تاک</b> رو با"
      " بالاترین کیفیت دانلود کنی!\n\n"
      "👇 لینک ویدیو رو برام بفرست:"
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
          text="⭐ خرید اشتراک VIP", callback_data="buy_vip_stars"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="👤 پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      )
  )

  # اگر کاربر ادمین بود دکمه پنل مدیریت را نشان بده
  if is_admin(user_id):
    kb.add(
        types.InlineKeyboardButton(
            text="⚙️ پنل مدیریت ربات", callback_data="open_admin_panel"
        )
    )

  bot.send_message(
      message.chat.id, welcome_text, reply_markup=kb, parse_mode="HTML"
  )


@bot.callback_query_handler(func=lambda call: call.data == "buy_vip_stars")
def buy_vip_stars_handler(call):
  prices = [types.LabeledPrice(label="اشتراک VIP ۳۰ روزه ربات", amount=29)]
  try:
    bot.send_invoice(
        chat_id=call.message.chat.id,
        title="اشتراک VIP ربات دانلودر",
        description="با خرید این اشتراک، برای همیشه از جوین اجباری کانال‌ها معاف می‌شوید!",
        invoice_payload="vip_subscription_30d",
        provider_token="",
        currency="XTR",
        prices=prices,
    )
  except Exception as e:
    bot.answer_callback_query(
        call.id, f"❌ خطا در ایجاد فاکتور پرداخت: {e}", show_alert=True
    )


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
      "🎉 <b>پرداخت با موفقیت انجام شد!</b>\nشما اکنون کاربر <b>VIP</b> ربات شدید"
      " و محدودیت جوین اجباری برای شما برداشته شد. ❤️",
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
    bot.delete_message(call.message.chat.id, call.message.message_id)
    start_cmd(call.message)


# ==================== پنل مدیریت پیشرفته ====================
def show_admin_panel_content(chat_id):
  icon, _ = get_theme_emoji()
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT COUNT(*) FROM users")
  total_users = cursor.fetchone()[0]
  cursor.execute("SELECT SUM(usage_count) FROM users")
  total_usage = cursor.fetchone()[0] or 0
  cursor.execute("SELECT COUNT(*) FROM admins")
  total_admins = cursor.fetchone()[0]

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
          f"\n{idx}. <code>{ch_id}</code> ({c_type})\n └ سقف ممبر: {limit_str} |"
          f" زمان: {time_str}\n"
      )
  else:
    fj_status = "هیچ کانال/گروهی فعال نیست"

  text = (
      "👑 <b>پنل مدیریت جامع و قدرتمند ربات</b>\n\n"
      f"👥 کل کاربران: <code>{total_users}</code> نفر\n"
      f"📊 کل دانلودها: <code>{total_usage}</code> بار\n"
      f"🛡️ تعداد ادمین‌ها: <code>{total_admins}</code> نفر\n"
      "🎨 رنگ کنونی دکمه‌ها:"
      f" <b>{get_setting('theme_color').upper()}</b>\n\n"
      f"📢 <b>لیست جوین اجباری فعلی:</b>\n{fj_status}"
  )

  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text=f"{icon} افزودن کانال/گپ جوین اجباری (با سقف ممبر و زمان)",
          callback_data="adm_add_fj",
      ),
      types.InlineKeyboardButton(
          text=f"{icon} حذف کامل موارد جوین اجباری", callback_data="adm_clear_fj"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} مدیریت ادمین‌ها (افزودن / لیست)",
          callback_data="adm_manage_admins",
      ),
      types.InlineKeyboardButton(
          text=f"{icon} ارسال پیام همگانی", callback_data="adm_broadcast"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} تغییر متن خوش‌آمدگویی", callback_data="adm_set_welcome"
      ),
      types.InlineKeyboardButton(
          text=f"{icon} تغییر رنگ دکمه‌ها", callback_data="adm_change_theme"
      ),
  )
  bot.send_message(chat_id, text, reply_markup=kb)


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
    return
  bot.answer_callback_query(call.id)
  show_admin_panel_content(call.message.chat.id)


# ==================== مدیریت ادمین‌ها ====================
@bot.callback_query_handler(func=lambda call: call.data == "adm_manage_admins")
def manage_admins_menu(call):
  if not is_admin(call.from_user.id):
    return
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

  bot.edit_message_text(
      f"🛡️ <b>لیست ادمین‌های ربات:</b>\n\n{admins_str}\n\nبرای افزودن یا حذف"
      " ادمین، دکمه‌های زیر را انتخاب کنید:",
      call.message.chat.id,
      call.message.message_id,
      reply_markup=kb,
  )


@bot.callback_query_handler(func=lambda call: call.data == "adm_add_admin")
def ask_new_admin_id(call):
  if int(call.from_user.id) != int(
      MAIN_ADMIN_ID
  ):  # فقط ادمین اصلی می‌تواند ادمین اضافه کند
    bot.answer_callback_query(
        call.id,
        "❌ فقط ادمین اصلی اجازه افزودن ادمین جدید را دارد!",
        show_alert=True,
    )
    return

  msg = bot.send_message(
      call.message.chat.id,
      "➕ <b>آیدی عددی (User ID)</b> کاربر مورد نظر را برای اعطای دسترسی ادمین"
      " ارسال کنید:\n(می‌توانید از ربات‌های آی‌دی‌یاب بگیرید)",
  )
  bot.register_next_step_handler(msg, save_new_admin)


def save_new_admin(message):
  if not is_admin(message.from_user.id):
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
    msg = bot.send_message(
        message.chat.id,
        "❌ فرمت اشتباه است! لطفاً فقط یک عدد صحیح (آیدی عددی) بفرستید:",
    )
    bot.register_next_step_handler(msg, save_new_admin)


@bot.callback_query_handler(func=lambda call: call.data == "adm_del_admin")
def ask_del_admin_id(call):
  if int(call.from_user.id) != int(MAIN_ADMIN_ID):
    bot.answer_callback_query(
        call.id,
        "❌ فقط ادمین اصلی اجازه حذف ادمین‌ها را دارد!",
        show_alert=True,
    )
    return

  msg = bot.send_message(
      call.message.chat.id,
      "➖ <b>آیدی عددی (User ID)</b> ادمینی که می‌خواهید دسترسی‌اش را بگیرید"
      " ارسال کنید:",
  )
  bot.register_next_step_handler(msg, process_del_admin)


def process_del_admin(message):
  if not is_admin(message.from_user.id):
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
    msg = bot.send_message(message.chat.id, "❌ لطفاً فقط یک عدد صحیح بفرستید:")
    bot.register_next_step_handler(msg, process_del_admin)


# ==================== ویزارد افزودن جوین اجباری (گام‌به‌گام) ====================
admin_wizard = {}


@bot.callback_query_handler(func=lambda call: call.data == "adm_add_fj")
def wizard_start(call):
  if not is_admin(call.from_user.id):
    return
  active = get_active_forced_joins()
  if len(active) >= 5:
    bot.answer_callback_query(
        call.id,
        "❌ حداکثر ۵ کانال/گروه همزمان می‌تواند فعال باشد!",
        show_alert=True,
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
  if not is_admin(message.from_user.id):
    return
  try:
    parts = message.text.strip().split()
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
    bot.send_message(
        message.chat.id,
        "📂 <b>مرحله ۲ از ۴:</b>\n\nنوع محیط را انتخاب کنید:",
        reply_markup=kb,
    )
  except Exception:
    msg = bot.send_message(
        message.chat.id,
        "❌ فرمت اشتباه است! لطفاً طبق نمونه بفرستید:\n<code>@MyChannel"
        " https://t.me/MyChannel</code>",
    )
    bot.register_next_step_handler(msg, wizard_get_link)


@bot.callback_query_handler(func=lambda call: call.data.startswith("wiz_type_"))
def wizard_get_type(call):
  if not is_admin(call.from_user.id):
    return
  admin_wizard[call.from_user.id]["chat_type"] = call.data.split("_")[2]

  kb = types.InlineKeyboardMarkup(row_width=1)
  kb.add(
      types.InlineKeyboardButton(
          text="♾️ بی‌نهایت (بدون سقف ممبر)", callback_data="wiz_limit_inf"
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
  try:
    limit = int(message.text.strip())
    admin_wizard[message.from_user.id]["limit"] = limit
    wizard_ask_duration(message.chat.id)
  except Exception:
    msg = bot.send_message(
        message.chat.id, "❌ لطفاً فقط یک عدد صحیح وارد کنید (مثلاً 50):"
    )
    bot.register_next_step_handler(msg, wizard_get_limit)


@bot.callback_query_handler(func=lambda call: call.data == "wiz_limit_inf")
def wizard_limit_inf(call):
  if not is_admin(call.from_user.id):
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
      " وارد کنید (مثلاً <code>24</code> برای یک شبانه‌روز) یا روی دکمه دائمی"
      " بزنید:",
      reply_markup=kb,
  )
  bot.register_next_step_handler(msg, wizard_get_hours)


def wizard_get_hours(message):
  if not is_admin(message.from_user.id):
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
  if not is_admin(call.from_user.id):
    return
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

  del admin_wizard[user_id]

  limit_str = f"{limit} نفر" if limit != -1 else "بی‌نهایت"
  time_str = f"{hours} ساعت" if hours != -1 else "دائمی"
  bot.send_message(
      chat_id,
      "✅ <b>کانال/گپ با موفقیت به سیستم جوین اجباری اضافه شد!</b>\n\n"
      f"🔹 آیدی: <code>{chat_id_ch}</code>\n"
      f"🔢 سقف ممبر: <b>{limit_str}</b>\n"
      f"⏳ زمان ماندگاری: <b>{time_str}</b>",
  )


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
    bot.answer_callback_query(
        call.id,
        "✅ تمامی کانال‌های جوین اجباری پاک شدند.",
        show_alert=True,
    )
    show_admin_panel_content(call.message.chat.id)

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
        "🎨 <b>رنگ تم دکمه‌ها را انتخاب کنید:</b>",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("theme_"))
def set_theme_callback(call):
  color = call.data.split("_")[1]
  set_setting("theme_color", color)
  bot.answer_callback_query(
      call.id,
      f"✅ تم دکمه‌ها به {color.upper()} تغییر یافت.",
      show_alert=True,
  )
  show_admin_panel_content(call.message.chat.id)


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


# ==================== دریافت لینک و دانلود ====================
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
          text="🎵 دانلود موزیک (MP3)", callback_data=f"dl|audio|{url_id}"
      )
  )
  kb.add(
      types.InlineKeyboardButton(
          text="👤 پشتیبانی", url=f"https://t.me/{SUPPORT_ID}"
      )
  )

  bot.reply_to(message, "🎬 کیفیت مورد نظر را انتخاب کنید:", reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dl|"))
def process_download_choice(call):
  _, choice, url_id = call.data.split("|", 2)
  url = get_pending_url(url_id)

  if not url:
    bot.answer_callback_query(
        call.id, "❌ منقضی شده است! لینک را دوباره بفرستید.", show_alert=True
    )
    return

  bot.answer_callback_query(call.id, "⏳ در حال دانلود...")
  status_msg = bot.send_message(
      call.message.chat.id, "🔄 <i>در حال پردازش...</i>"
  )

  cache_key = f"{choice}_{url_id}"
  conn = sqlite3.connect("downloader_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT file_id, file_type FROM cache WHERE url_hash=?", (cache_key,)
  )
  cached = cursor.fetchone()
  conn.close()

  if cached:
    file_id, file_type = cached
    bot.edit_message_text(
        "⚡ <i>ارسال فوری...</i>",
        call.message.chat.id,
        status_msg.message_id,
    )
    if file_type == "audio":
      bot.send_audio(
          call.message.chat.id, file_id, caption="🎵 فایل صوتی استخراج شده."
      )
    else:
      bot.send_video(
          call.message.chat.id, file_id, caption="🎬 ویدیوی دانلود شده."
      )
    bot.delete_message(call.message.chat.id, status_msg.message_id)
    return

  try:
    ydl_opts = {"outtmpl": "downloads/%(id)s.%(ext)s", "quiet": True}
    if choice == "audio":
      ydl_opts["format"] = "bestaudio/best"
    else:
      ydl_opts["format"] = f"best[height<={choice}]/best"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=True)
      filename = ydl.prepare_filename(info)
      title = info.get("title", "ویدیو")

    bot.edit_message_text(
        "📤 <i>در حال آپلود روی تلگرام...</i>",
        call.message.chat.id,
        status_msg.message_id,
    )

    with open(filename, "rb") as f:
      if choice == "audio":
        sent_msg = bot.send_audio(
            call.message.chat.id, f, caption=f"🎵 {title}"
        )
        file_id = sent_msg.audio.file_id
        file_type = "audio"
      else:
        sent_msg = bot.send_video(
            call.message.chat.id, f, caption=f"🎬 <b>{title}</b>"
        )
        file_id = sent_msg.video.file_id
        file_type="video"

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
        f"❌ خطا در دانلود:\n<code>{str(e)[:150]}</code>",
        call.message.chat.id,
        status_msg.message_id,
    )


# ==================== اجرای ربات با ضد قطعی ====================
if __name__ == "__main__":
  if not os.path.exists("downloads"):
    os.makedirs("downloads")

  keep_alive()
  print(
      "🤖 ربات کامل همراه با مدیریت ادمین‌ها و پنل مدیریت همه‌فن‌حریف روشن"
      " شد..."
  )

  while True:
    try:
      bot.infinity_polling(
          skip_pending=True, timeout=90, long_polling_timeout=60
      )
    except Exception as e:
      print(f"⚠️ خطای موقت اتصال: {e}")
      time.sleep(5)
