#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
👑 TITAN AI - v9.0 (Image & Text Edition)
- ردود نصية (Streaming) أو ردود كصور فخمة.
- اشتراك إجباري في قناة @HealthUltimate.
- واجهة مستخدم متطورة.
"""
import os, sys, time, json, html, re, threading, requests, sqlite3, base64, textwrap, io
from datetime import date, datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# ============================================================
# ⚙️ الإعدادات
# ============================================================
TELEGRAM_TOKEN = "9180671607:AAHuf7EJA3TjG7yUrYXGOrKwPB0Vq3WqzVU"
API_BASE_URL   = "https://freemodel.in/v1"
API_KEY        = "fm_f75c9423bc6c268585b22e9e567395d9a2d61f72ac87fe53"

ADMIN_ID       = 123456789 # ⚠️ ضع معرفك هنا
DEFAULT_MODEL  = "gpt-4o"
FALLBACK_MODEL = "gpt-3.5-turbo"
DAILY_LIMIT    = 50

CHANNEL_USERNAME = "@HealthUltimate"
CHANNEL_URL = "https://t.me/HealthUltimate"

TG_URL     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MODEL_URL  = API_BASE_URL.rstrip("/") + "/chat/completions"
FILE_URL   = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"
BOT_USERNAME = ""

# رابط خط عربي (Cairo) لاستخدامه في كتابة النص على الصورة
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf"
FONT_PATH = "Cairo-Regular.ttf"

# ============================================================
# 🗄️ قاعدة البيانات (لحفظ وضع الصور لكل مستخدم)
# ============================================================
DB = sqlite3.connect("titan_v9.db", check_same_thread=False)
DB_LOCK = threading.Lock()

def init_db():
    with DB_LOCK:
        c = DB.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users 
                     (chat_id INTEGER PRIMARY KEY, model TEXT, persona TEXT, temp REAL, 
                      msgs_today INTEGER DEFAULT 0, last_date TEXT, is_banned INTEGER DEFAULT 0,
                      img_mode INTEGER DEFAULT 0)""") # img_mode: 0 = نص، 1 = صورة
        c.execute("""CREATE TABLE IF NOT EXISTS history 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT)""")
        DB.commit()
init_db()
TODAY = str(date.today())

def get_user(chat_id):
    global TODAY
    with DB_LOCK:
        c = DB.cursor()
        c.execute("SELECT model, persona, temp, msgs_today, last_date, is_banned, img_mode FROM users WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        if not row:
            default_persona = "أنت مساعد ذكي، فخم، ومحترف. تجيب بوضوح وبأسلوب راقٍ."
            c.execute("INSERT INTO users (chat_id, model, persona, temp, last_date, img_mode) VALUES (?, ?, ?, ?, ?, ?)", 
                      (chat_id, DEFAULT_MODEL, default_persona, 0.7, TODAY, 0))
            DB.commit()
            return DEFAULT_MODEL, default_persona, 0.7, 0, TODAY, 0, 0
        if row[4] != TODAY:
            c.execute("UPDATE users SET msgs_today=0, last_date=? WHERE chat_id=?", (TODAY, chat_id))
            DB.commit()
            row = (row[0], row[1], row[2], 0, TODAY, row[5], row[6])
        return row

def set_user_data(chat_id, key, value):
    with DB_LOCK:
        c = DB.cursor()
        c.execute(f"UPDATE users SET {key}=? WHERE chat_id=?", (value, chat_id))
        DB.commit()

def check_limit(chat_id, role):
    if role == "admin": return True
    _, _, _, msgs, _, banned, _ = get_user(chat_id)
    return msgs < DAILY_LIMIT and not banned

def increment_msg(chat_id):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("UPDATE users SET msgs_today=msgs_today+1 WHERE chat_id=?", (chat_id,))
        DB.commit()

def get_history(chat_id):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("SELECT role, content FROM history WHERE chat_id=? ORDER BY id ASC", (chat_id,))
        return [{"role": r[0], "content": r[1]} for r in c.fetchall()]

def add_history(chat_id, role, content):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("INSERT INTO history (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, role, content))
        DB.commit()

def clear_history(chat_id):
    with DB_LOCK:
        c = DB.cursor()
        c.execute("DELETE FROM history WHERE chat_id=?", (chat_id,))
        DB.commit()

# ============================================================
# 📡 أدوات تلغرام
# ============================================================
def log(msg): print(f"[SYS] {time.strftime('%H:%M:%S')} | {msg}", file=sys.stderr, flush=True)

def api_call(method, **params):
    try:
        r = requests.post(f"{TG_URL}/{method}", json=params, timeout=30)
        return r.json()
    except: return {"ok": False}

def format_text(text):
    text = re.sub(r"```(\w+)?\n?(.*?)```", r"<pre>\2</pre>", text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("&lt;pre&gt;", "<pre>").replace("&lt;/pre&gt;", "</pre>")
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
    return text

def send(chat_id, text, markup=None):
    params = {"chat_id": chat_id, "text": format_text(text), "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup: params["reply_markup"] = markup
    res = api_call("sendMessage", **params)
    if not res.get("ok") and "can't parse entities" in res.get("description", ""):
        params.pop("parse_mode", None)
        params["text"] = text.replace("**", "").replace("```", "")
        res = api_call("sendMessage", **params)
    return res

def edit(chat_id, msg_id, text, markup=None):
    params = {"chat_id": chat_id, "message_id": msg_id, "text": format_text(text), "parse_mode": "HTML"}
    if markup: params["reply_markup"] = markup
    res = api_call("editMessageText", **params)
    if not res.get("ok"):
        desc = res.get("description", "")
        if "message is not modified" in desc: return res
        if "can't parse entities" in desc:
            params.pop("parse_mode", None)
            params["text"] = text.replace("**", "").replace("```", "")
            res = api_call("editMessageText", **params)
    return res

def download_image(file_id):
    try:
        res = api_call("getFile", file_id=file_id)
        if res.get("ok"):
            img = requests.get(f"{FILE_URL}/{res['result']['file_path']}", timeout=10).content
            return base64.b64encode(img).decode('utf-8')
    except: pass
    return None

# ============================================================
# 🖼️ محرك رسم النص على الصور (Image Generator)
# ============================================================
def ensure_font():
    if not os.path.exists(FONT_PATH):
        try:
            r = requests.get(FONT_URL, timeout=30)
            with open(FONT_PATH, 'wb') as f: f.write(r.content)
        except Exception as e:
            log(f"Font download failed: {e}")

def generate_image(text, username):
    ensure_font()
    
    # إعداد الصورة والخلفية الفخمة
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), "#121212") # خلفية داكنة فخمة
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(FONT_PATH, 45)
        font_small = ImageFont.truetype(FONT_PATH, 30)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # إعادة تشكيل النص العربي
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    
    # تقسيم النص لأسطر
    lines = []
    for paragraph in bidi_text.split('\n'):
        wrapped = textwrap.wrap(paragraph, width=40) # 40 حرف في السطر
        lines.extend(wrapped)
        
    # رسم الإطار العلوي
    draw.text((W - 50, 40), "TITAN AI 👑", font=font_small, fill="#f1c40f", anchor="ra")
    draw.line((50, 90, W - 50, 90), fill="#333333", width=2)

    # رسم النص
    y_text = 130
    for line in lines:
        if y_text > H - 100: break # منع الخروج عن الصورة
        draw.text((W - 50, y_text), line, font=font, fill="#ffffff", anchor="ra")
        y_text += 65 # المسافة بين الأسطر
        
    # رسم الإطار السفلي (اسم المستخدم)
    draw.line((50, H - 80, W - 50, H - 80), fill="#333333", width=2)
    draw.text((W - 50, H - 60), f"طلب بواسطة: {username}", font=font_small, fill="#aaaaaa", anchor="ra")

    # حفظ الصورة
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    return img_byte_arr

# ============================================================
# 🔒 نظام الاشتراك الإجباري
# ============================================================
def is_subscribed(user_id):
    res = api_call("getChatMember", chat_id=CHANNEL_USERNAME, user_id=user_id)
    if res.get("ok"):
        if res["result"]["status"] in ["creator", "administrator", "member"]: return True
    return False

def get_join_keyboard():
    return {"inline_keyboard": [
        [{"text": "📢 اشترك في القناة أولاً", "url": CHANNEL_URL}],
        [{"text": "✅ تحقق من الاشتراك", "callback_data": "check_sub"}]
    ]}

# ============================================================
# 🎨 أزرار الواجهة الفخمة
# ============================================================
def kb_main(img_mode):
    img_btn_text = "🖼️ وضع الصور: مفعل ✅" if img_mode else "📝 وضع النص: مفعل ✅"
    return {"inline_keyboard": [
        [{"text": "🧠 الشخصيات", "callback_data": "menu_personas"}, {"text": "🗑️ مسح الذاكرة", "callback_data": "reset"}],
        [{"text": img_btn_text, "callback_data": "toggle_img"}, {"text": "📊 إحصائياتي", "callback_data": "menu_stats"}]
    ]}

def kb_personas():
    return {"inline_keyboard": [
        [{"text": "🧑‍💻 مبرمج خارق", "callback_data": "persona_prog"}, {"text": "🌐 مترجم محترف", "callback_data": "persona_trans"}],
        [{"text": "✍️ كاتب إبداعي", "callback_data": "persona_write"}, {"text": "💼 مستشار أعمال", "callback_data": "persona_biz"}],
        [{"text": "🔙 العودة للقائمة", "callback_data": "main"}]
    ]}

def kb_stop(): return {"inline_keyboard": [[{"text": "🛑 إيقاف التوليد", "callback_data": "stop"}]]}
def kb_final(img_mode): 
    txt = "🖼️ وضع الصور" if img_mode else "📝 وضع النص"
    return {"inline_keyboard": [[{"text": "🔄 إعادة التوليد", "callback_data": "regen"}, {"text": "🏠 القائمة", "callback_data": "main"}]]}

# ============================================================
# 🧠 محرك التوليد
# ============================================================
BUSY_USERS = set()
STOP_EVENTS = {}

def thinking_animation(chat_id, msg_id, stop_event):
    frames = ["⏳ جاري التفكير", "🧠 تحليل الطلب", "💭 صياغة الإجابة", "🎨 رسم الصورة" ]
    i = 0
    while not stop_event.is_set():
        edit(chat_id, msg_id, f"*{frames[i % 4]}...*", kb_stop())
        stop_event.wait(1.5)
        i += 1

def generate(chat_id, msg_id, text, img_b64=None, role="user"):
    if not check_limit(chat_id, role):
        edit(chat_id, msg_id, "⚠️ **لقد وصلت للحد الأقصى اليومي (50 رسالة).**\nيرجى المحاولة غداً.", kb_main(0))
        return

    BUSY_USERS.add(chat_id)
    if chat_id not in STOP_EVENTS: STOP_EVENTS[chat_id] = threading.Event()
    STOP_EVENTS[chat_id].clear()

    stop_anim = threading.Event()
    threading.Thread(target=thinking_animation, args=(chat_id, msg_id, stop_anim), daemon=True).start()

    model, persona, temp, _, _, _, img_mode = get_user(chat_id)
    history = get_history(chat_id)[-10:] 
    
    content = text if not img_b64 else [{"type": "text", "text": text or "حلل الصورة"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]
    messages = [{"role": "system", "content": persona}] + history + [{"role": "user", "content": content}]
    
    payload = {"model": model, "messages": messages, "temperature": float(temp), "stream": True if not img_mode else False}
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    full_text, last_edit = "", time.time()
    success = False

    for current_model in [model, FALLBACK_MODEL]:
        try:
            payload["model"] = current_model
            with requests.post(MODEL_URL, headers=headers, json=payload, stream=(not img_mode), timeout=90) as r:
                if r.status_code != 200: continue
                success = True
                if img_mode:
                    # الوضع المباشر (بدون بث)
                    full_text = r.json()["choices"][0]["message"]["content"]
                else:
                    # وضع البث
                    for line in r.iter_lines():
                        if STOP_EVENTS[chat_id].is_set(): break
                        if line and line.startswith(b"data: "):
                            data = line[6:].decode()
                            if data == "[DONE]": break
                            try:
                                chunk = json.loads(data)["choices"][0]["delta"].get("content", "")
                                if chunk:
                                    stop_anim.set()
                                    full_text += chunk
                                    if time.time() - last_edit > 1.2:
                                        edit(chat_id, msg_id, full_text + " ▌", kb_stop())
                                        last_edit = time.time()
                            except: pass
                    break
        except: pass

    stop_anim.set()
    BUSY_USERS.discard(chat_id)

    if not success or not full_text.strip():
        edit(chat_id, msg_id, "⚠️ تعذر الاتصال بالموديل.", kb_main(img_mode))
        return

    add_history(chat_id, "user", text if not img_b64 else f"[صورة] {text}")
    add_history(chat_id, "assistant", full_text)
    increment_msg(chat_id)

    # إذا كان وضع الصور مفعلاً، نرسم النص ونرسله كصورة
    if img_mode:
        edit(chat_id, msg_id, "🎨 *جاري رسم الإجابة على صورة فخمة...*")
        user_name = "المستخدم"
        img_file = generate_image(full_text, user_name)
        
        # حذف رسالة الانتظار وإرسال الصورة
        api_call("deleteMessage", chat_id=chat_id, message_id=msg_id)
        files = {'photo': ('response.jpg', img_file)}
        data = {'chat_id': chat_id, 'caption': '👑 **TITAN AI**', 'parse_mode': 'HTML', 'reply_markup': json.dumps(kb_final(img_mode))}
        requests.post(f"{TG_URL}/sendPhoto", data=data, files=files)
    else:
        # الوضع النصي العادي
        edit(chat_id, msg_id, full_text, kb_final(img_mode))

# ============================================================
# 🕹️ الأحداث
# ============================================================
def setup_commands():
    commands = [
        {"command": "start", "description": "بدء تشغيل البوت"},
        {"command": "menu", "description": "عرض لوحة التحكم"},
        {"command": "clear", "description": "مسح الذاكرة"},
        {"command": "id", "description": "معرفة معرف الحساب"}
    ]
    api_call("setMyCommands", commands=commands)

def on_message(msg):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text = msg.get("text", "")
    role = "admin" if user_id == ADMIN_ID else "user"

    # التحقق من الاشتراك الإجباري
    if user_id != ADMIN_ID and not is_subscribed(user_id):
        send(chat_id, "⚠️ **عذراً، يجب عليك الاشتراك في قناتنا أولاً.**", get_join_keyboard())
        return

    user_first_name = msg["from"].get("first_name", "")
    user_username = msg["from"].get("username", "")
    _, _, _, _, _, _, img_mode = get_user(chat_id)

    if text in ["/start", "/menu"]:
        current_hour = datetime.now().hour
        greeting = "🌅 صباح الخير" if 5 <= current_hour < 12 else "☀️ طاب يومك" if 12 <= current_hour < 18 else "🌙 مساء الخير"
        display_name = f"يا {user_first_name}" if user_first_name else "بك"
        
        welcome = (
            f"👑 **{greeting} {display_name}**\n\n"
            "أنا مساعدك الشخصي. يمكنك الآن اختيار طريقة عرض الإجابات:\n"
            "1️⃣ **وضع النص:** يكتب الإجابة مباشرة كرسالة.\n"
            "2️⃣ **وضع الصور:** يحول الإجابة إلى صورة فخمة (تأخذ وقتاً أطول قليلاً)."
        )
        send(chat_id, welcome, kb_main(img_mode))
        return

    if text == "/id":
        send(chat_id, f"🆔 معرفك: `{user_id}`")
    elif text == "/clear":
        clear_history(chat_id)
        send(chat_id, "🧹 **تم مسح الذاكرة.**", kb_main(img_mode))
    elif chat_id in BUSY_USERS:
        send(chat_id, "⏳ يرجى الانتظار...")
    else:
        init = send(chat_id, "*⏳ جاري التفكير...*", kb_stop())
        if init.get("ok"):
            msg_id = init["result"]["message_id"]
            if msg.get("photo"):
                b64 = download_image(msg["photo"][-1]["file_id"])
                threading.Thread(target=generate, args=(chat_id, msg_id, text, b64, role)).start()
            elif text:
                threading.Thread(target=generate, args=(chat_id, msg_id, text, None, role)).start()

def on_callback(cb):
    cb_id, chat_id, msg_id, data = cb["id"], cb["message"]["chat"]["id"], cb["message"]["message_id"], cb["data"]
    user_id = cb.get("from", {}).get("id", chat_id)
    role = "admin" if user_id == ADMIN_ID else "user"
    
    _, _, _, _, _, _, img_mode = get_user(chat_id)

    if data == "check_sub":
        if is_subscribed(user_id):
            api_call("answerCallbackQuery", callback_query_id=cb_id, text="✅ تم التحقق!", show_alert=False)
            edit(chat_id, msg_id, "🎉 **تم التحقق من اشتراكك بنجاح!**\nأرسل /start للبدء.", kb_main(img_mode))
        else:
            api_call("answerCallbackQuery", callback_query_id=cb_id, text="❌ لم تشترك بعد!", show_alert=True)
        return

    api_call("answerCallbackQuery", callback_query_id=cb_id)

    if data == "main": 
        edit(chat_id, msg_id, "🏠 **القائمة الرئيسية:**", kb_main(img_mode))
    elif data == "toggle_img":
        new_mode = 1 if img_mode == 0 else 0
        set_user_data(chat_id, "img_mode", new_mode)
        msg = "🖼️ **تم تفعيل وضع الصور.** سأقوم برسم الإجابات على صورة." if new_mode else "📝 **تم تفعيل وضع النص.** سأكتب الإجابات مباشرة."
        edit(chat_id, msg_id, msg, kb_main(new_mode))
    elif data == "menu_personas": 
        edit(chat_id, msg_id, "🧠 **اختر الشخصية:**", kb_personas())
    elif data.startswith("persona_"):
        p_type = data.split("_")[1]
        prompts = {"prog": "أنت مبرمج خبير.", "trans": "أنت مترجم محترف.", "write": "أنت كاتب إبداعي.", "biz": "أنت مستشار أعمال."}
        set_user_data(chat_id, "persona", prompts.get(p_type, "مساعد ذكي"))
        edit(chat_id, msg_id, "✅ **تم تغيير الشخصية بنجاح.**", kb_main(img_mode))
    elif data == "menu_stats":
        _, _, temp, msgs, _, _, _ = get_user(chat_id)
        mode_text = "صور 🖼️" if img_mode else "نص 📝"
        edit(chat_id, msg_id, f"📊 **إحصائياتك:**\n\n💬 الرسائل: {msgs}/{DAILY_LIMIT}\n⚙️ الوضع الحالي: {mode_text}", kb_main(img_mode))
    elif data == "reset":
        clear_history(chat_id)
        edit(chat_id, msg_id, "🧹 **تم مسح الذاكرة.**", kb_main(img_mode))
    elif data == "stop":
        if chat_id in STOP_EVENTS: STOP_EVENTS[chat_id].set()
    elif data == "regen":
        hist = get_history(chat_id)
        if hist and hist[-1]["role"] == "user":
            init = send(chat_id, "*🔄 جاري إعادة التوليد...*", kb_stop())
            if init.get("ok"):
                threading.Thread(target=generate, args=(chat_id, init["result"]["message_id"], hist[-1]["content"], None, role)).start()

# ============================================================
# ⚡ التشغيل
# ============================================================
def main():
    global BOT_USERNAME
    me = api_call("getMe")
    if not me.get("ok"): sys.exit("❌ توكن البوت غير صالح.")
    BOT_USERNAME = me["result"]["username"]
    log(f"👑 TITAN AI v9.0 يعمل: @{BOT_USERNAME}")
    
    ensure_font() # تحميل الخط عند بدء التشغيل
    setup_commands()
    offset = None
    
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
            if offset: params["offset"] = offset
            upd = api_call("getUpdates", **params)
            if not upd.get("ok"): time.sleep(3); continue
                
            for u in upd["result"]:
                offset = u["update_id"] + 1
                if "message" in u: on_message(u["message"])
                elif "callback_query" in u: on_callback(u["callback_query"])
        except Exception as e:
            log(f"Loop Error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nتوقف.")