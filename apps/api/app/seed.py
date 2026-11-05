"""Demo ma'lumotlarini yuklash.

Manba: demo_fuqarolar_bazasi.xlsx (Xorazm viloyati, Urganch shahri,
Navbahor mahallasi). Skript idempotent: mavjud yozuvlarni yangilaydi.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    AppSetting,
    Case,
    Citizen,
    Conversation,
    ConversationMessage,
    Family,
    House,
    LegislationChunk,
    LegislationDocument,
    LegislationVersion,
    Mahalla,
    Program,
    ProgramSource,
    ScheduledJob,
    Street,
    Task,
    User,
    WorkLog,
)

DATA_FILE = Path("/home/shohjahon/Downloads/Telegram Desktop/demo_fuqarolar_bazasi.xlsx")
# Bundled with the API project so the Vercel serverless bundle includes it.
PREFERRED_FILE = Path(__file__).resolve().parents[1] / "data" / "demo_fuqarolar_bazasi.xlsx"
RNG = random.Random(20261103)
NOW = datetime.now(timezone.utc)


def _stable_int(value: str, modulo: int) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16) % modulo


def _verified(seed: str) -> datetime:
    return NOW - timedelta(days=_stable_int(seed, 21))


def load_source_rows():
    path = DATA_FILE if DATA_FILE.exists() else PREFERRED_FILE
    if not path.exists():
        raise RuntimeError(
            "Demo XLSX topilmadi. Uni data/demo_fuqarolar_bazasi.xlsx ga joylang."
        )
    workbook = load_workbook(path, read_only=True, data_only=True)
    houses = list(workbook["Ko'chalar_Uylar"].iter_rows(values_only=True))[1:]
    families = list(workbook["Oilalar"].iter_rows(values_only=True))[1:]
    citizens = list(workbook["Fuqarolar"].iter_rows(values_only=True))[1:]
    return houses, families, citizens


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def seed_hierarchy(db: Session) -> dict[str, Family]:
    houses_rows, families_rows, citizen_rows = load_source_rows()
    mahalla = db.execute(
        select(Mahalla).where(Mahalla.name == "Navbahor mahallasi")
    ).scalar_one_or_none()
    if mahalla is None:
        mahalla = Mahalla(
            name="Navbahor mahallasi",
            district="Urganch shahri",
            region="Xorazm viloyati",
        )
        db.add(mahalla)
        db.flush()
    streets: dict[str, Street] = {}
    houses: dict[str, House] = {}
    for row in houses_rows:
        if not row or not row[0]:
            continue
        street_name = _clean(row[2])
        house_no = _clean(row[3])
        if not street_name or not house_no:
            continue
        if street_name not in streets:
            street = db.execute(
                select(Street).where(
                    Street.mahalla_id == mahalla.id, Street.name == street_name
                )
            ).scalar_one_or_none()
            if street is None:
                street = Street(mahalla_id=mahalla.id, name=street_name)
                db.add(street)
                db.flush()
            streets[street_name] = street
        key = f"{street_name}|{house_no}"
        house = db.execute(
            select(House).where(
                House.street_id == streets[street_name].id, House.house_number == house_no
            )
        ).scalar_one_or_none()
        if house is None:
            house = House(
                street_id=streets[street_name].id,
                house_number=house_no,
                address_label=f"{street_name}, {house_no}-uy",
            )
            db.add(house)
            db.flush()
        houses[key] = house
    family_map: dict[str, Family] = {}
    for row in families_rows:
        if not row or not row[0]:
            continue
        family_id = _clean(row[0])
        street_name = _clean(row[3])
        house_no = _clean(row[4])
        house = houses.get(f"{street_name}|{house_no}")
        if house is None:
            continue
        family = db.get(Family, family_id)
        if family is None:
            family = Family(
                id=family_id,
                house_id=house.id,
                family_type=_clean(row[8]) or "To'liq oila",
                social_status=_clean(row[9]) or "Yo'q",
                notes=_clean(row[10]),
            )
            db.add(family)
            family_map[family_id] = family
        else:
            family_map[family_id] = family
    # Preload existing citizen ids in one query to keep the loop cheap.
    existing_ids = set(
        db.execute(select(Citizen.id)).scalars().all()
    )
    new_citizens: list[Citizen] = []
    seen_ids: set[str] = set()
    for row in citizen_rows:
        if not row or not row[0]:
            continue
        cid = _clean(row[0])
        full_name = _clean(row[1])
        if not full_name or cid in seen_ids:
            continue
        seen_ids.add(cid)
        family_id = _clean(row[8])
        family = family_map.get(family_id)
        needs = _clean(row[14])
        needs_list = [n.strip() for n in needs.split(",") if n.strip() and n.strip() != "Yo'q"]
        citizen = Citizen(
            id=cid,
            full_name=full_name,
            family_id=family.id if family else None,
            gender=_clean(row[2]) or "Erkak",
            birth_date=_date(row[3]),
            phone=_clean(row[4]),
            family_role=_clean(row[9]) or "Farzand",
            education=_clean(row[10]) or "O'rta",
            employment_status=_clean(row[11]) or "Ishlamaydi",
            profession=_clean(row[12]) or "Yo'q",
            social_status=_clean(row[13]) or "Yo'q",
            needs=needs_list,
            needs_text=needs if needs != "Yo'q" else "",
            notes=_clean(row[15]),
            data_source="demo_fuqarolar_bazasi.xlsx",
            last_verified_at=_verified(cid),
        )
        if cid in existing_ids:
            db.merge(citizen)
        else:
            new_citizens.append(citizen)
    if new_citizens:
        db.add_all(new_citizens)
    db.flush()
    # Assign family heads without extra per-row queries.
    if new_citizens:
        all_citizens = db.execute(select(Citizen).where(Citizen.family_id.is_not(None))).scalars().all()
        for citizen in all_citizens:
            family = family_map.get(citizen.family_id or "")
            if family and not family.family_head_citizen_id and citizen.family_role in {
                "Ota",
                "Ona",
                "Bobo",
                "Buvi",
            }:
                family.family_head_citizen_id = citizen.id
    db.commit()
    return family_map


CASE_BLUEPRINTS = [
    ("Bandlik", "Ish bilan ta'minlash bo'yicha murojaat", "open", "high", "Ishsiz fuqaro kasb-hunar yo'nalishida ish topishni so'radi. Bandlik markazi bilan bog'lanish rejalashtirildi."),
    ("Ijtimoiy yordam", "Moddiy yordam ajratish masalasi", "in_progress", "normal", "Kam ta'minlangan oila moddiy yordam uchun murojaat qildi. Hujjatlar to'plami tekshirilmoqda."),
    ("Kredit va subsidiya", "Tadbirkorlik krediti bo'yicha maslahat", "waiting", "high", "Fuqaro tikuvchilik ustaxonasini ochish uchun kredit olishni rejalashtirmoqda. Bank talablari aniqlashtirilmoqda."),
    ("Ta'lim", "Ta'lim kontrakti uchun yordam", "in_progress", "normal", "Talaba oilasining moliyaviy holati og'irlashgani sababli kontrakt to'lovi bo'yicha yordam so'raldi."),
    ("Tibbiy yordam", "Reabilitatsiya kursiga yo'llanma", "open", "urgent", "Nogironligi bor fuqaro uchun reabilitatsiya kursiga yo'llanma kerak. Tibbiyot muassasasi bilan aloqa qilindi."),
    ("Uy-joy", "Uy-joy sharoitini yaxshilash masalasi", "open", "normal", "Ko'p bolali oila uy-joy sharoitini yaxshilash bo'yicha murojaat qildi."),
    ("Hujjatlar", "Tug'ilganlik guvohnomasini tiklash", "resolved", "normal", "Fuqaro tug'ilganlik guvohnomasini yo'qotgan. FHDYo bo'limi orqali nusxa olindi."),
    ("Oila munosabatlari", "Oila ichidagi nizoni hal qilish", "in_progress", "high", "Oila a'zolari o'rtasida kelishmovchilik yuzaga kelgan. Mahalla profilaktika inspektori bilan suhbat o'tkazildi."),
    ("Bandlik", "Yoshlar uchun vaqtinchalik ish", "closed", "low", "Yozgi ta'til davrida yoshlar uchun vaqtinchalik ish joyi topildi. Natija ijobiy."),
    ("Ijtimoiy yordam", "Nafaqa tayinlash bo'yicha murojaat", "in_progress", "normal", "Ijtimoiy nafaqa tayinlash uchun ariza qabul qilindi, tuman bo'limiga yuborildi."),
    ("Kredit va subsidiya", "Subsidiya olish bo'yicha maslahat", "open", "normal", "Issiqxona qurish uchun subsidiya olish imkoniyatlari so'raldi."),
    ("Ta'lim", "Maktabga yaqinlashtirish masalasi", "closed", "low", "Maktabgacha ta'lim muassasasida joy masalasi hal qilindi."),
    ("Tibbiy yordam", "Dori-darmon bilan ta'minlash", "waiting", "normal", "Qandli diabet bilan og'rigan fuqaro uchun dori-darmon ajratish so'raldi."),
    ("Hujjatlar", "Yashash joyi ma'lumotnomasi", "closed", "low", "Fuqaroga yashash joyi bo'yicha ma'lumotnoma berildi."),
]

TASK_BLUEPRINTS = [
    ("Ishsiz fuqaro bilan suhbat o'tkazish", "Bandlik", "high", "Bugun bandlik markazi ro'yxatiga kiritilishi tekshiriladi."),
    ("Moddiy yordam hujjatlarini tekshirish", "Ijtimoiy yordam", "normal", "Daromad ma'lumotnomasi va oila tarkibi hujjatlari solishtiriladi."),
    ("Kredit bo'yicha bank talablarini aniqlashtirish", "Kredit va subsidiya", "high", "Fuqaro tanlagan bank filiali bilan bog'lanib, talablar aniqlanadi."),
    ("Kontrakt to'lovi bo'yicha ariza tayyorlash", "Ta'lim", "normal", "Ta'lim muassasasidan kontrakt miqdori olib kelinadi."),
    ("Reabilitatsiya yo'llanmasini rasmiylashtirish", "Tibbiy yordam", "urgent", "Tuman tibbiyot birlashmasi bilan yo'llanma kelishiladi."),
    ("Uy-joy komissiyasi xulosasini olish", "Uy-joy", "normal", "Komissiya yig'ilishi sanasi tasdiqlanadi."),
    ("Nafaqa arizasini tuman bo'limiga yuborish", "Ijtimoiy yordam", "normal", "Ariza ro'yxatga olinishi nazorat qilinadi."),
    ("Subsidiya dasturi shartlarini tushuntirish", "Kredit va subsidiya", "low", "Issiqxona qurish dasturi bo'yicha ma'lumot beriladi."),
    ("Dori-darmon murojaatini kuzatish", "Tibbiy yordam", "high", "Dorixona va poliklinika o'rtasida aloqa qilinadi."),
    ("Yoshlar bandligi ro'yxatini yangilash", "Bandlik", "normal", "30 yoshgacha bo'lgan ishsizlar ro'yxati tekshiriladi."),
]

WORKLOG_BLUEPRINTS = [
    ("uchrashuv", "Uy sharoitida uchrashuv", "Oila a'zolari bilan suhbat o'tkazildi, ehtiyojlar aniqlashtirildi."),
    ("telefon", "Telefon orqali aloqa", "Fuqaro bilan telefon orqali bog'lanildi va keyingi qadam kelishildi."),
    ("tavsiya", "Tavsiya berildi", "Fuqaroga tegishli tashkilotga murojaat qilish tartibi tushuntirildi."),
    ("hujjat", "Hujjat qabul qilindi", "Murojaat uchun zarur hujjatlar qabul qilindi va ro'yxatga olindi."),
    ("bajarilgan ish", "Amaliy yordam ko'rsatildi", "Murojaat bo'yicha amaliy yordam ko'rsatildi, natija qayd etildi."),
    ("natija", "Natija ma'lum qilindi", "Fuqaroga murojaat natijasi haqida ma'lumot berildi."),
]


def seed_operational(db: Session) -> None:
    citizens = db.execute(
        select(Citizen).where(Citizen.archived_at.is_(None)).order_by(Citizen.id)
    ).scalars().all()
    if not citizens:
        raise RuntimeError("Fuqarolar yuklanmagan.")
    unemployed = [c for c in citizens if c.employment_status == "Ishsiz"]
    social = [c for c in citizens if c.social_status != "Yo'q"]
    youth = [c for c in citizens if c.birth_date and c.birth_date.year >= 1996]
    needy = [c for c in citizens if c.needs]
    pool = unemployed + social + youth + needy
    if not pool:
        pool = citizens
    today = datetime.now(timezone.utc).date()
    cases: list[Case] = []
    if not db.execute(select(Case).limit(1)).scalar_one_or_none():
        for index, (category, title, status, priority, description) in enumerate(CASE_BLUEPRINTS):
            citizen = pool[index % len(pool)]
            opened = datetime.now(timezone.utc) - timedelta(days=(index * 3) % 45, hours=index)
            case = Case(
                citizen_id=citizen.id,
                family_id=citizen.family_id,
                category=category,
                title=title,
                description=description,
                opened_at=opened,
                status=status,
                priority=priority,
                responsible_user="Mahalla raisi yordamchisi",
                target_date=today + timedelta(days=(index % 9) - 2),
                outcome="Murojaat ijobiy hal qilindi." if status == "closed" else "",
                closed_at=opened + timedelta(days=4) if status == "closed" else None,
                created_by="seed",
            )
            db.add(case)
            db.flush()
            cases.append(case)
    else:
        cases = db.execute(select(Case).order_by(Case.opened_at.desc())).scalars().all()
    if not db.execute(select(Task).limit(1)).scalar_one_or_none():
        for index, (title, category, priority, description) in enumerate(TASK_BLUEPRINTS):
            citizen = pool[(index * 7) % len(pool)]
            case = cases[index % len(cases)] if cases else None
            if index < 3:
                due = today
                status = "new"
            elif index < 5:
                due = today + timedelta(days=1)
                status = "in_progress"
            elif index < 7:
                due = today + timedelta(days=3)
                status = "waiting"
            elif index == 7:
                due = today - timedelta(days=2)
                status = "new"
            elif index == 8:
                due = today - timedelta(days=4)
                status = "in_progress"
            else:
                due = today - timedelta(days=1)
                status = "new"
            task = Task(
                title=title,
                description=description,
                citizen_id=citizen.id,
                family_id=citizen.family_id,
                case_id=case.id if case else None,
                category=category,
                priority=priority,
                status=status,
                due_date=due,
                assignee="Mahalla ijtimoiy xodimi",
                created_by="seed",
            )
            db.add(task)
            db.flush()
            db.add(
                WorkLog(
                    citizen_id=citizen.id,
                    family_id=citizen.family_id,
                    case_id=case.id if case else None,
                    task_id=task.id,
                    type="vazifa",
                    title="Vazifa yaratildi",
                    description=f"{title} — mas'ul xodimga biriktirildi.",
                    occurred_at=datetime.now(timezone.utc) - timedelta(days=index % 5, hours=index),
                    author_id="seed",
                    source="seed",
                )
            )
        for index in range(8):
            citizen = pool[(index * 11) % len(pool)]
            task = db.execute(select(Task).order_by(Task.created_at).limit(8)).scalars().all()[index]
            completed_at = datetime.now(timezone.utc) - timedelta(days=index % 6, hours=index + 1)
            task.status = "completed"
            task.completed_at = completed_at
            task.evidence_note = "Murojaat bo'yicha amaliy yordam ko'rsatildi, natija fuqaroga ma'lum qilindi."
            db.add(
                WorkLog(
                    citizen_id=citizen.id,
                    family_id=citizen.family_id,
                    case_id=task.case_id,
                    task_id=task.id,
                    type="bajarilgan ish",
                    title="Vazifa bajarildi",
                    description=task.evidence_note,
                    occurred_at=completed_at,
                    author_id="seed",
                    source="seed",
                )
            )
    if not db.execute(select(WorkLog).where(WorkLog.type == "uchrashuv").limit(1)).scalar_one_or_none():
        for index in range(24):
            citizen = pool[(index * 13) % len(pool)]
            kind, title, description = WORKLOG_BLUEPRINTS[index % len(WORKLOG_BLUEPRINTS)]
            occurred = datetime.now(timezone.utc) - timedelta(days=index % 30, hours=index % 9)
            db.add(
                WorkLog(
                    citizen_id=citizen.id,
                    family_id=citizen.family_id,
                    type=kind,
                    title=title,
                    description=description,
                    occurred_at=occurred,
                    author_id="seed",
                    source="seed",
                    approval_status="confirmed",
                )
            )
    db.commit()


PROGRAMS = [
    {
        "name": "Oilaviy tadbirkorlikni qo'llab-quvvatlash krediti",
        "type": "credit",
        "organization": "Xalq banki",
        "target_group": "Oilaviy tadbirkorlik bilan shug'ullanmoqchi bo'lgan fuqarolar",
        "eligibility": {"min_age": 18, "max_age": 65, "requires_business": False, "categories": ["Kam ta'minlangan oila", "Ko'p bolali oila", "Yoshlar daftari", "Ayollar daftari"]},
        "amount": "50 mln so'mgacha",
        "interest_rate": "Yillik stavka bank tomonidan belgilanadi",
        "term_months": "36 oygacha",
        "grace_period": "6 oygacha",
        "required_documents": ["Pasport", "Tadbirkorlik loyihasi", "Daromad ma'lumotnomasi", "Garov hujjatlari"],
        "application_channel": "Bank filiali yoki mobil ilova",
        "official_url": "https://xb.uz",
    },
    {
        "name": "Yosh tadbirkorlar uchun imtiyozli kredit",
        "type": "credit",
        "organization": "Biznesni rivojlantirish banki",
        "target_group": "30 yoshgacha bo'lgan tadbirkorlar",
        "eligibility": {"min_age": 18, "max_age": 30, "requires_business": True, "categories": ["Yoshlar daftari"]},
        "amount": "500 mln so'mgacha",
        "interest_rate": "Imtiyozli stavka",
        "term_months": "60 oygacha",
        "grace_period": "12 oygacha",
        "required_documents": ["Pasport", "Biznes-reja", "Ro'yxatdan o'tish hujjati", "Garov"],
        "application_channel": "Bank filiali",
        "official_url": "https://brb.uz",
    },
    {
        "name": "Ayollar tadbirkorligini qo'llab-quvvatlash",
        "type": "credit",
        "organization": "Agrobank",
        "target_group": "Tadbirkorlik bilan shug'ullanuvchi ayollar",
        "eligibility": {"min_age": 18, "max_age": 65, "requires_business": True, "categories": ["Ayollar daftari", "Kam ta'minlangan oila"]},
        "amount": "300 mln so'mgacha",
        "interest_rate": "Bank tomonidan belgilanadi",
        "term_months": "36 oygacha",
        "grace_period": "6 oygacha",
        "required_documents": ["Pasport", "Biznes-reja", "Garov hujjatlari"],
        "application_channel": "Bank filiali",
        "official_url": "https://agrobank.uz",
    },
    {
        "name": "Ipoteza krediti",
        "type": "credit",
        "organization": "Ipoteka bank",
        "target_group": "Uy-joy sotib olishni rejalashtirgan fuqarolar",
        "eligibility": {"min_age": 18, "max_age": 65, "requires_business": False, "categories": []},
        "amount": "Uy-joy qiymatining 80 foizigacha",
        "interest_rate": "Yillik stavka bank tomonidan belgilanadi",
        "term_months": "240 oygacha",
        "grace_period": "Yo'q",
        "required_documents": ["Pasport", "Daromad ma'lumotnomasi", "Uy-joy hujjatlari"],
        "application_channel": "Bank filiali",
        "official_url": "https://ipotekabank.uz",
    },
    {
        "name": "Issiqxona qurish uchun subsidiya",
        "type": "subsidy",
        "organization": "Qishloq xo'jaligi vazirligi",
        "target_group": "Issiqxona faoliyatini boshlovchi dehqon xo'jaliklari",
        "eligibility": {"min_age": 18, "requires_business": True, "categories": ["Kam ta'minlangan oila"]},
        "amount": "Loyiha qiymatining bir qismi",
        "interest_rate": "Subsidiya — foizsiz",
        "term_months": "—",
        "grace_period": "—",
        "required_documents": ["Yer hujjati", "Loyiha-smeta hujjati", "Pasport"],
        "application_channel": "Tuman qishloq xo'jaligi bo'limi",
        "official_url": "https://agro.uz",
    },
    {
        "name": "Ijtimoiy himoya yagona reyestri orqali yordam",
        "type": "benefit",
        "organization": "Ijtimoiy himoya milliy agentligi",
        "target_group": "Kam ta'minlangan oilalar",
        "eligibility": {"min_age": 18, "requires_business": False, "categories": ["Kam ta'minlangan oila", "Ijtimoiy himoyaga muhtoj"]},
        "amount": "Oila daromadiga qarab belgilanadi",
        "interest_rate": "—",
        "term_months": "—",
        "grace_period": "—",
        "required_documents": ["Pasport", "Oila tarkibi ma'lumotnomasi", "Daromad ma'lumotnomasi"],
        "application_channel": "Mahalla yoki tuman ijtimoiy himoya bo'limi",
        "official_url": "https://gov.uz",
    },
    {
        "name": "Ta'lim kontrakti uchun imtiyozli kredit",
        "type": "credit",
        "organization": "O'zbekiston Milliy banki",
        "target_group": "Oliy va professional ta'lim talabalari",
        "eligibility": {"min_age": 16, "max_age": 35, "requires_business": False, "categories": ["Yoshlar daftari", "Kam ta'minlangan oila"]},
        "amount": "Kontrakt summasigacha",
        "interest_rate": "Imtiyozli stavka",
        "term_months": "O'qish muddati + 12 oy",
        "grace_period": "O'qish davri",
        "required_documents": ["Pasport", "Talabalik ma'lumotnomasi", "Kontrakt shartnomasi"],
        "application_channel": "Bank filiali",
        "official_url": "https://nbu.uz",
    },
    {
        "name": "Temir daftar orqali moddiy yordam",
        "type": "subsidy",
        "organization": "Mahalla va oilani qo'llab-quvvatlash tizimi",
        "target_group": "Temir daftar va ijtimoiy reyestrga kiritilgan oilalar",
        "eligibility": {"min_age": 18, "requires_business": False, "categories": ["Temir daftar", "Kam ta'minlangan oila", "Nogironligi bor (I guruh)", "Nogironligi bor (II guruh)"]},
        "amount": "Tuman komissiyasi qaroriga asosan",
        "interest_rate": "—",
        "term_months": "—",
        "grace_period": "—",
        "required_documents": ["Pasport", "Oila tarkibi ma'lumotnomasi", "Tegishli toifa hujjati"],
        "application_channel": "Mahalla fuqarolar yig'ini",
        "official_url": "https://gov.uz",
    },
]


LEGISLATION = [
    {
        "title": "O'zbekiston Respublikasi Konstitutsiyasi",
        "number": "Konstitutsiya",
        "doc_type": "Konstitutsiya",
        "url": "https://lex.uz/uz/search/all?q=Konstitutsiya",
        "chunks": [
            ("Umumiy qoida", "Inson va uning hayoti, erkinligi, sha'ni, qadr-qimmati va boshqa daxlsiz huquqlari oliy qadriyat hisoblanadi. Davlat o'z faoliyatini inson manfaatlarini ta'minlashga qaratadi."),
            ("Ijtimoiy himoya", "Davlat aholining ijtimoiy himoyaga muhtoj qatlamlarini qo'llab-quvvatlaydi, ijtimoiy ta'minot tizimini rivojlantiradi va nogironligi bor shaxslarning huquqlarini ta'minlaydi."),
            ("Mahalliy o'zini o'zi boshqarish", "Mahalla fuqarolarning o'zini o'zi boshqarish organi sifatida aholining kundalik ehtiyojlarini hal etishda ishtirok etadi."),
        ],
        "note": "Konstitutsiyaning amaldagi tahriri Lex.uz dan olinadi. Modda raqamlari rasmiy matn bo'yicha tekshirilishi shart.",
    },
    {
        "title": "Fuqarolarning murojaatlari to'g'risida",
        "number": "O'RQ-445",
        "doc_type": "Qonun",
        "url": "https://lex.uz/uz/search/all?q=Fuqarolarning%20murojaatlari%20to%27g%27risida",
        "chunks": [
            ("Murojaat shakllari", "Fuqarolar murojaatlari taklif, ariza va shikoyat shaklida bo'lishi mumkin. Murojaat og'zaki, yozma yoki elektron shaklda yuborilishi mumkin."),
            ("Ko'rib chiqish muddati", "Murojaatlar qonunchilikda belgilangan muddatlarda ko'rib chiqilishi va fuqaroga javob berilishi kerak. Qo'shimcha o'rganish talab etilsa, muddat uzaytirilishi mumkin."),
            ("Raqamlashtirish", "Elektron murojaatlar yagona interaktiv davlat xizmatlari portali orqali ham yuborilishi mumkin."),
        ],
        "note": "Demo snapshot. Aniq muddatlar va tartib Lex.uz dagi amaldagi tahrirda tekshiriladi.",
    },
    {
        "title": "Bandlik to'g'risida",
        "number": "O'RQ-194",
        "doc_type": "Qonun",
        "url": "https://lex.uz/uz/search/all?q=Bandlik%20to%27g%27risida",
        "chunks": [
            ("Bandlikka ko'maklashish", "Davlat bandlikka ko'maklashish tizimini yuritadi, ishsiz fuqarolarni ro'yxatga oladi va ish topishda ko'maklashadi."),
            ("Ishsiz deb e'tirof etish", "Ishsiz deb bandlik organlarida ro'yxatga olingan, ish bilan ta'minlanmagan va daromadga ega bo'lmagan mehnatga layoqatli fuqarolar e'tirof etiladi."),
            ("Kasb-hunar tayyorlash", "Ishsiz fuqarolar kasb-hunar tayyorlash va qayta tayyorlash kurslariga yuborilishi mumkin."),
        ],
        "note": "Demo snapshot. Amaldagi tartib Lex.uz dagi tahrirda tekshiriladi.",
    },
    {
        "title": "Tadbirkorlik faoliyati erkinligining kafolatlari to'g'risida",
        "number": "O'RQ-328",
        "doc_type": "Qonun",
        "url": "https://lex.uz/uz/search/all?q=Tadbirkorlik%20faoliyati%20erkinligining%20kafolatlari",
        "chunks": [
            ("Kafolatlar", "Davlat tadbirkorlik faoliyati erkinligini kafolatlaydi va noqonuniy aralashuvga yo'l qo'ymaydi."),
            ("Ruxsat berish tartibi", "Tadbirkorlik faoliyatini boshlash uchun talab qilinadigan ruxsatlar qonunchilikda belgilangan tartibda olinadi."),
        ],
        "note": "Demo snapshot. Amaldagi tahrir Lex.uz dan tekshiriladi.",
    },
    {
        "title": "Mahalla va oilani qo'llab-quvvatlash tizimini takomillashtirish chora-tadbirlari to'g'risida",
        "number": "PF-5938",
        "doc_type": "Farmon",
        "url": "https://lex.uz/uz/search/all?q=PF-5938",
        "chunks": [
            ("Mahalla instituti", "Mahalla aholi bilan ishlashning asosiy bo'g'ini sifatida mustahkamlanadi, uning moddiy-texnik bazasi rivojlantiriladi."),
            ("Ijtimoiy reyestr", "Kam ta'minlangan va ijtimoiy himoyaga muhtoj oilalarni aniqlash uchun ijtimoiy reyestr yuritiladi."),
        ],
        "note": "Demo snapshot. Farmonning amaldagi tahriri Lex.uz dan olinadi.",
    },
    {
        "title": "Aholining ijtimoiy himoyasini kuchaytirish bo'yicha qo'shimcha chora-tadbirlar to'g'risida",
        "number": "PF-5938-izoh",
        "doc_type": "Farmon",
        "url": "https://lex.uz/uz/search/all?q=ijtimoiy%20himoya",
        "chunks": [
            ("Manzilli yordam", "Ijtimoiy yordam oilaning haqiqiy daromadi va ehtiyojidan kelib chiqib, manzilli tarzda ko'rsatiladi."),
            ("Ayollar va yoshlar", "Ayollar daftari va Yoshlar daftari orqali alohida toifadagi fuqarolarga qo'shimcha yordam ko'rsatiladi."),
        ],
        "note": "Demo snapshot. Rasmiy matn va amaldagi holat Lex.uz orqali tekshiriladi.",
    },
]


def seed_programs(db: Session) -> None:
    for item in PROGRAMS:
        program = db.execute(
            select(Program).where(Program.name == item["name"], Program.organization == item["organization"])
        ).scalar_one_or_none()
        if program is None:
            program = Program(name=item["name"], organization=item["organization"])
            db.add(program)
        program.type = item["type"]
        program.target_group = item["target_group"]
        program.region = "Xorazm viloyati, Urganch shahri"
        program.eligibility = item["eligibility"]
        program.amount = item["amount"]
        program.interest_rate = item["interest_rate"]
        program.term_months = item["term_months"]
        program.grace_period = item["grace_period"]
        program.required_documents = item["required_documents"]
        program.application_channel = item["application_channel"]
        program.official_url = item["official_url"]
        program.valid_from = date(2025, 1, 1)
        program.valid_to = date(2026, 12, 31)
        program.last_verified_at = NOW - timedelta(days=_stable_int(item["name"], 20) + 1)
        program.status = "verified"
        program.notes = (
            "Demo ma'lumot bazasi. Yakuniy shartlar, stavka va talablar bank filialida "
            "yoki rasmiy saytda tasdiqlanishi shart."
        )
        db.flush()
        if not db.execute(
            select(ProgramSource).where(ProgramSource.program_id == program.id)
        ).scalar_one_or_none():
            db.add(
                ProgramSource(
                    program_id=program.id,
                    url=item["official_url"],
                    title=f"{item['organization']} rasmiy sayti",
                    retrieved_at=program.last_verified_at,
                    content_hash=hashlib.sha256(item["name"].encode()).hexdigest(),
                    status="verified",
                    notes="Manba sifatida saqlangan rasmiy havola.",
                )
            )
    db.commit()


def seed_legislation(db: Session) -> None:
    for item in LEGISLATION:
        document = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == item["url"])
        ).scalar_one_or_none()
        if document is None:
            document = LegislationDocument(source_url=item["url"], title=item["title"])
            db.add(document)
            db.flush()
        document.title = item["title"]
        document.number = item["number"]
        document.doc_type = item["doc_type"]
        document.adoption_date = None
        document.effective_date = None
        document.last_revision_date = None
        document.legal_status = "demo_snapshot"
        document.retrieved_at = NOW - timedelta(days=1)
        document.version_identifier = "demo-snapshot-2026-11"
        text = "\n\n".join(f"{heading}. {content}" for heading, content in item["chunks"])
        document.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document.raw_html = ""
        db.flush()
        version = db.execute(
            select(LegislationVersion).where(
                LegislationVersion.document_id == document.id,
                LegislationVersion.is_current.is_(True),
            )
        ).scalar_one_or_none()
        if version is None:
            version = LegislationVersion(
                document_id=document.id,
                version_label=document.version_identifier,
                content_hash=document.content_hash,
                raw_text=text,
                retrieved_at=document.retrieved_at,
            )
            db.add(version)
            db.flush()
        version.content_hash = document.content_hash
        version.raw_text = text
        version.retrieved_at = document.retrieved_at
        version.is_current = True
        existing = db.execute(
            select(LegislationChunk).where(LegislationChunk.version_id == version.id)
        ).scalars().all()
        if not existing:
            for index, (heading, content) in enumerate(item["chunks"]):
                db.add(
                    LegislationChunk(
                        document_id=document.id,
                        version_id=version.id,
                        article="",
                        heading=heading,
                        content=content,
                        chunk_index=index,
                        search_text=f"{item['title']} {heading} {content}".lower(),
                    )
                )
        db.flush()
    db.commit()


def seed_settings(db: Session) -> None:
    defaults = {
        "app": {
            "theme": "system",
            "language": "uz-Latn",
            "timezone": "Asia/Tashkent",
            "ai_provider": "nvidia",
            "ai_model": "",
            "ai_budget": 300000,
            "agents_enabled": {
                "document": True,
                "reporting": True,
                "legislation": True,
                "credit_subsidy": True,
                "plan_control": True,
            },
            "scheduler_time": "21:00",
            "demo_mode": True,
            "mahalla": "Navbahor mahallasi",
            "district": "Urganch shahri",
            "region": "Xorazm viloyati",
        }
    }
    for key, value in defaults.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
    jobs = [
        ("kunlik-hisobot", "daily_report", "daily", {"type": "daily", "use_ai": True}),
        ("kechikkan-vazifalar", "overdue_scan", "daily", {}),
        ("qonunchilik-yangilash", "legislation_refresh", "weekly", {}),
        ("dasturlar-tekshirish", "programs_refresh", "monthly", {}),
    ]
    for name, job_type, schedule, payload in jobs:
        job = db.execute(select(ScheduledJob).where(ScheduledJob.name == name)).scalar_one_or_none()
        if job is None:
            job = ScheduledJob(name=name, job_type=job_type, schedule=schedule, payload=payload)
            db.add(job)
            job.next_run_at = NOW + timedelta(minutes=15)
    db.commit()


def seed_conversation(db: Session) -> None:
    if db.execute(select(Conversation).limit(1)).scalar_one_or_none():
        return
    conversation = Conversation(title="Kunlik ish rejasi")
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            ConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content="Bugun qaysi vazifalarga e'tibor berishim kerak?",
                created_at=NOW - timedelta(hours=3),
            ),
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=(
                    "Bugungi rejada muddati bugun tugaydigan vazifalar va kechikkan murojaatlar "
                    "birinchi navbatda turadi. Menyu → Vazifalar bo'limida ularni ustuvorlik bo'yicha "
                    "ko'rishingiz mumkin."
                ),
                agent="plan_control",
                created_at=NOW - timedelta(hours=3) + timedelta(seconds=40),
            ),
        ]
    )
    db.commit()


def seed_admin(db: Session) -> None:
    from app.core.config import assert_admin_password_allowed, settings

    # K-6: ishlab chiqarishda standart parol bilan admin yaratilmasligi kerak.
    assert_admin_password_allowed()
    username = (settings.admin_username or "wax").strip().lower()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(username=username)
        db.add(user)
    user.display_name = "Mahalla administratori"
    user.password_hash = hash_password(settings.admin_password or "waxs")
    user.role = "admin"
    user.permissions = []
    user.is_active = True
    db.commit()


def run() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_admin(db)
        seed_hierarchy(db)
        seed_operational(db)
        seed_programs(db)
        seed_legislation(db)
        seed_settings(db)
        seed_conversation(db)
        citizens = db.execute(select(Citizen)).scalars().all()
        print(f"Seed tugadi: {len(citizens)} fuqaro, mahalla Navbahor.")


if __name__ == "__main__":
    run()
