# Mahalla Assistant — Demo

Xorazm viloyati, Urganch shahri, **Navbahor mahallasi** uchun rasmiy ish yuritish va AI assistent tizimi. Mahalla raisi yordamchisi va ijtimoiy xodimlar uchun: fuqarolar bazasi, murojaatlar, vazifalar nazorati, hisobotlar, Lex.uz qonunchiligi, kredit-subsidiya dasturlari va o'zbek tilida gaplashadigan AI agentlar.

> **Demo kirish:** bitta administrator. Login va parol `ADMIN_USERNAME` / `ADMIN_PASSWORD` muhit o'zgaruvchilaridan olinadi (standart qiymatlar `apps/api/app/core/config.py` ichida; `.env.local` bilan o'zgartirishingiz mumkin).

---

## Arxitektura

```
mahalla-assistant/
├── apps/
│   ├── web/                 # Next.js 15 (App Router, TypeScript) — interfeys
│   │   └── api/v1/* → API'ga proxy (same-origin cookie uchun)
│   └── api/                 # FastAPI + SQLAlchemy + PostgreSQL
│       ├── app/
│       │   ├── core/        # config, db, security, errors, pagination
│       │   ├── models.py    # 37 jadval
│       │   ├── schemas.py   # Pydantic
│       │   ├── routers/     # auth, dashboard, citizens, hierarchy, cases,
│       │   │                # documents, reports, legislation, programs,
│       │   │                # agents, admin, setup, health
│       │   ├── services/    # biznes-mantiq + agentlar + Lex.uz scraper
│       │   └── seed.py      # demo ma'lumotlar yuklovchi
│       ├── tests/           # pytest
│       └── api/index.py     # Vercel Python runtime kirish nuqtasi
├── apps/api/data/demo_fuqarolar_bazasi.xlsx   # manba dataset
└── .env.example
```

**Asosiy qarorlar**

- **Ikki Vercel loyihasi** bitta repodan: `apps/web` (Next.js) va `apps/api` (FastAPI). Frontend `/api/v1/*` so'rovlarini o'ziga proxy qiladi → cookie lar same-origin bo'lib qoladi.
- **Ma'lumotlar bazasi:** Vercel Marketplace (Neon) PostgreSQL. `DATABASE_URL` env orqali.
- **Fayllar:** Vercel Blob (agar `BLOB_READ_WRITE_TOKEN` bo'lsa), aks holda PostgreSQL `bytea` zaxira varianti.
- **Autentifikatsiya:** yagona admin, httpOnly session cookie + CSRF token, argon2 parol hash. Login limiti: 15 daqiqada 8 urinish.
- **AI:** OpenRouter va NVIDIA NIM (real API kalitlari), faqat bepul modellar, eng kuchli → zaif tartibda fallback. Token budjeti kunlik nazorat ostida.

## AI agentlar

| Agent | Vazifasi |
|---|---|
| **Orkestrator** | So'rovni tahlil qiladi, tegishli agentga yo'naltiradi |
| **Reja va nazorat** | Bugungi/kechikkan vazifalar, murojaatlar, tavsiyalar; vazifa loyihasi yaratadi |
| **Hisobot** | SQL ko'rsatkichlari asosida kunlik/haftalik/oylik hisobot loyihasi |
| **Qonunchilik** | Lex.uz dan jonli yuklash + manbali (sitata bilan) javob |
| **Kredit-subsidiya** | Avval bank/dastur so'raydi, keyin **faqat** tanlangan bank bo'yicha javob beradi va tanlovni eslab qoladi |
| **Hujjat** | Excel/CSV/Word import-eksport tartibi va holati |

Agentlar **deterministik asboblar-first**: raqamlar va faktlar bazadan/Lex.uz dan olinadi, LLM faqat tilni yaratish uchun. Biznes yozuvlari (vazifa yaratish, hisobot yaratish, hujjat importi, qonunchilik sinxroni) `draft_actions` sifatida taklif qilinadi va **tasdiqlangandan keyin** bajariladi. Yagona istisno — suhbat davomida eslab qolinadigan **tanlov** (masalan, qaysi bank bo'yicha kredit shartlari kerakligi): bu yozuv foydalanuvchiga ochiq aytiladi (`«Tanlovingizni eslab qoldim: ...»`) va javobda `preference_saved` maydoni bilan qaytariladi.

## Mahalliy ishga tushirish

```bash
# 1. Python muhit
python -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt

# 2. PostgreSQL + .env.local (.env.example dan ko'chirib DATABASE_URL ni to'ldiring)
cp .env.example .env.local

# 3. Baza va demo ma'lumotlar
PYTHONPATH=apps/api python -m app.seed

# 4. API (8000-port)
PYTHONPATH=apps/api uvicorn app.main:app --port 8000

# 5. Frontend (3000-port)
cd apps/web && pnpm install && pnpm dev
```

Brauzerda `http://localhost:3000` → admin login (yuqoridagi `ADMIN_USERNAME`/`ADMIN_PASSWORD`).

## Testlar

```bash
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q   # 14 smoke test
cd apps/web && npx next build                                       # frontend build
```

## Hujjatlar

- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Vercel ga 10 daqiqada deploy qilish yo'riqnomasi
- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** — bosh reja bo'yicha to'liq tayyorlik hisoboti
- API schemasi: `http://localhost:8000/api/docs` (Swagger)
