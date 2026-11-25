# 🎮 Telegram o'yin boti

Bitta faylli Telegram bot: **zar**, **sonni top**, **viktorina** va **reyting**.
Hech qanday tashqi kutubxona kerak emas — faqat Python 3.8+ va standart kutubxona.

## O'yinlar

| O'yin | Tavsif | Ball |
|-------|--------|------|
| 🎲 Zar | Zar tashlaysiz | +1…+6 |
| 🔢 Sonni top | 1–100 orasidagi sonni topasiz | +5…+25 (urinishga qarab) |
| 🧠 Viktorina | Savolga 4 variantdan javob | to'g'ri javobga +2 |
| 🏆 Reyting | Top-10 o'yinchi | — |

## Ishga tushirish

1. Python borligini tekshiring:

   ```bash
   python --version
   ```

2. Token `.env` faylida turibdi (`BOT_TOKEN=...`). Uni almashtirish uchun shu faylni tahrirlang
   yoki muhit o'zgaruvchisi bering:

   ```bash
   BOT_TOKEN=123456:ABC... python bot.py
   ```

3. Botni ishga tushiring:

   - Windowsda: `start.bat` faylini ikki marta bosing (oyna yopilib ketmaydi,
     xato bo'lsa matni ko'rinib turadi).
   - Terminalda:

   ```bash
   python bot.py
   ```

   Konsolda `Bot ishga tushdi: @username` chiqsa — hammasi joyida.
   To'xtatish: `Ctrl+C`.

4. Telegramda botga `/start` yozing.

## Muhim: bot javob berishi uchun

Telegram bot faqat `bot.py` (yoki `start.bat`) ishlab turganda javob beradi.
Dastur yopiq bo'lsa, `/start` bossangiz ham hech narsa bo'lmaydi — xabarlar
navbatda turadi va dastur ishga tushganda o'tkazib yuboriladi.

Ishga tushganda bot `ADMIN_ID` ga "✅ Bot ishga tushdi" xabarini yuboradi —
shu xabar kelsa, hammasi ishlayapti.

Python o'rnatilmagan bo'lsa: [python.org](https://python.org) dan yuklab oling,

O'rnatishda **"Add python.exe to PATH"** ni albatta belgilang.

## 🤖 AI suhbat

Bot buyruq bo'lmagan **har qanday matnli xabarga AI orqali javob beradi**
(foydalanuvchi qaysi tilda yozsa — o'sha tilda). Sozlash:

1. [z.ai](https://z.ai) da ro'yxatdan o'ting va API kalit oling.
2. `.env` fayliga qo'shing:

   ```env
   ZAI_API_KEY=kalitni-shu-yerga
   ZAI_API_BASE=https://api.z.ai/api/paas/v4
   ZAI_MODEL=glm-4-flash
   ```

3. Botni qayta ishga tushiring. Konsolda `AI suhbat yoqilgan (model: glm-4-flash)`
   chiqsa — tayyor.

Kalit bo'lmasa bot avvalgidek ishlaydi, faqat erkin matnga AI javobi o'rniga
qisqa ko'rsatma yuboradi. AI chaqiruvi ham `urllib` orqali — qo'shimcha
kutubxona kerak emas.

## Buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `/start` | O'yinni boshlash / asosiy menyu |
| `/garaj` | Garaj: ta'mirlash, tuning, sotish |
| `/bozor` | Mashina sotib olish |
| `/poyga` | Poygada qatnashish (1 000 so'm) |
| `/ish` | Pul ishlash (45 soniyada bir) |
| `/top` | Eng boy haydovchilar reytingi |
| `/menu` | Asosiy menyu |
| `/stop` | Joriy o'yinni bekor qilish |

Bu ro'yxat Telegramdagi `/` tugmasida avtomatik ko'rinadi: bot ishga tushganda
`setMyCommands` orqali yuboriladi.

**Muhim:** buyruqlarni chatga qo'lda yozish yoki nusxalash shart emas — ular
Telegram menyusiga bir marta yoziladi. Lekin ularga javob berish uchun `bot.py`
ishlab turishi kerak.

## Tuzilish

```
bot.py         # butun bot kodi
.env           # BOT_TOKEN (gitga tushmaydi)
.env.example   # namuna
data/scores.json  # ballar (avtomatik yaratiladi)
```

## Eslatma

- Bot long polling rejimida ishlaydi, webhook yoki server kerak emas; kompyuter
  yoqilgan vaqtda ishlaydi.
- `data/scores.json` faylini o'chirsangiz, reyting noldan boshlanadi.
