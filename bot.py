#!/usr/bin/env python3
"""Telegram o'yin boti: mashina simulyatori + mini o'yinlar.

Tashqi kutubxonalar kerak emas — faqat Python 3.8+ standart kutubxonasi.
Ishga tushirish: python bot.py
"""

import html
import json
import os
import random
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SCORES_FILE = DATA_DIR / "scores.json"
PLAYERS_FILE = DATA_DIR / "players.json"
API_ROOT = "https://api.telegram.org/bot"

START_MONEY = 15000
RACE_ENTRY = 1000
WORK_COOLDOWN = 45  # soniya
MAX_ENGINE = 10

# Mashina bozori: id -> nom, quvvat (HP), narx
CARS = {
    "matiz": {"name": "Daewoo Matiz", "power": 60, "price": 8000},
    "nexia": {"name": "Daewoo Nexia", "power": 85, "price": 25000},
    "cobalt": {"name": "Chevrolet Cobalt", "power": 105, "price": 65000},
    "gentra": {"name": "Chevrolet Gentra", "power": 115, "price": 95000},
    "malibu": {"name": "Chevrolet Malibu 2", "power": 160, "price": 240000},
    "tahoe": {"name": "Chevrolet Tahoe", "power": 360, "price": 700000},
    "bmw": {"name": "BMW M5", "power": 600, "price": 1600000},
    "ferrari": {"name": "Ferrari 488", "power": 670, "price": 4500000},
}

# ---------------------------------------------------------------------------
# Viktorina savollari: (savol, [variantlar], to'g'ri javob indeksi)
# ---------------------------------------------------------------------------
QUIZ = [
    ("O'zbekistonning poytaxti qaysi shahar?", ["Samarqand", "Toshkent", "Buxoro", "Namangan"], 1),
    ("Quyosh sistemasidagi eng katta sayyora?", ["Yer", "Mars", "Yupiter", "Saturn"], 2),
    ("1 kilobayt necha bayt?", ["100", "1000", "1024", "2048"], 2),
    ("Telegram qaysi yilda paydo bo'lgan?", ["2010", "2013", "2015", "2017"], 1),
    ("Suvning kimyoviy formulasi?", ["CO2", "H2O", "O2", "NaCl"], 1),
    ("Eng katta okean qaysi?", ["Atlantika", "Hind", "Tinch okeani", "Shimoliy Muz"], 2),
    ("Bir yilda necha kun bor (kabisa yili emas)?", ["364", "365", "366", "360"], 1),
    ("Python tilini kim yaratgan?", ["Guido van Rossum", "James Gosling", "Dennis Ritchie", "Linus Torvalds"], 0),
]

# Telegram menyusidagi ("/" tugmasi) buyruqlar ro'yxati
COMMANDS = [
    {"command": "start", "description": "🏎 O'yinni boshlash / asosiy menyu"},
    {"command": "garaj", "description": "🚗 Garaj: ta'mirlash, tuning, sotish"},
    {"command": "bozor", "description": "🛒 Mashina sotib olish"},
    {"command": "poyga", "description": "🏁 Poygada qatnashish (1 000 so'm)"},
    {"command": "ish", "description": "💼 Pul ishlash (45 soniyada bir)"},
    {"command": "top", "description": "🏆 Eng boy haydovchilar reytingi"},
    {"command": "menu", "description": "🏠 Asosiy menyu"},
    {"command": "stop", "description": "❌ Joriy o'yinni bekor qilish"},
]

MAIN_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🚗 Garaj", "callback_data": "car:garage"},
            {"text": "🛒 Bozor", "callback_data": "car:market"},
        ],
        [
            {"text": "🏁 Poyga", "callback_data": "car:race"},
            {"text": "💼 Ish", "callback_data": "car:work"},
        ],
        [
            {"text": "🏆 Reyting", "callback_data": "car:top"},
            {"text": "🎮 Mini o'yinlar", "callback_data": "games"},
        ],
    ]
}

GAMES_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "🎲 Zar tashlash", "callback_data": "game:dice"},
            {"text": "🔢 Sonni top", "callback_data": "game:guess"},
        ],
        [{"text": "🧠 Viktorina", "callback_data": "game:quiz"}],
        [{"text": "⬅️ Orqaga", "callback_data": "menu"}],
    ]
}

BACK_KEYBOARD = {"inline_keyboard": [[{"text": "⬅️ Orqaga", "callback_data": "menu"}]]}


class TelegramError(RuntimeError):
    """Telegram API qaytargan xato."""


# ---------------------------------------------------------------------------
# Telegram API
# ---------------------------------------------------------------------------
def api_call(token, method, **params):
    url = f"{API_ROOT}{token}/{method}"
    body = json.dumps(params).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise TelegramError(f"HTTP {exc.code}: {raw[:200]}") from exc
    except urllib.error.URLError as exc:
        raise TelegramError(f"tarmoq xatosi: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TelegramError("so'rov vaqti tugadi") from exc

    if not payload.get("ok"):
        raise TelegramError(payload.get("description") or "noma'lum xato")
    return payload["result"]


def get_updates(token, offset, timeout=30):
    return api_call(token, "getUpdates", offset=offset, timeout=timeout, limit=100)


def send_message(token, chat_id, text, keyboard=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True}
    if keyboard is not None:
        params["reply_markup"] = keyboard
    return api_call(token, "sendMessage", **params)


def edit_message(token, chat_id, message_id, text, keyboard=None):
    params = {"chat_id": chat_id, "message_id": message_id, "text": text,
              "parse_mode": "HTML"}
    if keyboard is not None:
        params["reply_markup"] = keyboard
    try:
        return api_call(token, "editMessageText", **params)
    except TelegramError as exc:
        if "not modified" in str(exc).lower():
            return None
        raise


def answer_callback(token, callback_id, text=None):
    params = {"callback_query_id": callback_id}
    if text:
        params["text"] = text
    try:
        api_call(token, "answerCallbackQuery", **params)
    except TelegramError:
        pass  # callback eskirgan bo'lsa, botni to'xtatmaymiz


def get_me(token):
    return api_call(token, "getMe")


def register_commands(token):
    """Buyruqlarni Telegram menyusiga yozadi."""
    api_call(token, "setMyCommands", commands=COMMANDS)


def delete_webhook(token):
    """Webhook faol bo'lsa getUpdates 409 Conflict qaytaradi (bot javob bermaydi).

    Bu bot faqat long polling'da ishlaydi, shuning uchun webhookni o'chiramiz.
    Shu bilan birga bir marta qayta urinamiz — eski webhook bo'lsa ham ishlaydi.
    """
    api_call(token, "deleteWebhook", drop_pending_updates=False)


def send_typing(token, chat_id):
    """Chatda 'yozmoqda...' belgisini ko'rsatadi."""
    try:
        api_call(token, "sendChatAction", chat_id=chat_id, action="typing")
    except TelegramError:
        pass


# ---------------------------------------------------------------------------
# AI suhbat (Z.ai, OpenAI-mos chat completions API — kutubxonalarsiz)
# ---------------------------------------------------------------------------
AI_DEFAULT_BASE = "https://api.z.ai/api/paas/v4"
AI_DEFAULT_MODEL = "glm-4-flash"
AI_TIMEOUT = 45
AI_HISTORY_LIMIT = 8  # chat uchun eslab qolinadigan oxirgi xabarlar soni
AI_SYSTEM_PROMPT = (
    "Siz Telegramdagi o'yin botining aqlli yordamchisiz. "
    "Foydalanuvchi qaysi tilda yozsa, o'sha tilda javob bering (o'zbekcha yozsa — o'zbekcha). "
    "Javoblar qisqa, aniq va do'stona bo'lsin. "
    "Bot haqida: bu 'Car Simulator 2 UZB' o'yin boti — garaj, bozor, poyga, ish, "
    "mini o'yinlar (zar, sonni top, viktorina) va reyting. "
    "Buyruqlar: /start, /garaj, /bozor, /poyga, /ish, /top, /menu, /stop."
)

ai_history = {}


class AIError(RuntimeError):
    """AI xizmatidan javob olinmadi."""


def ai_settings():
    """(.env yoki muhitdan) API kalit, manzil va modelni o'qiydi."""
    key = (os.environ.get("ZAI_API_KEY") or "").strip() or read_env("ZAI_API_KEY")
    if not key:
        key = (os.environ.get("AI_API_KEY") or "").strip() or read_env("AI_API_KEY")
    base = (os.environ.get("ZAI_API_BASE") or "").strip() or read_env("ZAI_API_BASE") \
        or AI_DEFAULT_BASE
    model = (os.environ.get("ZAI_MODEL") or "").strip() or read_env("ZAI_MODEL") \
        or AI_DEFAULT_MODEL
    return key, base.rstrip("/"), model


def ai_enabled():
    return bool(ai_settings()[0])


def ask_ai(chat_id, text):
    """AI dan javob oladi va chat tarixini eslab qoladi."""
    key, base, model = ai_settings()
    if not key:
        raise AIError("ZAI_API_KEY sozlanmagan")

    history = ai_history.setdefault(chat_id, [])
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=AI_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise AIError(f"HTTP {exc.code}: {raw[:200]}") from exc
    except urllib.error.URLError as exc:
        raise AIError(f"tarmoq xatosi: {exc.reason}") from exc
    except (TimeoutError, ValueError) as exc:
        raise AIError(str(exc)) from exc

    try:
        answer = (payload["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("javob formati kutilganidan farq qiladi") from exc
    if not answer:
        raise AIError("bo'sh javob")

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    del history[:-AI_HISTORY_LIMIT]
    return answer


def chunk_text(text, limit=3800):
    """Telegram 4096 belgi limitidan oshmasligi uchun bo'laklarga bo'ladi."""
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


def send_ai_reply(token, chat_id, answer):
    parts = [html.escape(p) for p in chunk_text(answer)]
    for part in parts[:-1]:
        send_message(token, chat_id, part)
    send_message(token, chat_id, parts[-1], MAIN_KEYBOARD)



# ---------------------------------------------------------------------------
# Saqlash
# ---------------------------------------------------------------------------
def _load_json(path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default
    return data if isinstance(data, dict) else default


def _save_json(path, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# Mini o'yinlar uchun ballar
def add_points(user, amount):
    scores = _load_json(SCORES_FILE, {})
    key = str(user["id"])
    entry = scores.get(key) or {"name": "O'yinchi", "points": 0}
    entry["name"] = user.get("first_name") or user.get("username") or entry["name"]
    entry["points"] = int(entry.get("points", 0)) + amount
    scores[key] = entry
    _save_json(SCORES_FILE, scores)
    return entry["points"]


def games_leaderboard_text():
    scores = _load_json(SCORES_FILE, {})
    if not scores:
        return "🏆 <b>Mini o'yinlar reytingi</b>\n\nHozircha bo'sh. O'yin o'ynang!"
    top = sorted(scores.values(), key=lambda i: int(i.get("points", 0)), reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Mini o'yinlar reytingi</b>", ""]
    for i, e in enumerate(top):
        place = medals[i] if i < len(medals) else f"{i + 1}."
        lines.append(f"{place} {html.escape(str(e.get('name', '?')))} — {e.get('points', 0)} ball")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mashina simulyatori: o'yinchi
# ---------------------------------------------------------------------------
def new_player():
    return {
        "money": START_MONEY,
        "car": "matiz",
        "eng": 0,
        "condition": 100,
        "xp": 0,
        "wins": 0,
        "losses": 0,
        "km": 0,
        "job_ready": 0,
    }


def with_player(user):
    players = _load_json(PLAYERS_FILE, {})
    key = str(user["id"])
    player = players.get(key)
    if not isinstance(player, dict) or "car" not in player:
        player = new_player()
    player.setdefault("eng", 0)
    player["name"] = user.get("first_name") or user.get("username") or player.get("name", "Driver")
    players[key] = player
    return players, player


def save_players(players):
    _save_json(PLAYERS_FILE, players)


def fmt(number):
    return f"{int(number):,}".replace(",", " ")


def money(value):
    return f"{fmt(value)} so'm"


def car_name(player):
    return CARS.get(player.get("car", "matiz"), CARS["matiz"])["name"]


def level(player):
    return int(player.get("xp", 0)) // 100 + 1


def power(player):
    base = CARS.get(player.get("car", "matiz"), CARS["matiz"])["power"]
    return int(base * (1 + 0.08 * int(player.get("eng", 0))))


def effective_power(player):
    condition = max(0, min(100, int(player.get("condition", 100))))
    return max(10, int(power(player) * (0.55 + 0.45 * condition / 100)))


def condition_bar(condition):
    filled = max(0, min(10, round(condition / 10)))
    return "█" * filled + "░" * (10 - filled) + f" {condition}%"


def car_menu_text(user, player):
    return (
        f"🏎 <b>Mashina simulyatori</b>\n"
        f"👤 {html.escape(player.get('name', 'Driver'))} · {level(player)}-daraja\n\n"
        f"💰 Pul: <b>{money(player['money'])}</b>\n"
        f"🚗 Mashina: <b>{car_name(player)}</b>\n"
        f"⚡ Quvvat: {power(player)} HP (tuning +{player.get('eng', 0)})\n"
        f"🔧 Holat: {condition_bar(int(player.get('condition', 100)))}\n"
        f"🏁 Poygalar: {player.get('wins', 0)} g'alaba / {player.get('losses', 0)} mag'lubiyat\n"
        f"🛣 Bosilgan yo'l: {fmt(player.get('km', 0))} km\n\n"
        f"Quyidan bo'limni tanlang 👇"
    )


def garage_text(player):
    repair_cost = (100 - int(player.get("condition", 100))) * 60
    tune_cost = 5000 * (int(player.get("eng", 0)) + 1)
    lines = [
        f"🚗 <b>{car_name(player)}</b>",
        "",
        f"⚡ Quvvat: {power(player)} HP",
        f"🔧 Holat: {condition_bar(int(player.get('condition', 100)))}",
        f"💰 Pul: {money(player['money'])}",
        "",
    ]
    if repair_cost > 0:
        lines.append(f"🔧 Ta'mirlash narxi: {money(repair_cost)}")
    else:
        lines.append("🔧 Mashina to'liq sog'lom ✅")
    if int(player.get("eng", 0)) < MAX_ENGINE:
        lines.append(f"⚡ Tuning (+8% quvvat) narxi: {money(tune_cost)}")
    else:
        lines.append("⚡ Tuning maksimal darajada 🏁")
    if player.get("car") == "matiz":
        lines.append("💰 Boshlang'ich Matiz sotilmaydi")
    else:
        lines.append(f"💰 Sotish narxi: {money(sale_value(player))}")
    return "\n".join(lines)


def sale_value(player):
    base = CARS.get(player.get("car", "matiz"), CARS["matiz"])["price"]
    condition = int(player.get("condition", 100))
    return int(base * 0.6 * (0.5 + 0.5 * condition / 100))


def garage_keyboard(player):
    repair_cost = (100 - int(player.get("condition", 100))) * 60
    tune_cost = 5000 * (int(player.get("eng", 0)) + 1)
    rows = []
    if repair_cost > 0:
        rows.append([{"text": f"🔧 Ta'mirlash — {money(repair_cost)}", "callback_data": "car:repair"}])
    if int(player.get("eng", 0)) < MAX_ENGINE:
        rows.append([{"text": f"⚡ Tuning — {money(tune_cost)}", "callback_data": "car:tune"}])
    if player.get("car") != "matiz":
        rows.append([{"text": f"💰 Sotish — {money(sale_value(player))}", "callback_data": "car:sell"}])
    rows.append([{"text": "⬅️ Orqaga", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


def market_text():
    lines = ["🛒 <b>Mashina bozori</b>", ""]
    for car in CARS.values():
        lines.append(f"• {car['name']} — {car['power']} HP · {money(car['price'])}")
    lines.append("")
    lines.append("Mashina sotib olsangiz, eskisi 60% narxda hisobga olinadi.")
    return "\n".join(lines)


def market_keyboard(player):
    rows = []
    for car_id, car in CARS.items():
        mark = " ✅" if car_id == player.get("car") else ""
        rows.append([{
            "text": f"{car['name']} — {money(car['price'])}{mark}",
            "callback_data": f"car:buy:{car_id}",
        }])
    rows.append([{"text": "⬅️ Orqaga", "callback_data": "menu"}])
    return {"inline_keyboard": rows}


def players_leaderboard_text():
    players = _load_json(PLAYERS_FILE, {})
    if not players:
        return "🏆 <b>Reyting</b>\n\nHozircha bo'sh — birinchi bo'lib poygaga chiqing!"
    top = sorted(players.values(), key=lambda p: int(p.get("money", 0)), reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Eng boy haydovchilar</b>", ""]
    for i, p in enumerate(top):
        place = medals[i] if i < len(medals) else f"{i + 1}."
        lines.append(
            f"{place} {html.escape(str(p.get('name', 'Driver')))} — {money(p.get('money', 0))}, "
            f"{CARS.get(p.get('car', 'matiz'), CARS['matiz'])['name']}"
        )
    return "\n".join(lines)


# --- Amallar ---------------------------------------------------------------
def do_race(player):
    condition = int(player.get("condition", 100))
    if condition < 15:
        return (f"⚠️ <b>Mashina holati juda past</b> ({condition}%).\n\n"
                "Garajga borib ta'mirlang — aks holda poygada yutqazasiz.")
    if int(player["money"]) < RACE_ENTRY:
        return (f"💸 Poyga uchun kirish narxi {money(RACE_ENTRY)}.\n"
                f"Sizda {money(player['money'])} bor. 💼 Ish bo'limida pul ishlang.")

    player["money"] = int(player["money"]) - RACE_ENTRY
    my_power = effective_power(player)

    opp_id = random.choice(list(CARS))
    opp_car = CARS[opp_id]
    opp_power = max(20, int(opp_car["power"] * random.uniform(0.85, 1.15)))
    chance = my_power / (my_power + opp_power)

    won = random.random() < chance
    km = random.randint(4, 18)
    player["km"] = int(player.get("km", 0)) + km

    if won:
        prize = RACE_ENTRY * 2 + random.randint(500, 1800)
        player["money"] = int(player["money"]) + prize
        player["wins"] = int(player.get("wins", 0)) + 1
        player["xp"] = int(player.get("xp", 0)) + 25
        player["condition"] = max(0, condition - 4)
        result = (
            f"🏁 <b>Poyga natijasi</b>\n\n"
            f"🚗 Siz: {car_name(player)} — {my_power} HP\n"
            f"🚙 Raqib: {opp_car['name']} — {opp_power} HP\n"
            f"🛣 Masofa: {km} km\n\n"
            f"✅ <b>G'alaba!</b>\n"
            f"💰 Yutuq: +{money(prize)}\n"
            f"⭐ Tajriba: +25 XP\n"
            f"🔧 Holat: -4%"
        )
    else:
        player["losses"] = int(player.get("losses", 0)) + 1
        player["xp"] = int(player.get("xp", 0)) + 5
        player["condition"] = max(0, condition - 9)
        result = (
            f"🏁 <b>Poyga natijasi</b>\n\n"
            f"🚗 Siz: {car_name(player)} — {my_power} HP\n"
            f"🚙 Raqib: {opp_car['name']} — {opp_power} HP\n"
            f"🛣 Masofa: {km} km\n\n"
            f"❌ <b>Mag'lubiyat.</b>\n"
            f"💸 Kirish narxi: -{money(RACE_ENTRY)}\n"
            f"⭐ Tajriba: +5 XP\n"
            f"🔧 Holat: -9%"
        )

    keyboard = {
        "inline_keyboard": [
            [{"text": "🏁 Yana poyga", "callback_data": "car:race"}],
            [{"text": "🚗 Garaj", "callback_data": "car:garage"},
             {"text": "⬅️ Orqaga", "callback_data": "menu"}],
        ]
    }
    return result, keyboard


def do_work(player):
    now = int(time.time())
    wait = int(player.get("job_ready", 0)) - now
    if wait > 0:
        return (f"⏳ <b>Dam oling.</b>\n\nKeyingi ishga {wait} soniya qoldi.\n"
                f"💰 Pul: {money(player['money'])}"), WORK_KEYBOARD
    earn = random.randint(800, 2200)
    player["money"] = int(player["money"]) + earn
    player["job_ready"] = now + WORK_COOLDOWN
    player["condition"] = max(0, int(player.get("condition", 100)) - 2)
    text = (
        f"💼 <b>Ish bajarildi!</b>\n\n"
        f"🚕 Taksi buyurtmalarini yetkazdingiz.\n"
        f"💰 Daromad: +{money(earn)}\n"
        f"🔧 Mashina holati: -2%\n\n"
        f"Jami pul: <b>{money(player['money'])}</b>"
    )
    return text, WORK_KEYBOARD


WORK_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "💼 Yana ishlash", "callback_data": "car:work"}],
        [{"text": "🚗 Garaj", "callback_data": "car:garage"},
         {"text": "⬅️ Orqaga", "callback_data": "menu"}],
    ]
}


def do_repair(player):
    condition = int(player.get("condition", 100))
    if condition >= 100:
        return "🔧 Mashina allaqachon to'liq sog'lom ✅"
    cost = (100 - condition) * 60
    if int(player["money"]) < cost:
        return (f"💸 Ta'mirlash uchun {money(cost)} kerak.\n"
                f"Sizda {money(player['money'])} bor. 💼 Ish bo'limida pul ishlang.")
    player["money"] = int(player["money"]) - cost
    player["condition"] = 100
    return (f"🔧 <b>Ta'mirlash bajarildi!</b>\n\n"
            f"💰 Sarf: -{money(cost)}\n"
            f"🔧 Holat: 100% ✅\n"
            f"💰 Qolgan pul: {money(player['money'])}")


def do_tune(player):
    eng = int(player.get("eng", 0))
    if eng >= MAX_ENGINE:
        return "⚡ Tuning allaqachon maksimal darajada 🏁"
    cost = 5000 * (eng + 1)
    if int(player["money"]) < cost:
        return (f"💸 Tuning uchun {money(cost)} kerak.\n"
                f"Sizda {money(player['money'])} bor.")
    player["money"] = int(player["money"]) - cost
    player["eng"] = eng + 1
    return (f"⚡ <b>Tuning o'rnatildi!</b>\n\n"
            f"Yangi quvvat: <b>{power(player)} HP</b>\n"
            f"Tuning darajasi: {player['eng']}/{MAX_ENGINE}\n"
            f"💰 Sarf: -{money(cost)}\n"
            f"💰 Qolgan pul: {money(player['money'])}")


def do_sell(player):
    if player.get("car") == "matiz":
        return ("💰 Boshlang'ich Matiz sotilmaydi.\n\n"
                "Avval bozordan boshqa mashina oling, keyin uni sotishingiz mumkin.")
    value = sale_value(player)
    player["money"] = int(player["money"]) + value
    player["car"] = "matiz"
    player["eng"] = 0
    player["condition"] = 100
    return (f"💰 <b>Mashina sotildi!</b>\n\n"
            f"Hisobingizga: +{money(value)}\n"
            f"Hozir sizda: Daewoo Matiz (boshlang'ich mashina)\n"
            f"💰 Pul: <b>{money(player['money'])}</b>\n\n"
            f"🛒 Bozordan yangi mashina oling.")


def do_buy(player, car_id):
    if car_id not in CARS:
        return "Bunday mashina topilmadi."
    if car_id == player.get("car"):
        return "🚗 Bu mashina allaqachon sizda."
    car = CARS[car_id]
    trade_in = sale_value(player)
    price = car["price"]
    cost = max(0, price - trade_in)
    if int(player["money"]) < cost:
        missing = cost - int(player["money"])
        return (f"💸 <b>{car['name']}</b> uchun {money(cost)} kerak.\n"
                f"Yetmayotgan summa: {money(missing)}\n\n"
                f"💰 Sizda: {money(player['money'])}")
    player["money"] = int(player["money"]) - cost
    player["car"] = car_id
    player["eng"] = 0
    player["condition"] = 100
    return (f"🎉 <b>Yangi mashina!</b>\n\n"
            f"🚗 {car['name']}\n"
            f"⚡ Quvvat: {car['power']} HP\n"
            f"💰 Sarf: -{money(cost)}"
            + (f" (eski mashina hisobga olindi: {money(trade_in)})" if trade_in else "")
            + f"\n💰 Qolgan pul: {money(player['money'])}")


# ---------------------------------------------------------------------------
# Mashina simulyatori callbacklari
# ---------------------------------------------------------------------------
def handle_car(token, callback, data):
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    user = callback.get("from") or {}

    players, player = with_player(user)
    action = data[4:]  # "car:" dan keyin

    if action == "garage":
        answer_callback(token, callback["id"])
        edit_message(token, chat_id, message_id, garage_text(player), garage_keyboard(player))
        save_players(players)
        return

    if action == "market":
        answer_callback(token, callback["id"])
        edit_message(token, chat_id, message_id, market_text(), market_keyboard(player))
        save_players(players)
        return

    if action == "race":
        answer_callback(token, callback["id"])
        result = do_race(player)
        if isinstance(result, tuple):
            text, keyboard = result
        else:
            text, keyboard = result, garage_keyboard(player)
        save_players(players)
        edit_message(token, chat_id, message_id, text, keyboard)
        return

    if action == "work":
        text, keyboard = do_work(player)
        answer_callback(token, callback["id"], f"💰 {money(player['money'])}")
        save_players(players)
        edit_message(token, chat_id, message_id, text, keyboard)
        return

    if action == "repair":
        condition_before = int(player.get("condition", 100))
        text = do_repair(player)
        answer_callback(token, callback["id"],
                        "✅ Ta'mirlandi" if player.get("condition") == 100 and condition_before < 100 else None)
        save_players(players)
        edit_message(token, chat_id, message_id, text, garage_keyboard(player))
        return

    if action == "tune":
        eng_before = int(player.get("eng", 0))
        text = do_tune(player)
        answer_callback(token, callback["id"],
                        "⚡ Tuning o'rnatildi" if player.get("eng", 0) > eng_before else None)
        save_players(players)
        edit_message(token, chat_id, message_id, text, garage_keyboard(player))
        return

    if action == "sell":
        text = do_sell(player)
        answer_callback(token, callback["id"], "💰 Sotildi")
        save_players(players)
        edit_message(token, chat_id, message_id, text, MARKET_BACK_KEYBOARD)
        return

    if action == "top":
        answer_callback(token, callback["id"])
        save_players(players)
        edit_message(token, chat_id, message_id, players_leaderboard_text(), BACK_KEYBOARD)
        return

    if action.startswith("buy:"):
        car_id = action[4:]
        text = do_buy(player, car_id)
        answer_callback(token, callback["id"])
        save_players(players)
        edit_message(token, chat_id, message_id, text, MARKET_BACK_KEYBOARD)
        return

    answer_callback(token, callback["id"])


MARKET_BACK_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "🛒 Bozor", "callback_data": "car:market"}],
        [{"text": "🚗 Garaj", "callback_data": "car:garage"},
         {"text": "⬅️ Orqaga", "callback_data": "menu"}],
    ]
}


# ---------------------------------------------------------------------------
# Mini o'yinlar
# ---------------------------------------------------------------------------
DICE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
states = {}


def new_guess(chat_id):
    states[chat_id] = {"mode": "guess", "secret": random.randint(1, 100), "tries": 0}


def clear_state(chat_id):
    states.pop(chat_id, None)


def start_guess(token, chat_id):
    new_guess(chat_id)
    send_message(
        token,
        chat_id,
        "🔢 <b>Sonni top</b>\n\n"
        "Men 1 dan 100 gacha son o'yladim. Taxminingizni yozib yuboring.\n"
        "Kamroq urinishda topsangiz — ko'proq ball olasiz!\n\n"
        "Bekor qilish: /stop",
    )


def handle_guess_input(token, chat_id, user, text):
    state = states.get(chat_id)
    if not state:
        return
    try:
        guess = int(text)
    except ValueError:
        send_message(token, chat_id, "Iltimos, butun son yuboring (1–100).")
        return
    if not 1 <= guess <= 100:
        send_message(token, chat_id, "Son 1 va 100 orasida bo'lishi kerak.")
        return

    state["tries"] += 1
    secret, tries = state["secret"], state["tries"]
    if guess < secret:
        send_message(token, chat_id, f"⬆️ Kattaroq son. ({tries}-urinish)")
    elif guess > secret:
        send_message(token, chat_id, f"⬇️ Kichikroq son. ({tries}-urinish)")
    else:
        points = max(5, 25 - (tries - 1) * 4)
        total = add_points(user, points)
        clear_state(chat_id)
        send_message(
            token, chat_id,
            f"🎉 <b>Topdingiz!</b>\n\nSon: <b>{secret}</b>\nUrinishlar: {tries}\n"
            f"Ball: +{points} (jami: {total})",
            BACK_KEYBOARD,
        )


def send_quiz(token, chat_id, message_id=None):
    index = random.randrange(len(QUIZ))
    question, options, _ = QUIZ[index]
    rows = [[{"text": option, "callback_data": f"quiz:{index}:{i}"}]
            for i, option in enumerate(options)]
    rows.append([{"text": "⬅️ Orqaga", "callback_data": "games"}])
    text = f"🧠 <b>Savol:</b> {html.escape(question)}"
    keyboard = {"inline_keyboard": rows}
    if message_id:
        edit_message(token, chat_id, message_id, text, keyboard)
    else:
        send_message(token, chat_id, text, keyboard)


# ---------------------------------------------------------------------------
# Xabarlar
# ---------------------------------------------------------------------------
def welcome_text(user):
    return (
        f"Salom, <b>{html.escape(user.get('first_name') or user.get('username') or 'Haydovchi')}</b>! 👋\n\n"
        "🏎 <b>Car Simulator 2 UZB</b>\n"
        "Garajdan boshlaysiz: Daewoo Matiz + 15 000 so'm.\n\n"
        "🚗 <b>Garaj</b> — mashina holati, ta'mirlash, tuning, sotish\n"
        "🛒 <b>Bozor</b> — yangi mashina sotib olish\n"
        "🏁 <b>Poyga</b> — pul va tajriba (kirish 1 000 so'm)\n"
        "💼 <b>Ish</b> — har 45 soniyada daromad\n"
        "🏆 <b>Reyting</b> — eng boy haydovchilar\n"
        "🎮 <b>Mini o'yinlar</b> — zar, sonni top, viktorina\n\n"
        "Buyruqlar: /start, /garaj, /poyga, /ish, /bozor, /top, /stop"
    )


def on_message(token, message):
    chat_id = message["chat"]["id"]
    user = message.get("from") or {}
    text = (message.get("text") or "").strip()
    if not text:
        # Rasm/stiker/ovoz yuborilsa ham jim qolmasin
        if any(k in message for k in ("sticker", "photo", "voice", "video", "document")):
            send_message(token, chat_id,
                         "Men faqat matnli xabarlarga javob beraman 🙂\n/menu ni bosing 👇",
                         MAIN_KEYBOARD)
        return

    command = text.split()[0].split("@")[0].lower()
    players, player = with_player(user)

    if command in ("/start", "/menu", "/help"):
        clear_state(chat_id)
        save_players(players)
        send_message(token, chat_id, welcome_text(user), MAIN_KEYBOARD)
        return

    if command in ("/garaj", "/garage", "/car"):
        save_players(players)
        send_message(token, chat_id, garage_text(player), garage_keyboard(player))
        return

    if command in ("/bozor", "/market"):
        save_players(players)
        send_message(token, chat_id, market_text(), market_keyboard(player))
        return

    if command in ("/poyga", "/race"):
        result = do_race(player)
        save_players(players)
        if isinstance(result, tuple):
            send_message(token, chat_id, result[0], result[1])
        else:
            send_message(token, chat_id, result, garage_keyboard(player))
        return

    if command in ("/ish", "/work"):
        text_out, keyboard = do_work(player)
        save_players(players)
        send_message(token, chat_id, text_out, keyboard)
        return

    if command in ("/reyting", "/top", "/score"):
        save_players(players)
        send_message(token, chat_id, players_leaderboard_text(), BACK_KEYBOARD)
        return

    if command in ("/stop", "/cancel"):
        clear_state(chat_id)
        send_message(token, chat_id, "O'yin to'xtatildi. /menu orqali qayta boshlang.")
        return

    state = states.get(chat_id)
    if state and state.get("mode") == "guess":
        handle_guess_input(token, chat_id, user, text)
        return

    if command.startswith("/"):
        send_message(token, chat_id, "Bunday buyruq yo'q. /menu ni bosing.", MAIN_KEYBOARD)
        return

    # Erkin matnli savol — AI javob beradi (sozlangan bo'lsa)
    if ai_enabled():
        send_typing(token, chat_id)
        try:
            answer = ask_ai(chat_id, text)
        except AIError as exc:
            print(f"[ai] {exc}", file=sys.stderr, flush=True)
            send_message(
                token, chat_id,
                "🤖 AI hozir javob bera olmadi.\n"
                "Birozdan keyin qayta yozing yoki /menu ni bosing 👇",
                MAIN_KEYBOARD,
            )
            return
        send_ai_reply(token, chat_id, answer)
        return

    send_message(token, chat_id, "Boshlash uchun /menu ni bosing 👇", MAIN_KEYBOARD)


def on_callback(token, callback):
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    user = callback.get("from") or {}
    data = callback.get("data") or ""

    if data.startswith("car:"):
        handle_car(token, callback, data)
        return

    if data == "menu":
        clear_state(chat_id)
        answer_callback(token, callback["id"])
        edit_message(token, chat_id, message_id, welcome_text(user), MAIN_KEYBOARD)
        return

    if data == "games":
        answer_callback(token, callback["id"])
        edit_message(
            token, chat_id, message_id,
            "🎮 <b>Mini o'yinlar</b>\n\nO'yinni tanlang:",
            GAMES_KEYBOARD,
        )
        return

    if data == "game:dice":
        value = random.randint(1, 6)
        total = add_points(user, value)
        answer_callback(token, callback["id"], f"Zar: {value}")
        keyboard = {
            "inline_keyboard": [
                [{"text": "🎲 Yana tashlash", "callback_data": "game:dice"}],
                [{"text": "⬅️ Orqaga", "callback_data": "games"}],
            ]
        }
        edit_message(
            token, chat_id, message_id,
            f"🎲 Zar tashlandi: {DICE_FACES[value - 1]} <b>{value}</b>\n\n"
            f"Ball: +{value}\nJami (mini o'yinlar): <b>{total}</b>",
            keyboard,
        )
        return

    if data == "game:guess":
        answer_callback(token, callback["id"])
        start_guess(token, chat_id)
        return

    if data == "game:quiz":
        answer_callback(token, callback["id"])
        send_quiz(token, chat_id, message_id)
        return

    if data == "quiz:more":
        answer_callback(token, callback["id"])
        send_quiz(token, chat_id, message_id)
        return

    if data == "score":
        answer_callback(token, callback["id"])
        edit_message(token, chat_id, message_id, games_leaderboard_text(), BACK_KEYBOARD)
        return

    if data.startswith("quiz:"):
        parts = data.split(":")
        try:
            question_index, choice = int(parts[1]), int(parts[2])
            question, options, correct = QUIZ[question_index]
        except (IndexError, ValueError):
            answer_callback(token, callback["id"])
            return
        if not 0 <= choice < len(options):
            answer_callback(token, callback["id"])
            return
        next_keyboard = {
            "inline_keyboard": [
                [{"text": "➡️ Yana savol", "callback_data": "quiz:more"}],
                [{"text": "⬅️ Orqaga", "callback_data": "games"}],
            ]
        }
        if choice == correct:
            total = add_points(user, 2)
            answer_callback(token, callback["id"], "To'g'ri! +2 ball")
            text = (
                f"✅ <b>To'g'ri javob!</b>\n\n{html.escape(question)}\n"
                f"Javob: <b>{html.escape(options[correct])}</b>\n\nBall: +2 (jami: {total})"
            )
        else:
            answer_callback(token, callback["id"], "Noto'g'ri 😔")
            text = (
                f"❌ <b>Noto'g'ri.</b>\n\n{html.escape(question)}\n"
                f"To'g'ri javob: <b>{html.escape(options[correct])}</b>"
            )
        edit_message(token, chat_id, message_id, text, next_keyboard)
        return

    answer_callback(token, callback["id"])


def handle_update(token, update):
    try:
        if "message" in update:
            on_message(token, update["message"])
        elif "callback_query" in update:
            on_callback(token, update["callback_query"])
    except TelegramError as exc:
        print(f"[xato] {update.get('update_id')}: {exc}", file=sys.stderr, flush=True)
    except Exception as exc:  # kutilmagan xato botni to'xtatmasligi kerak
        print(f"[xato] {update.get('update_id')}: {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)


# ---------------------------------------------------------------------------
# Ishga tushirish
# ---------------------------------------------------------------------------
def read_env(name):
    """Muhit o'zgaruvchisi yoki .env fayldan qiymat o'qiydi."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return ""
    # utf-8-sig: Notepad bilan saqlangan fayldagi BOM belgisi kalitni buzmasin
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if key == name:
            return value.strip().strip('"').strip("'")
    return ""


def load_token():
    return (os.environ.get("BOT_TOKEN") or "").strip() or read_env("BOT_TOKEN")


def load_admin_id():
    raw = (os.environ.get("ADMIN_ID") or "").strip() or read_env("ADMIN_ID")
    return int(raw) if raw.isdigit() else None


def main():
    # Windows konsolida emoji sababli UnicodeEncodeError bilan yiqilib qolmasin
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    token = load_token()
    if not token:
        print("BOT_TOKEN topilmadi. .env fayliga BOT_TOKEN=... yozing.", file=sys.stderr)
        return 1

    try:
        me = get_me(token)
    except TelegramError as exc:
        message = str(exc)
        if "unauthorized" in message.lower() or "401" in message:
            print("❌ Token yaroqsiz — Telegram uni tanimaydi (401 Unauthorized).", file=sys.stderr)
            print("   Sababi: token bekor qilingan (revoke), xato ko'chirilgan yoki eskirgan.", file=sys.stderr)
            print("   Yechim:", file=sys.stderr)
            print("     1) Telegramda @BotFather ga o'ting", file=sys.stderr)
            print("     2) /mybots -> botingizni tanlang -> API Token", file=sys.stderr)
            print("     3) Yangi tokenni nusxalab, .env faylidagi BOT_TOKEN= qatoriga qo'ying", file=sys.stderr)
        else:
            print(f"Token tekshiruvi muvaffaqiyatsiz: {message}", file=sys.stderr)
        return 1

    print(f"Bot ishga tushdi: @{me.get('username')} ({me.get('first_name')})", flush=True)
    print("To'xtatish uchun Ctrl+C bosing.", flush=True)

    if ai_enabled():
        print(f"AI suhbat yoqilgan (model: {ai_settings()[2]}).", flush=True)
    else:
        print("AI suhbat o'chirilgan — .env ga ZAI_API_KEY=... qo'shing.", flush=True)

    try:
        delete_webhook(token)
        print("Webhook tozalandi — long polling tayyor.", flush=True)
    except TelegramError as exc:
        print(f"[ogohlantirish] webhookni o'chirib bo'lmadi: {exc}",
              file=sys.stderr, flush=True)

    try:
        register_commands(token)
        print("Buyruqlar menyusi yangilandi (Telegramda '/' ni bosing).", flush=True)
    except TelegramError as exc:
        print(f"[ogohlantirish] buyruqlar yangilanmadi: {exc}", file=sys.stderr, flush=True)

    admin_id = load_admin_id()
    if admin_id:
        try:
            send_message(
                token, admin_id,
                "✅ <b>Bot ishga tushdi va xabarlarga javob bera oladi.</b>\n\n"
                f"@{me.get('username')}\n"
                "Telegramda /start bosing — menyu chiqadi.",
            )
            print(f"Admin ({admin_id}) ga 'ishga tushdim' xabari yuborildi.", flush=True)
        except TelegramError as exc:
            print(f"[ogohlantirish] admin xabari yuborilmadi: {exc}", file=sys.stderr, flush=True)

    # Eski (javobsiz qolgan) xabarlarni o'tkazib yuboramiz — spam bo'lmasin
    offset = 0
    try:
        pending = get_updates(token, -1, timeout=0)
        if pending:
            offset = pending[-1]["update_id"] + 1
            print(f"Eski {len(pending)} ta xabar o'tkazib yuborildi.", flush=True)
    except TelegramError:
        pass
    while True:
        try:
            updates = get_updates(token, offset, timeout=30)
        except TelegramError as exc:
            message = str(exc)
            if "409" in message or "conflict" in message.lower():
                print("[xato] 409 Conflict: xabarlarni olish bloklangan.",
                      file=sys.stderr, flush=True)
                print("   Sababi: botning boshqa nusxasi ishlab turgan (ikkinchi oyna) "
                      "yoki webhook faol.", file=sys.stderr, flush=True)
                print("   Yechim: bot.py ning barcha boshqa oynalarini yoping "
                      "(Faqat bittasi ishlashi kerak).", file=sys.stderr, flush=True)
            else:
                print(f"[tarmoq] {message} — 3 soniyadan keyin qayta urinamiz",
                      file=sys.stderr, flush=True)
            time.sleep(3)
            continue

        for update in updates:
            offset = max(offset, update["update_id"] + 1)
            handle_update(token, update)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")
