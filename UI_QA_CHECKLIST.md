# UI QA CHECKLIST — Premium Redesign

Har band: ✓ (tekshirildi) · holat: production-qa tayyor

## Umumiy
- [x] 15 route yagona shell + design system
- [x] Light/dark theme to'liq
- [x] 360→1920 viewport overflow = 0
- [x] Console errors = 0
- [x] Skeleton loading (dashboard, lists)
- [x] Empty state (jadval/timeline)
- [x] Error state + Qayta urinish
- [x] ConfirmDialog (danger amallar)
- [x] Toast feedback
- [x] Keyboard: Escape modal/drawer, Enter yuborish, ↑↓ slash-navigatsiya
- [x] aria-label icon-only tugmalarda
- [x] prefers-reduced-motion
- [x] Tabular numerals

## Funksional regression (barchasi saqlangan)
- [x] Login/logout/session redirect/CSRF mutation
- [x] Dashboard: KPI linklar, quick upload, attention panel
- [x] Citizens: qidiruv, 2 filtr, pagination, **yangi fuqaro**, **tahrirlash**, **arxivlash**
- [x] Families: 3 tab, qidiruv, pagination, **oila yaratish**, **tafsilot drawer**
- [x] Cases: qidiruv, holat filtri, **drawer forma + qidiruvli fuqaro**, holat ConfirmDialog
- [x] Tasks: 2 filtr, **yangi vazifa**, complete ConfirmDialog + dalil
- [x] Worklogs: tur filtr, **yangi yozuv**
- [x] Chat: suhbatlar ro'yxati, o'chirish, slash 11 buyruq, mikrofon, manbalar, draft approve/reject
- [x] Agents: status, provayder health, model zanjiri, budget
- [x] Documents: upload→tahlil→varaq→mapping→preview→xatolar→commit/rollback, download/**delete**
- [x] Reports: generate, list, preview drawer, approve dialog, eksport Word/PDF
- [x] Legislation: status, qidiruv, savol-javob, manbalar, Lex.uz sync
- [x] Programs: 2 filtr, taqqoslash, fuqaro matching, rasmiy havolalar
- [x] Admin: settings (AI provayder+**model**+budjet, lokal, scheduler), audit **filtrlar**, usage **trend**, jobs **error expand + run**, backup

## Backend dalil
- [x] `git diff master -- apps/api` = faqat tasdiqlangan Bosqich 4A
- [x] `lib/api.ts` / `lib/auth.ts` = 0 diff
- [x] Endpoint path/payload/response o'zgarmagan
