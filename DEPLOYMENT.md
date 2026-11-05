# Vercel deploy — HOLAT: ✅ DEPLOY QILINGAN

**LIVE:** https://mahalla-assistant.vercel.app (admin kirish — `ADMIN_USERNAME` / `ADMIN_PASSWORD` env orqali)
**API:** https://mahalla-assistant-api.vercel.app · Baza: Neon Postgres (Vercel Marketplace, `mahalla-db`)
**Repo:** https://github.com/wax-yv/mahalla-assistant

---

## Joriy arxitektura (deploy qilingan holat)

| Qism | Usul |
|---|---|
| API (`mahalla-assistant-api`) | GitHub `master` push → **avtomatik** deploy (Root Directory: `apps/api`) |
| Web (`mahalla-assistant`) | `vercel deploy` CLI (`apps/web` ichidan) — Git-avto-deploy o'chirilgan |
| Baza | Neon Postgres, `DATABASE_URL` env (integration tomonidan boshqariladi) |
| Seed | `POST /api/v1/setup` + `X-Setup-Token` (faqat `citizens==0` bo'lsa yuklaydi) |

---

# Quyidagi yo'riqnoma — boshqacha hisobda qayta deploy qilish uchun

Bitta GitHub repo → **ikki Vercel loyihasi**. Jarayon ~10 daqiqa.

## 0. Talablar

- GitHub repo (private ham bo'ladi)
- Vercel hisobi (Hobby — bepul yetadi)
- Real API kalitlar: `OPENROUTER_API_KEY`, `NVIDIA_NIM_API_KEY`

## 1. PostgreSQL bazasini ulash (1-qadam)

1. Vercel → **Storage** → **Create Database** → **Neon Postgres** (yoki Marketplace'dagi boshqa Postgres).
2. Nomini `mahalla-db` deb qo'ying, region: Frankfurt (fra1) yoki eng yaqin.
3. Yaratilgach, **`.env.local` tab**ida `DATABASE_URL` (pooled) ko'rinadi — uni nusxalang.

## 2. API loyihasi (2-qadam)

1. Vercel → **Add New → Project** → shu repo'ni import qiling.
2. **Root Directory:** `apps/api`
3. **Framework Preset:** Other (Python)
4. **Environment Variables** (Production + Preview):

   | Key | Qiymat |
   |---|---|
   | `DATABASE_URL` | 1-qadamdan olingan pooled URL |
   | `APP_ENV` | `production` |
   | `AUTH_SECRET` | uzun tasodifiy satr (masalan `openssl rand -hex 32`) |
   | `SETUP_TOKEN` | uzun tasodifiy satr (birinchi sozlash uchun) |
   | `CRON_SECRET` | uzun tasodifiy satr |
   | `ADMIN_USERNAME` | o'zingiz belgilagan admin logini |
   | `ADMIN_PASSWORD` | o'zingiz belgilagan kuchli parol (bo'sh/default bo'lmasligi kerak) |
   | `OPENROUTER_API_KEY` | OpenRouter kaliti (`sk-or-...`) |
   | `NVIDIA_NIM_API_KEY` | NVIDIA kaliti (`nvapi-...`) |
   | `FRONTEND_URL` | keyin 3-qadamda olingan web URL (masalan `https://mahalla-assistant.vercel.app`) |
   | `APP_BASE_URL` | API o'z URLsi (masalan `https://mahalla-assistant-api.vercel.app`) |

   **Ulanish to'plami (O-12).** Neon bepul tarifida ulanishlar soni
   chegaralangan; har Vercel instansiyasi o'z to'plamini yaratadi. Shu sababli
   ulanish soni o'zi ham chegaralangan:

   | Key | Default | Tavsiya |
   |---|---|---|
   | `DB_POOL_SIZE` | `2` | Neon **pooled** URL bilan 2–3 yetarli |
   | `DB_MAX_OVERFLOW` | `3` | Ko'p instansiyada `0` qiling |
   | `DB_POOL_NULL` | `false` | `true` bo'lsa NullPool (har so'rov yangi ulanish) |

   > `DATABASE_URL` **pooled** bo'lishi shart (`-pooler` bilan tugaydi).
   > To'g'ridan-to'g'ri URL ishlatilsa, `DB_POOL_NULL=true` qo'ying.

5. **Deploy** bosing. Birinchi build ~2 daqiqa.

### Birinchi sozlash (seed)

Deploy tugagach, API URLiga so'rov yuboring:

```bash
curl -X POST https://<api-url>/api/v1/setup \
  -H "X-Setup-Token: <SETUP_TOKEN qiymati>"
```

Bu 37 jadvalni yaratadi va 1 mahalla, 12 ko'cha, 202 uy, 285 oila, 1258 fuqaro, demo murojaat/vazifalar, 8 dastur, 6 qonunchilik snapshot, admin hisobini (`ADMIN_USERNAME`/`ADMIN_PASSWORD`) yuklaydi. Tekshirish:

```bash
curl https://<api-url>/api/v1/setup/status
# {"setup_required":false}
```

> `/setup/status` ochiq endpoint — u faqat `setup_required` holatini qaytaradi
> (baza haqolati, foydalanuvchi/fuqaro sonlari va xato matnlari sizib chiqmaydi).

## 3. Web loyihasi (3-qadam)

1. Vercel → **Add New → Project** → xuddi shu repo, yana bir marta.
2. **Root Directory:** `apps/web`
3. **Framework Preset:** Next.js (avtomatik)
4. **Environment Variables:**

   | Key | Qiymat |
   |---|---|
   | `API_ORIGIN` | 2-qadamdagi API URL (masalan `https://mahalla-assistant-api.vercel.app`) |

5. **Deploy**. Tayyor — `https://<web-url>` da ochiladi. Admin kirish ma'lumotlari API loyihasidagi `ADMIN_USERNAME`/`ADMIN_PASSWORD` env o'zgaruvchilarida (o'zingiz belgilagan).

## 4. Yakuniy sozlash

- API loyihasida `FRONTEND_URL` va `APP_BASE_URL` ni 3-qadamdagi haqiqiy URL bilan yangilab, **Redeploy** qiling (CORS uchun).
- **Sxema migratsiyasi (majburiy):** repoda Alembic yo'q va `create_all()` mavjud jadvalga yangi ustun qo'shmaydi. Shu sababli bazadagi o'zgarishlarni `scripts/migrate.sql` orqali qo'lda bajarish kerak:
  ```bash
  psql "$DATABASE_URL" -f scripts/migrate.sql
  ```
  Neon/Supabase SQL editor'ida `scripts/migrate.sql` faylini ochib butunlay bajarish ham mumkin. Skript `IF NOT EXISTS` bilan himoyalangan — bir necha marta ishga tushirsa ham xato bermaydi. hozirgi migrate.sql tarkibi:
  - **K-8** — `conversations.user_id` ustuni + indeks (suhbat egalik nazorati / IDOR himoyasi);
  - **J-6** — `citizens.data_source` uzunligi `VARCHAR(255)` ga kengaytirilgan;
  - **J-8** — `backup_runs.data` (BYTEA) — zaxira nusxa baytlari bazada saqlanadi;
  - **N-10** — `memory_items (key, conversation_id)` bo'yicha unikal indeks;
  - **O-16** — mavjud administratorlarga `reports.approve` ruxsati beriladi (hisobot tasdiqlash uchun `admin` roli yetarli emas — ruxsat aniq bo'lishi shart).

  > **O-16 eslatmasi:** migratsiyani bajarmasangiz, administrator hisobotni tasdiqlay olmaydi (`403`). Skript `idempotent` — ruxsat mavjud bo'lsa, qayta qo'shilmaydi.

  > Eslatma: `create_all()` faqat jadvallarni yaratadi, mavjud jadvallarga ustun **qo'shmaydi**. Shu sababli migratsiyani skip qilish K-8 ni ishlashdan to'xtatadi (suhbat egaligi `user_id` siz saqlanmaydi).
- **Cron:** `apps/api/vercel.json` da Vercel Cron sozlamasi bor — `GET /api/v1/cron/run-due` har kuni 04:00 UTC (09:00 Toshkent) chaqiriladi. Endpoint `Authorization: Bearer <CRON_SECRET>` sarlavhasini talab qiladi; `CRON_SECRET` env o'zgaruvchisi bo'lmasa yoki `change-me` bo'lsa endpoint **503** qaytaradi (o'chirilgan holat). Qo'lda sinash:
  ```bash
  curl -H "Authorization: Bearer $CRON_SECRET" https://<api-url>/api/v1/cron/run-due
  ```

## Muhim eslatmalar

- **Kredit-subsidiya agenti** avval bank/dastur nomini so'raydi — bu xatto, chunki shartlar bankdan bankga farq qiladi.
- **Lex.uz** bo'limi jonli ishlaydi: hujjatlar `lex.uz` dan yuklanadi, manba bilan ko'rsatiladi.
- **Budjet:** kunlik AI token limiti `AI_DAILY_TOKEN_BUDGET` (default 300 000). Sozlamalar → AI sarflari bo'limida kuzatiladi.
- **Fayl hajmi:** yuklanadigan hujjat max 4 MB (`MAX_UPLOAD_MB`).
- Baza jadvallari serverless **cold start**da faqat birinchi marta yaratiladi (marker jadval tekshiriladi), keyingi so'rovlar tez ishlaydi.
