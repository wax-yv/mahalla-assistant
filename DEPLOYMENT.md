# Vercel deploy — HOLAT: ✅ DEPLOY QILINGAN

**LIVE:** https://mahalla-assistant.vercel.app (login `wax` / `waxs`)
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
   | `ADMIN_USERNAME` | `wax` |
   | `ADMIN_PASSWORD` | `waxs` |
   | `OPENROUTER_API_KEY` | OpenRouter kaliti (`sk-or-...`) |
   | `NVIDIA_NIM_API_KEY` | NVIDIA kaliti (`nvapi-...`) |
   | `FRONTEND_URL` | keyin 3-qadamda olingan web URL (masalan `https://mahalla-assistant.vercel.app`) |
   | `APP_BASE_URL` | API o'z URLsi (masalan `https://mahalla-assistant-api.vercel.app`) |

5. **Deploy** bosing. Birinchi build ~2 daqiqa.

### Birinchi sozlash (seed)

Deploy tugagach, API URLiga so'rov yuboring:

```bash
curl -X POST https://<api-url>/api/v1/setup \
  -H "X-Setup-Token: <SETUP_TOKEN qiymati>"
```

Bu 37 jadvalni yaratadi va 1 mahalla, 12 ko'cha, 202 uy, 285 oila, 1258 fuqaro, demo murojaat/vazifalar, 8 dastur, 6 qonunchilik snapshot, admin `wax/waxs` ni yuklaydi. Tekshirish:

```bash
curl https://<api-url>/api/v1/setup/status
# {"database":"ok","users":1,"citizens":1258,"setup_required":false}
```

## 3. Web loyihasi (3-qadam)

1. Vercel → **Add New → Project** → xuddi shu repo, yana bir marta.
2. **Root Directory:** `apps/web`
3. **Framework Preset:** Next.js (avtomatik)
4. **Environment Variables:**

   | Key | Qiymat |
   |---|---|
   | `API_ORIGIN` | 2-qadamdagi API URL (masalan `https://mahalla-assistant-api.vercel.app`) |

5. **Deploy**. Tayyor — `https://<web-url>` da ochiladi, login `wax` / `waxs`.

## 4. Yakuniy sozlash

- API loyihasida `FRONTEND_URL` va `APP_BASE_URL` ni 3-qadamdagi haqiqiy URL bilan yangilab, **Redeploy** qiling (CORS uchun).
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
