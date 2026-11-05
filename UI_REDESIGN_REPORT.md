# UI REDESIGN REPORT — Premium Visual Redesign (Modern Civic Intelligence)

**Branch:** `ui/premium-redesign` → `master` · **Sana:** 2026-11-05
**Hujjatlar:** MASTER UI/UX SPEC (funksional) + PREMIUM DESIGN SPEC (vizual)

## 1. Qamrov va yondashuv

- 15 route to'liq qayta dizayn qilindi; **funksionallik 100% saqlandi**.
- Backend: faqat foydalanuvchi alohida buyurtma qilgan **Bosqich 4A (AI Routing v2 + Data-Q&A)** bo'yichagina o'zgardi (pastda dalil).
- `lib/api.ts` va `lib/auth.ts`: **0 o'zgarish**.

## 2. Design System (Bosqich 1)

- Premium palitra (light/dark): brand 950–50 scale, surface 1/2/3, semantik 4 rang + soft foni — §2 bo'yicha.
- Tipografika: **faqat Inter** (Fraunces olib tashlandi), H1 28/24, H2 21/19, H3 16, body 14–15, tabular numerals.
- Spacing 4px tizimi, radius 8/12/16, shadow-sm/md/lg, z-index to'plami.
- Komponentlar: Button (primary/secondary/outline/ghost/danger + sm/md/lg + loading), Input/Select/Textarea (hover/focus/disabled/error), Badge (6 ton), Card, Modal, Drawer, ConfirmDialog, Toast, Tooltip-ishla, Skeleton/Empty/Error state, FileDropzone, SearchSelect, Field, DataTable asoslari, Timeline, Progress, Stepper.
- Ikonal: **lucide-react** (unicode/emoji to'liq olib tashlandi — §13).

## 3. Application Shell (Bosqich 2)

- Sidebar 248px ⇄ 72px collapse (tooltip'li), guruhlar, active indikator rang+belgi.
- Topbar 64px (desktop+mobile): breadcrumb, theme toggle, foydalanuvchi, chiqish.
- Mobile: bottom-nav 5 + **«Boshqa bo'limlar»** drawer (qolgan 10 route), 44×44 touch target, safe-area.

## 4. Sahifalar (Bosqich 3–5)

| Sahifa | Asosiy o'zgarishlar |
|---|---|
| Login | Premium markaziy karta, password toggle, Inter, demo-creds yo'q |
| Dashboard | KPI kartalar ikon+link, attention panel (kechikkan/bugun), chartlar, setup-hero dropzone, sifat paneli |
| Citizens | URL-sync filtrlar, toolbar+chips, `tel:` link, needs chips +N, **Yangi fuqaro/Tahrirlash drawer**, arxivlash ConfirmDialog, mobile tayyor |
| Citizen detail | Breadcrumb, edit drawer, arxiv confirm, quality panel, timeline |
| Families | Premium tablar (sarlavha+tavsif), **oila yaratish formasi**, tafsilot drawer (a'zolar bilan) |
| Cases | **Drawer forma + qidiruvli fuqaro tanlash** (`/citizens/options`), detail holat ConfirmDialog |
| Tasks | URL-sync, **Yangi vazifa drawer**, Complete ConfirmDialog (dalil majburiy) |
| Worklogs | Premium timeline, o'zbek label'lar, **yangi yozuv drawer** |
| Chat | **Markdown render**, DraftActionCard (o'qiladigan payload + texnik accordion), citation bloklari, slash keyboard-navigatsiya, avto-grow composer, busy-time hint, suhbat o'chirish |
| Agents | Overview statlar, provayder health (jonli), budget progress-bar, model zanjiri + **faol model** belgisi |
| Documents | **Stepper**, **drag-and-drop dropzone**, **preview table**, xato/ogohlantirish chip-filtrlar, **commit ConfirmDialog** (can_commit sababi), download/delete amallari |
| Reports | Generate blok, **preview Drawer**, approve ConfirmDialog, eksportlar |
| Legislation | Status strip, qidiruv natijalari, savol-javob manbali bloklar |
| Programs | Katalog/filtrlar/taqqoslash/matching (premium ko'rinish) |
| Admin | Guruhlangan settings (Mahalla/Lokal/AI/Scheduler), **model tanlash** + zanjir preview, audit **filtrlar + badge**, **14-kun trend**, job error expand, backup ConfirmDialog |

## 5. Bosqich 4A — AI Routing v2 + Data-Q&A (backend, alohida buyurtma)

- `data_stats` agent: statistik savollar («nechta», «soni») → **SQL aniq hisob** + guruh taqsimoti + filtrlangan havola. Xallusinatsiya yo'q (raqamlar faqat bazadan).
- Smalltalk prompt grounding: tashqi tizim nomlarini o'ylab topish taqiqlandi.
- **Model tanlash**: sozlamalarda tanlangan model zanjir boshiga qo'yiladi, xatolikda avtomatik davom etadi; validatsiya bilan.
- Testlar: 19/19 pytest ✓ (intent, facet counts, model order, admin validatsiya).

## 6. Backend o'zgarmaganligi dalili

`git diff master --stat -- apps/api` → faqat 4A fayllari (agents.py, ai_gateway.py, admin.py, routers/agents.py 1 qator, tests). Boshqa bosqichlarda 0. `lib/api.ts`, `lib/auth.ts` diff — bo'sh.

## 7. QA natijalari

- Viewport audit: **13 sahifa × 8 ekran (360→1920) = nol horizontal overflow** ✓
- Console errors: 0 ✓ · Dark/light: to'liq ✓ · Sidebar collapse ✓ · Mobile drawer ✓
- Funksional E2E: login, dashboard, citizens CRUD, families, cases+status, tasks complete/create, chat (slash, markdown, data-stats javobi «35 nafar»), agents, documents (upload→analysis→preview), reports, admin ✓
- `next build` ✓ · tsc ✓ · pytest 19/19 ✓
- Screenshotlar: `docs/redesign/before/` (30) va `docs/redesign/after/` (20+)

## 8. Ma'lum cheklovlar (backend imkoni)

- Bildirishnoma markazi, global qidiruv, Kanban drag-status, ish yozuvida fuqaro ismi — backend endpoint'i yo'q (soxta qilinmadi, §2.3).
- Chat markdown — react-markdown/remark-gfm qo'shildi (§13.3 talabi).

## 9. Dependency'lar

`lucide-react` (ikon tizimi — §13), `react-markdown` + `remark-gfm` (chat markdown — §13.3). Boshqa kutubxona qo'shilmadi.
