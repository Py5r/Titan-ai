#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏆 TITAN AI - المنصة المتكاملة (الإصدار الأسطوري)
- ذاكرة دائمة (SQLite)، دعم الصور (Vision)، الوضع المضمن (Inline Mode).
- شخصيات متعددة، تصدير المحادثات، وواجهة مستخدم احترافية.
"""
import os, sys, time, json, html, re, threading, requests, sqlite3, base64
from datetime import datetime

# ============================================================
# ⚙️ الإعدادات
# ============================================================
TELEGRAM_TOKEN = "9180671607:AAHuf7EJA3TjG7yUrYXGOrKwPB0Vq3WqzVU"
API_BASE_URL   = "https://freemodel.in/v1"
API_KEY        = "fm_f75c9423bc6c268585b22e9e567395d9a2d61f72ac87fe53"
DEFAULT_MODEL  = "gpt-4o"

TG_URL     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
MODEL_URL  = API_BASE_URL.rstrip("/") + "/chat/completions"
MODELS_URL = API_BASE_URL.rstrip("/") + "/models"
FILE_URL   = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}"

# ============================================================
# 🗄️ قاعدة البيانات (لحفظ الإعدادات والمحادثات)
# ============================================================
DB_CONN = sqlite3.connect("titan_ai.db", check_same_thread=False)
DB_LOCK = threading.Lock()

def init_db():
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users 
                     (chat_id INTEGER PRIMARY KEY, model TEXT, persona TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS history 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT, timestamp DATETIME)""")
        DB_CONN.commit()

init_db()

def get_user(chat_id):
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("SELECT model, persona FROM users WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO users (chat_id, model, persona) VALUES (?, ?, ?)", 
                      (chat_id, DEFAULT_MODEL, "مساعد ذكي ومحترف يجيب بوضوح."))
            DB_CONN.commit()
            return DEFAULT_MODEL, "مساعد ذكي ومحترف يجيب بوضوح."
        return row[0], row[1]

def set_user_model(chat_id, model):
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("UPDATE users SET model=? WHERE chat_id=?", (model, chat_id))
        DB_CONN.commit()

def set_user_persona(chat_id, persona):
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("UPDATE users SET persona=? WHERE chat_id=?", (persona, chat_id))
        DB_CONN.commit()

def get_history(chat_id):
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("SELECT role, content FROM history WHERE chat_id=? ORDER BY id ASC", (chat_id,))
        return [{"role": r[0], "content": r[1]} for r in c.fetchall()]

def add_history(chat_id, role, content):
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("INSERT INTO history (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                  (chat_id, role, content, datetime.now()))
        DB_CONN.commit()

def clear_history(chat_id):
    with DB_LOCK:
        c = DB_CONN.cursor()
        c.execute("DELETE FROM history WHERE chat_id=?", (chat_id,))
        DB_CONN.commit()

# ============================================================
# 📡 أدوات تلغرام والتنسيق
# ============================================================
def log(msg):
    print(f"[TITAN] {time.strftime('%H:%M:%S')} | {msg}", file=sys.stderr, flush=True)

def api_call(method, **params):
    try:
        r = requests.post(f"{TG_URL}/{method}", json=params, timeout=30)
        return r.json()
    except Exception as e:
        log(f"API Error: {e}")
        return {"ok": False}

def html_format(text):
    text = html.escape(text)
    text = re.sub(r"```(?:\w+)?\n?(.*?)```", r"<pre><code>\1</code></pre>", text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    return text

def send(chat_id, text, markup=None):
    params = {"chat_id": chat_id, "text": html_format(text), "parse_mode": "HTML", "disable_web_page_preview": True}
    if markup: params["reply_markup"] = markup
    return api_call("sendMessage", **params)

def edit(chat_id, msg_id, text, markup=None):
    params = {"chat_id": chat_id, "message_id": msg_id, "text": html_format(text), "parse_mode": "HTML"}
    if markup: params["reply_markup"] = markup
    res = api_call("editMessageText", **params)
    if not res.get("ok") and "message is not modified" not in res.get("description", ""):
        if "can't parse entities" in res.get("description", ""):
            params.pop("parse_mode", None)
            params["text"] = text
            api_call("editMessageText", **params)
    return res

def download_photo(file_id):
    """تحميل الصورة من تلغرام وتحويلها إلى Base64"""
    try:
        res = api_call("getFile", file_id=file_id)
        if not res.get("ok"): return None
        file_path = res["result"]["file_path"]
        r = requests.get(f"{FILE_URL}/{file_path}", timeout=15)
        if r.ok:
            return base64.b64encode(r.content).decode('utf-8')
    except Exception as e:
        log(f"Photo Error: {e}")
    return None

# ============================================================
# 🎨 واجهات المستخدم (UI)
# ============================================================
def kb_main():
    return {"inline_keyboard": [
        [{"text": "💬 الدردشة المباشرة", "callback_data": "menu_chat"}],
        [{"text": "🤖 الموديلات", "callback_data": "menu_models_0"}, {"text": "🧠 الشخصيات", "callback_data": "menu_personas"}],
        [{"text": "📊 إحصائياتي", "callback_data": "menu_stats"}, {"text": "⚙️ الإعدادات", "callback_data": "menu_settings"}]
    ]}

def kb_models(page=0):
    global MODELS_CACHE
    if not MODELS_CACHE: return {"inline_keyboard": [[{"text": "🔄 تحديث", "callback_data": "menu_models_0"}]]}
    per_page = 6
    start, end = page * per_page, (page * per_page) + per_page
    rows, row = [], []
    for i, m in enumerate(MODELS_CACHE[start:end], start=start):
        icon = "🟢" if "gpt" in m.lower() else "🔵" if "claude" in m.lower() else "🟡" if "gemini" in m.lower() else "⚪"
        row.append({"text": f"{icon} {m[:20]}", "callback_data": f"set_m_{i}"})
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    nav = []
    if page > 0: nav.append({"text": "⬅️", "callback_data": f"menu_models_{page-1}"})
    if end < len(MODELS_CACHE): nav.append({"text": "➡️", "callback_data": f"menu_models_{page+1}"})
    if nav: rows.append(nav)
    rows.append([{"text": "🔙 عودة", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}

def kb_personas():
    return {"inline_keyboard": [
        [{"text": "🧑‍💻 مبرمج", "callback_data": "set_p_1"}, {"text": "🌐 مترجم", "callback_data": "set_p_2"}],
        [{"text": "✍️ كاتب محتوى", "callback_data": "set_p_3"}, {"text": "💼 خبير أعمال", "callback_data": "set_p_4"}],
        [{"text": "🔙 عودة", "callback_data": "menu_main"}]
    ]}

def kb_stop_regen():
    return {"inline_keyboard": [[{"text": "🛑 إيقاف", "callback_data": "stop"}, {"text": "🔄 إعادة", "callback_data": "regen"}]]}

def kb_final():
    return {"inline_keyboard": [
        [{"text": "🔄 إعادة توليد", "callback_data": "regen"}, {"text": "🗑️ مسح", "callback_data": "clear"}],
        [{"text": "🏠 القائمة", "callback_data": "menu_main"}]
    ]}

# ============================================================
# 🧠 الذكاء الاصطناعي (AI Core)
# ============================================================
MODELS_CACHE = []
STOP_EVENTS = {}

def fetch_models():
    global MODELS_CACHE
    try:
        r = requests.get(MODELS_URL, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)
        if r.ok:
            MODELS_CACHE = sorted([m["id"] for m in r.json().get("data", [])])
    except: pass

def generate_ai(chat_id, msg_id, text, image_b64=None):
    model, persona = get_user(chat_id)
    if chat_id not in STOP_EVENTS: STOP_EVENTS[chat_id] = threading.Event()
    STOP_EVENTS[chat_id].clear()

    history = get_history(chat_id)
    
    # بناء الرسالة (نص أو صورة)
    if image_b64:
        user_content = [
            {"type": "text", "text": text or "ماذا يوجد في هذه الصورة؟"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]
    else:
        user_content = text

    messages = [{"role": "system", "content": persona}] + history + [{"role": "user", "content": user_content}]
    
    payload = {"model": model, "messages": messages, "stream": True}
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    full_text = ""
    last_edit = time.time()

    try:
        with requests.post(MODEL_URL, headers=headers, json=payload, stream=True, timeout=90) as r:
            if r.status_code != 200:
                edit(chat_id, msg_id, "⚠️ **خطأ:** الموديل لا يدعم هذا النوع من الطلبات أو غير متاح.")
                return

            for line in r.iter_lines():
                if STOP_EVENTS[chat_id].is_set(): break
                if line and line.startswith(b"data: "):
                    data = line[6:].decode()
                    if data == "[DONE]": break
                    try:
                        chunk = json.loads(data)["choices"][0]["delta"].get("content", "")
                        if chunk:
                            full_text += chunk
                            if time.time() - last_edit > 1.2:
                                edit(chat_id, msg_id, full_text + " ▌", kb_stop_regen())
                                last_edit = time.time()
                    except: pass
    except Exception as e:
        log(f"Stream Error: {e}")
        if not full_text:
            edit(chat_id, msg_id, "⚠️ انقطع الاتصال بالشبكة.")
            return

    if not full_text.strip():
        edit(chat_id, msg_id, "⚠️ لم يتم استلام رد.")
        return

    # حفظ في الذاكرة
    add_history(chat_id, "user", text if not image_b64 else f"[صورة مرفقة] {text}")
    add_history(chat_id, "assistant", full_text)

    # تقسيم النص إذا كان طويلاً
    chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
    edit(chat_id, msg_id, chunks[0], kb_final() if len(chunks)==1 else None)
    for c in chunks[1:]:
        send(chat_id, c, kb_final())

# ============================================================
# 🕹️ معالجة الأحداث (Handlers)
# ============================================================
def handle_message(msg):
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    photo = msg.get("photo")

    if text == "/start":
        send(chat_id, "🏆 **مرحباً بك في TITAN AI**\n\nمنصة ذكاء اصطناعي متكاملة.\nأرسل نصاً، أو صورة، أو استخدم الأزرار أدناه.", kb_main())
    elif text == "/menu":
        send(chat_id, "🏠 **القائمة الرئيسية:**", kb_main())
    elif text == "/clear":
        clear_history(chat_id)
        send(chat_id, "🗑️ **تم مسح الذاكرة بالكامل.**", kb_main())
    elif text == "/export":
        history = get_history(chat_id)
        if not history:
            send(chat_id, "لا يوجد محادثات لتصديرها.")
            return
        content = "\n\n".join([f"[{h['role'].upper()}]\n{h['content']}" for h in history])
        # إرسال كملف
        files = {'document': ('chat_history.txt', content.encode('utf-8'))}
        requests.post(f"{TG_URL}/sendDocument", data={'chat_id': chat_id}, files=files)
    elif text:
        init = send(chat_id, "⏳ **جاري التفكير...**", kb_stop_regen())
        if init.get("ok"):
            threading.Thread(target=generate_ai, args=(chat_id, init["result"]["message_id"], text)).start()
    elif photo:
        init = send(chat_id, "🖼️ **جاري تحليل الصورة...**", kb_stop_regen())
        if init.get("ok"):
            b64 = download_photo(photo[-1]["file_id"])
            if b64:
                threading.Thread(target=generate_ai, args=(chat_id, init["result"]["message_id"], text, b64)).start()
            else:
                edit(chat_id, init["result"]["message_id"], "⚠️ فشل تحميل الصورة.")

def handle_callback(cb):
    cb_id = cb["id"]
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    data = cb["data"]

    api_call("answerCallbackQuery", callback_query_id=cb_id)

    if data == "menu_main":
        edit(chat_id, msg_id, "🏠 **القائمة الرئيسية:**", kb_main())
    elif data.startswith("menu_models_"):
        if not MODELS_CACHE: fetch_models()
        page = int(data.split("_")[2])
        edit(chat_id, msg_id, "🤖 **اختر الموديل:**", kb_models(page))
    elif data.startswith("set_m_"):
        idx = int(data.split("_")[2])
        if idx < len(MODELS_CACHE):
            set_user_model(chat_id, MODELS_CACHE[idx])
            edit(chat_id, msg_id, f"✅ **تم تفعيل الموديل:**\n`{MODELS_CACHE[idx]}`", kb_main())
    elif data == "menu_personas":
        edit(chat_id, msg_id, "🧠 **اختر شخصية البوت:**", kb_personas())
    elif data.startswith("set_p_"):
        p_id = data.split("_")[2]
        personas = {
            "1": "أنت مبرمج خبير. أجب بالأكواد البرمجية فقط واشرحها باختصار.",
            "2": "أنت مترجم محترف. ترجم النصوص بدقة شديدة دون إضافات.",
            "3": "أنت كاتب محتوى إبداعي. استخدم أسلوباً جذاباً ومنسقاً.",
            "4": "أنت خبير أعمال واستثمار. أجب بلهجة احترافية مع أرقام ونصائح."
        }
        set_user_persona(chat_id, personas[p_id])
        edit(chat_id, msg_id, "✅ **تم تغيير الشخصية بنجاح.**", kb_main())
    elif data == "menu_stats":
        model, persona = get_user(chat_id)
        hist = len(get_history(chat_id))
        txt = f"📊 **إحصائياتك:**\n\n🤖 الموديل: `{model}`\n🧠 الشخصية: {persona[:30]}...\n💬 عدد الرسائل: {hist}"
        edit(chat_id, msg_id, txt, kb_main())
    elif data == "menu_settings":
        edit(chat_id, msg_id, "⚙️ **الإعدادات:**\nاستخدم الأزرار السابقة للتحكم، أو أرسل `/export` لتحميل المحادثة.", kb_main())
    elif data == "stop":
        if chat_id in STOP_EVENTS: STOP_EVENTS[chat_id].set()
    elif data == "regen":
        # إعادة توليد آخر سؤال
        history = get_history(chat_id)
        if history:
            last_user_msg = next((h["content"] for h in reversed(history) if h["role"] == "user"), None)
            if last_user_msg:
                init = send(chat_id, "🔄 **جاري إعادة التوليد...**", kb_stop_regen())
                if init.get("ok"):
                    threading.Thread(target=generate_ai, args=(chat_id, init["result"]["message_id"], last_user_msg)).start()
    elif data == "clear":
        clear_history(chat_id)
        edit(chat_id, msg_id, "🗑️ **تم مسح الذاكرة.**", kb_main())

# ============================================================
# ⚡ التشغيل الرئيسي
# ============================================================
def main():
    me = api_call("getMe")
    if not me.get("ok"): sys.exit("❌ توكن غير صالح.")
    print(f"🏆 TITAN AI يعمل الآن: @{me['result']['username']}")
    
    fetch_models()
    offset = None
    
    while True:
        try:
            params = {"timeout": 30}
            if offset: params["offset"] = offset
            upd = api_call("getUpdates", **params)
            
            if not upd.get("ok"): time.sleep(3); continue
            
            for u in upd["result"]:
                offset = u["update_id"] + 1
                if "message" in u: handle_message(u["message"])
                elif "callback_query" in u: handle_callback(u["callback_query"])
        except Exception as e:
            log(f"Loop Error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nتم الإيقاف.")