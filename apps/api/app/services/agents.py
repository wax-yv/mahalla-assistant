from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.audit import write_audit
from app.core.errors import bad_request, not_found
from app.core.time import today_local
from app.models import (
    AgentRun,
    AgentWorkflow,
    Case,
    Citizen,
    Conversation,
    ConversationMessage,
    Document,
    DraftAction,
    Family,
    House,
    ImportBatch,
    ImportError as ImportErrorModel,
    MemoryItem,
    Program,
    Street,
    Task,
    User,
    WorkLog,
)
from app.schemas import (
    CaseCreate,
    ReportGenerateRequest,
    TaskCreate,
    WorkLogCreate,
)
from app.services import ai_gateway, cases, dashboard, documents, legislation, programs, reports
from app.services.serializers import citizen_out, document_out, program_out, task_out

AGENT_LABELS = {
    "orchestrator": "Orchestrator",
    "document": "Hujjat agenti",
    "reporting": "Hisobot agenti",
    "legislation": "Qonunchilik agenti",
    "credit_subsidy": "Kredit va subsidiya agenti",
    "plan_control": "Reja va nazorat agenti",
}

INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("legislation", ("qonun", "modda", "lex.uz", "lexuz", "farmon", "kodeks", "konstitutsiya", "huquqiy norma", "qonunchilik")),
    ("credit_subsidy", ("kredit", "subsidiya", "ipoteka", "grant", "bank", "moliyalashtirish", "foizsiz yordam")),
    ("reporting", ("hisobot", "statistika", "ko'rsatkich", "tahlil", "necha foiz", "dinamika", "hisob-kitob")),
    ("document", ("hujjat", "fayl", "import", "eksport", "excel", "xlsx", "csv", "docx", "pdf", "yukla", "xatolik")),
    ("plan_control", ("vazifa", "reja", "bugun", "ertaga", "muddat", "kechik", "nazorat", "bajarildi", "bajarilmadi")),
    ("citizen_lookup", ("fuqaro", "kim", "manzil", "telefon", "oilasi", "yoshi", "haqida ma'lumot", "topib ber")),
]

STOPWORDS = {
    "men", "menga", "mening", "biz", "siz", "u", "bu", "shu", "qaysi", "nima",
    "qanday", "kerak", "iltimos", "bo'lsa", "haqida", "uchun", "bilan", "va",
    "yoki", "ham", "endi", "hozir", "bugun", "ertaga", "mumkin", "bor", "yo'q",
    "ayting", "ko'rsating", "bering", "qilib", "bo'ladi", "edi", "ekan",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


GREETING_RE = re.compile(
    r"\b(salom|assalomu|hayrli|salomlayman|hello|siz kim|kimsiz|kim siz|"
    r"nima qila olasiz|nimaga qodirsiz|yordam bering|qanday ishlar)\b",
    re.IGNORECASE,
)


def detect_intent(message: str) -> tuple[str, list[str]]:
    text = (message or "").lower()
    if GREETING_RE.search(text) and len(text.split()) <= 12:
        return "smalltalk", ["smalltalk"]
    scores: dict[str, int] = {}
    for intent, keywords in INTENT_RULES:
        score = 0
        for keyword in keywords:
            if keyword in text:
                score += 2 if len(keyword) > 6 else 1
        if score:
            scores[intent] = score
    if not scores:
        return "smalltalk", []
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    primary, top = ordered[0]
    secondary = [name for name, score in ordered[1:] if score >= max(2, top - 1)]
    if secondary:
        return "multi", [primary, *secondary[:2]]
    return primary, [primary]


def _clean_query(message: str) -> str:
    value = re.sub(r"[?.!,;:]+", " ", message or "")
    words = [word for word in value.split() if word.lower() not in STOPWORDS]
    return " ".join(words).strip()


def _org_list(db: Session) -> list[str]:
    return [item["name"] for item in programs.organizations(db)]


def _citizen_search(db: Session, message: str) -> list[Citizen]:
    text = message.strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 9:
        tail = digits[-9:]
        rows = db.execute(
            select(Citizen)
            .options(joinedload(Citizen.family).joinedload(Family.house).joinedload(House.street).joinedload(Street.mahalla))
            .where(Citizen.archived_at.is_(None), Citizen.phone.ilike(f"%{tail}%"))
            .limit(5)
        ).scalars().all()
        if rows:
            return list(rows)
    candidates = re.findall(r"[A-ZOʻʼ'][a-zA-Zʻʼ'‘’\-]{2,}", text)
    tokens = [token for token in candidates if token.lower() not in STOPWORDS][:4]
    base = (
        select(Citizen)
        .options(joinedload(Citizen.family).joinedload(Family.house).joinedload(House.street).joinedload(Street.mahalla))
        .where(Citizen.archived_at.is_(None))
    )
    if tokens:
        conditions = [Citizen.full_name.ilike(f"%{token}%") for token in tokens]
        rows = db.execute(base.where(or_(*conditions)).limit(8)).scalars().all()
        if rows:
            return list(rows)
    cleaned = _clean_query(text)
    if cleaned:
        rows = db.execute(base.where(Citizen.full_name.ilike(f"%{cleaned}%")).limit(8)).scalars().all()
        if rows:
            return list(rows)
    return []


def _address_text(citizen: Citizen) -> str:
    family = citizen.family
    if not family or not family.house:
        return "Manzil ko'rsatilmagan"
    house = family.house
    street = house.street
    mahalla = street.mahalla if street else None
    return f"{mahalla.name if mahalla else ''}, {street.name if street else ''}, {house.house_number}-uy"


def _money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _agent_error_message(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"[:500]


def _task_brief(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "citizen": task.citizen.full_name if getattr(task, "citizen", None) else None,
        "category": task.category,
    }


def _case_brief(case: Case) -> dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "status": case.status,
        "priority": case.priority,
        "category": case.category,
        "opened_at": case.opened_at.isoformat(),
        "citizen": case.citizen.full_name if getattr(case, "citizen", None) else None,
    }


def _describe_task_lines(tasks: list[Task], limit: int = 6) -> str:
    lines = []
    for task in tasks[:limit]:
        due = task.due_date.strftime("%d.%m.%Y") if task.due_date else "muddatsiz"
        who = f" — {task.citizen.full_name}" if getattr(task, "citizen", None) else ""
        lines.append(f"• {task.title}{who} (muddat: {due}, holat: {task.status})")
    return "\n".join(lines)


def _plan_facts(db: Session) -> dict[str, Any]:
    today = today_local()
    tasks = db.execute(
        select(Task)
        .options(joinedload(Task.citizen))
        .where(Task.status.notin_(["completed", "cancelled"]))
        .order_by(Task.due_date.is_(None), Task.due_date, Task.priority.desc())
    ).scalars().unique().all()
    due_today = [task for task in tasks if task.due_date == today]
    overdue = [task for task in tasks if task.due_date and task.due_date < today]
    upcoming = [task for task in tasks if task.due_date and today < task.due_date <= today + timedelta(days=3)]
    open_cases = db.execute(
        select(Case)
        .options(joinedload(Case.citizen))
        .where(Case.status.in_(["open", "in_progress", "waiting"]))
        .order_by(Case.priority.desc(), Case.opened_at)
        .limit(40)
    ).scalars().unique().all()
    urgent_cases = [case for case in open_cases if case.priority in {"urgent", "high"}]
    recent_logs = db.execute(
        select(WorkLog)
        .options(joinedload(WorkLog.citizen))
        .order_by(WorkLog.occurred_at.desc())
        .limit(5)
    ).scalars().unique().all()
    return {
        "today": today.isoformat(),
        "due_today": due_today,
        "overdue": overdue,
        "upcoming": upcoming,
        "open_cases": open_cases,
        "urgent_cases": urgent_cases,
        "recent_logs": recent_logs,
    }


def _plan_control(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    facts = _plan_facts(db)
    text = message.lower()
    drafts: list[dict[str, Any]] = []
    sources = [
        {"type": "database", "label": "Vazifalar va murojaatlar bazasi", "as_of": _now().isoformat()}
    ]
    title_match = re.search(r"(?:vazifa|topshiriq)\s*(?:yarat|qo'sh|qosh|ber)[:\s]*(.+)", message, re.I)
    if title_match:
        title = title_match.group(1).strip(" .\"'")[:200]
        due = facts["today"]
        if "ertaga" in text:
            due = (today_local() + timedelta(days=1)).isoformat()
        elif "indin" in text:
            due = (today_local() + timedelta(days=2)).isoformat()
        drafts.append(
            {
                "action_type": "create_task",
                "payload": {
                    "title": title or "Yangi topshiriq",
                    "description": f"AI assistent orqali taklif qilindi. Manba: {message[:300]}",
                    "category": "Boshqa",
                    "priority": "high" if "shoshil" in text or "muhim" in text else "normal",
                    "due_date": due,
                },
                "label": f"Vazifa yaratish: {title or 'Yangi topshiriq'}",
            }
        )
    lines = [
        f"Bugun {datetime.now().strftime('%d.%m.%Y')} holatiga ko'ra {len(facts['due_today'])} ta vazifa muddati bugun tugaydi, {len(facts['overdue'])} ta vazifa muddatidan oshgan.",
        "",
        "Muddati bugun tugaydigan vazifalar:",
        _describe_task_lines(facts["due_today"]) or "• Bugun uchun rejalashtirilgan vazifa yo'q.",
        "",
        "Muddatidan oshgan vazifalar:",
        _describe_task_lines(facts["overdue"]) or "• Kechikkan vazifa yo'q.",
        "",
        f"Ochiq murojaatlar: {len(facts['open_cases'])} ta, shundan {len(facts['urgent_cases'])} tasi yuqori yoki shoshilinch ustuvorlikda.",
    ]
    if facts["urgent_cases"]:
        lines.append("Yuqori ustuvorlikdagi murojaatlar:")
        for case in facts["urgent_cases"][:5]:
            who = f" — {case.citizen.full_name}" if getattr(case, "citizen", None) else ""
            lines.append(f"• {case.title}{who} ({case.status})")
    if facts["recent_logs"]:
        lines.append("")
        lines.append("So'nggi ish yozuvlari:")
        for log in facts["recent_logs"][:4]:
            lines.append(f"• {log.title} — {log.occurred_at.strftime('%d.%m.%Y %H:%M')}")
    lines.append("")
    lines.append("Tavsiya: avval muddatidan oshgan va shoshilinch toifadagi ishlarni yoping, so'ng bugungi vazifalarga o'ting.")
    return {
        "text": "\n".join(lines),
        "sources": sources,
        "drafts": drafts,
        "data": {
            "due_today": [_task_brief(task) for task in facts["due_today"][:10]],
            "overdue": [_task_brief(task) for task in facts["overdue"][:10]],
            "open_cases": [_case_brief(case) for case in facts["open_cases"][:10]],
        },
        "confidence": "high",
        "warnings": [],
    }


def _citizen_profile(db: Session, citizen: Citizen) -> dict[str, Any]:
    family = citizen.family
    members = []
    if family:
        members = [member for member in family.members if member.archived_at is None]
    tasks = db.execute(
        select(Task).where(Task.citizen_id == citizen.id).order_by(Task.created_at.desc()).limit(6)
    ).scalars().all()
    cases = db.execute(
        select(Case).where(Case.citizen_id == citizen.id).order_by(Case.opened_at.desc()).limit(6)
    ).scalars().all()
    logs = db.execute(
        select(WorkLog).where(WorkLog.citizen_id == citizen.id).order_by(WorkLog.occurred_at.desc()).limit(5)
    ).scalars().all()
    return {
        "citizen": citizen_out(citizen),
        "address": _address_text(citizen),
        "family_members": len(members),
        "family_head": family.family_head_citizen_id if family else None,
        "tasks": [_task_brief(task) for task in tasks],
        "cases": [_case_brief(case) for case in cases],
        "work_logs": [
            {
                "id": log.id,
                "title": log.title,
                "type": log.type,
                "occurred_at": log.occurred_at.isoformat(),
            }
            for log in logs
        ],
    }


def _citizen_lookup(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    matches = _citizen_search(db, message)
    if not matches:
        return {
            "text": (
                "Fuqaro topilmadi. Iltimos, F.I.Sh. (kamida familiya va ism), telefon raqami "
                "yoki manzilni aniqroq yozing. Masalan: «Zokirov Yusuf haqida ma'lumot»."
            ),
            "sources": [],
            "drafts": [],
            "data": {"matches": []},
            "confidence": "low",
            "warnings": ["Fuqaro bazasidan aniq mos yozuv topilmadi."],
        }
    if len(matches) > 1:
        lines = [f"Bir nechta mos fuqaro topildi ({len(matches)} ta). Qaysi biri kerakligini aniqlashtiring:", ""]
        options = []
        for citizen in matches[:8]:
            options.append(
                {
                    "id": citizen.id,
                    "full_name": citizen.full_name,
                    "address": _address_text(citizen),
                    "birth_date": citizen.birth_date.isoformat() if citizen.birth_date else None,
                }
            )
            lines.append(f"• {citizen.full_name} — {_address_text(citizen)}")
        return {
            "text": "\n".join(lines),
            "sources": [{"type": "database", "label": "Fuqarolar bazasi"}],
            "drafts": [],
            "data": {"matches": options},
            "confidence": "medium",
            "warnings": [],
        }
    citizen = matches[0]
    profile = _citizen_profile(db, citizen)
    address = profile["address"]
    lines = [
        f"{citizen.full_name} ({citizen.id})",
        f"Manzil: {address}",
        f"Tug'ilgan sana: {citizen.birth_date.strftime('%d.%m.%Y') if citizen.birth_date else 'ko‘rsatilmagan'}",
        f"Telefon: {citizen.phone or 'ko‘rsatilmagan'}",
        f"Oiladagi o'rni: {citizen.family_role}; oila a'zolari: {profile['family_members']} nafar",
        f"Bandlik: {citizen.employment_status}; kasbi: {citizen.profession or 'ko‘rsatilmagan'}",
        f"Ijtimoiy holati: {citizen.social_status or 'Yo‘q'}",
    ]
    if citizen.needs:
        lines.append(f"Ehtiyoji: {', '.join(citizen.needs)}")
    if profile["cases"]:
        lines.append("")
        lines.append("Ochiq va so'nggi murojaatlar:")
        for case in profile["cases"][:4]:
            lines.append(f"• {case['title']} ({case['status']}, {case['priority']})")
    if profile["tasks"]:
        lines.append("")
        lines.append("Vazifalar:")
        for task in profile["tasks"][:4]:
            lines.append(f"• {task['title']} ({task['status']})")
    if citizen.last_verified_at:
        lines.append("")
        lines.append(f"Ma'lumot oxirgi marta {citizen.last_verified_at.strftime('%d.%m.%Y')} da tekshirilgan.")
    return {
        "text": "\n".join(lines),
        "sources": [{"type": "database", "label": "Fuqarolar bazasi", "record_id": citizen.id}],
        "drafts": [],
        "data": profile,
        "confidence": "high",
        "warnings": [],
    }


def _period_for(message: str) -> tuple[date, date, str]:
    today = today_local()
    text = message.lower()
    if "kecha" in text:
        start = today - timedelta(days=1)
        return start, start, "kecha"
    if "hafta" in text:
        return today - timedelta(days=today.weekday()), today, "shu hafta"
    if "oy" in text:
        return today.replace(day=1), today, "shu oy"
    if "yil" in text:
        return today.replace(month=1, day=1), today, "shu yil"
    return today, today, "bugun"


def _reporting(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    start, end, label = _period_for(message)
    metrics = reports.compute_metrics(db, "daily", start, end, {})
    employment = metrics.get("employment", {})
    cases = metrics.get("cases", {})
    tasks = metrics.get("tasks", {})
    quality = metrics.get("quality", {})
    totals = metrics.get("totals", {})
    lines = [
        f"{label.capitalize()} uchun asosiy ko'rsatkichlar ({start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}):",
        f"• Aholi: {totals.get('citizens', 0)} nafar fuqaro, {totals.get('families', 0)} ta oila, {totals.get('houses', 0)} ta uy.",
        f"• Bandlik: {employment.get('employed', 0)} nafar band, {employment.get('unemployed', 0)} nafar ishsiz; bandlik darajasi {employment.get('employment_rate', 0)} foiz.",
        f"• Murojaatlar: {cases.get('total', 0)} ta, ochiq: {cases.get('open', 0)} ta.",
        f"• Vazifalar: {tasks.get('total', 0)} ta, bajarilgan: {tasks.get('completed', 0)} ta, muddati o'tgan: {tasks.get('overdue', 0)} ta.",
        f"• Ma'lumot sifati: {quality.get('score', 0)} foiz; to'ldirilmagan yozuvlar: {quality.get('incomplete', 0)} ta.",
    ]
    drafts: list[dict[str, Any]] = []
    text = message.lower()
    if any(word in text for word in ("tayyorla", "shakllantir", "yarat", "hisobot ber")):
        report_type = "daily"
        if "hafta" in text:
            report_type = "weekly"
        elif "oy" in text:
            report_type = "monthly"
        drafts.append(
            {
                "action_type": "generate_report",
                "payload": {
                    "type": report_type,
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                    "filters": {},
                },
                "label": f"Hisobot loyihasini yaratish: {label}",
            }
        )
        lines.append("")
        lines.append("Hisobot loyihasini yaratish uchun quyidagi amalni tasdiqlang. Tasdiqlangandan so'ng hisobot «Hisobotlar» bo'limida draft holatida paydo bo'ladi.")
    return {
        "text": "\n".join(lines),
        "sources": [
            {"type": "database", "label": "Hisobot ko'rsatkichlari (SQL)", "as_of": _now().isoformat()}
        ],
        "drafts": drafts,
        "data": {"metrics": metrics, "period": {"start": start.isoformat(), "end": end.isoformat()}},
        "confidence": "high",
        "warnings": ["Ko'rsatkichlar demo ma'lumotlar bazasidan hisoblandi."],
    }


def _legislation_agent(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    question = re.sub(
        r"^(qonunchilik|qonun|lex\.uz|lexuz)\s*(bo'yicha|haqida)?\s*[:\-]?\s*",
        "",
        message.strip(),
        flags=re.I,
    )
    result = legislation.ask(db, question or message, use_ai=True)
    text = result["answer"]
    if result.get("synced"):
        text += "\n\nLex.uz dan yangi manbalar yuklandi: " + ", ".join(result["synced"][:3])
    return {
        "text": text,
        "sources": result.get("sources", []),
        "drafts": [],
        "data": {"documents": result.get("documents", []), "verified": result.get("verified", False)},
        "confidence": "medium" if result.get("verified") else "needs_review",
        "warnings": result.get("warnings", []),
    }


def _credit_subsidy(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    conversation_id = context.get("conversation_id")
    text = message.lower()
    organizations = _org_list(db)
    detected = programs.detect_organization(db, message)
    preference = programs.get_preference(db, conversation_id)
    saved_org = (preference or {}).get("organization") if isinstance(preference, dict) else None
    citizen: Citizen | None = None
    citizen_matches = _citizen_search(db, message)
    if len(citizen_matches) == 1:
        citizen = citizen_matches[0]
    if detected is None and saved_org:
        wants_general = any(
            word in text for word in ("dastur", "kredit", "subsidiya", "shart", "talab", "foiz", "summa", "muddat")
        )
        if wants_general:
            rows = [row for row in programs.list_programs(db) if row["organization"] == saved_org]
            detected = {"organization": saved_org, "programs": rows}
    if detected is None:
        lines = [
            "Qaysi bank yoki dastur bo'yicha ma'lumot kerakligini ayting.",
            "",
            "Masalan: «Xalq banki krediti shartlari qanday?» yoki «Agrobank ayollar tadbirkorligi dasturi».",
            "",
            "Mavjud yo'nalishlar:",
        ]
        for name in organizations[:8]:
            lines.append(f"• {name}")
        lines.append("")
        lines.append("Bank yoki dastur nomini aytganingizdan keyin faqat shu tashkilot bo'yicha aniq ma'lumot beraman va tanlovingizni eslab qolaman.")
        return {
            "text": "\n".join(lines),
            "sources": [],
            "drafts": [],
            "data": {"organizations": organizations, "needs_organization": True},
            "confidence": "high",
            "warnings": [],
        }
    organization = detected["organization"]
    rows = [row for row in programs.list_programs(db) if row["organization"] == organization]
    if not rows:
        rows = [program_out(item) for item in detected["programs"]]
    programs.save_preference(
        db,
        conversation_id=conversation_id,
        organization=organization,
        program_id=rows[0]["id"] if len(rows) == 1 else None,
        program_name=rows[0]["name"] if len(rows) == 1 else None,
    )
    matches = []
    if citizen:
        matched = programs.match_citizen(db, citizen.id)
        matches = [item for item in matched if item["program_name"] in {row["name"] for row in rows}]
    lines = [f"{organization} bo'yicha ma'lumot:"]
    for index, row in enumerate(rows[:4], start=1):
        lines.append("")
        lines.append(f"{index}. {row['name']} ({row['type']})")
        lines.append(f"   Maqsadli guruh: {row['target_group']}")
        lines.append(f"   Summa: {row['amount']}")
        lines.append(f"   Stavka: {row['interest_rate']}")
        lines.append(f"   Muddat: {row['term_months']}; imtiyozli davr: {row['grace_period']}")
        if row.get("required_documents"):
            lines.append(f"   Zarur hujjatlar: {', '.join(row['required_documents'])}")
        lines.append(f"   Ariza kanali: {row['application_channel']}")
        if row.get("official_url"):
            lines.append(f"   Rasmiy manba: {row['official_url']}")
        if row.get("last_verified_at"):
            try:
                verified = datetime.fromisoformat(str(row["last_verified_at"]).replace("Z", "+00:00"))
                lines.append(f"   Oxirgi tekshiruv: {verified.strftime('%d.%m.%Y')}")
            except ValueError:
                pass
    if matches:
        lines.append("")
        lines.append(f"{citizen.full_name} bo'yicha moslik:")
        for item in matches[:4]:
            lines.append(f"• {item['program_name']}: {item['result']} — {'; '.join(item['reasons'][:2])}")
    lines.append("")
    lines.append("Yakuniy shartlar bank filialida yoki rasmiy saytda tasdiqlanishi shart. Tanlangan bank keyingi savollarda eslab qolinadi.")
    return {
        "text": "\n".join(lines),
        "sources": [
            {
                "type": "program",
                "label": row["name"],
                "organization": organization,
                "url": row.get("official_url"),
                "verified_at": row.get("last_verified_at"),
            }
            for row in rows
        ],
        "drafts": [],
        "data": {
            "organization": organization,
            "programs": rows,
            "matches": matches,
            "citizen": citizen_out(citizen) if citizen else None,
        },
        "confidence": "medium",
        "warnings": [
            "Dastur shartlari demo bazasidan olingan. Rasmiy tasdiq uchun bank filialiga murojaat qiling."
        ],
    }


IMPORT_ERROR_LABELS = {
    "AMBIGUOUS_DATE": "Sana formati noaniq (kun/oy tartibi)",
    "MISSING_BIRTH_DATE": "Tug'ilgan sana ko'rsatilmagan",
    "MISSING_PHONE": "Telefon raqami ko'rsatilmagan",
    "FULL_NAME_REQUIRED": "F.I.Sh. bo'sh",
    "INVALID_BIRTH_DATE": "Tug'ilgan sana noto'g'ri formatda",
    "FUTURE_BIRTH_DATE": "Tug'ilgan sana kelajakda",
    "INVALID_PHONE": "Telefon raqami noto'g'ri",
    "DUPLICATE_IN_FILE": "Fayl ichida dublikat qator",
    "EXISTING_CITIZEN": "Bazada mavjud fuqaro (yangilanadi)",
    "MISSING_COLUMN": "Majburiy ustun topilmadi",
    "PARSE_NOTE": "Fayl o'qish izohi",
}


def _import_report(db: Session) -> dict[str, Any] | None:
    batch = db.execute(
        select(ImportBatch)
        .options(joinedload(ImportBatch.document))
        .order_by(ImportBatch.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if batch is None:
        return None
    rows = db.execute(
        select(ImportErrorModel).where(ImportErrorModel.batch_id == batch.id).order_by(ImportErrorModel.row_number)
    ).scalars().all()
    by_code: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    for row in rows:
        by_code[row.code] = by_code.get(row.code, 0) + 1
        if len(samples) < 8:
            samples.append(
                {
                    "row": row.row_number,
                    "code": row.code,
                    "message": row.message[:160],
                    "severity": row.severity,
                }
            )
    summary = batch.summary or {}
    return {
        "batch_id": batch.id,
        "file": batch.document.original_name if batch.document else batch.document_id,
        "status": batch.status,
        "total_rows": int(summary.get("total_rows", 0)),
        "valid_rows": int(summary.get("valid_rows", 0)),
        "error_count": batch.error_count or 0,
        "warning_count": batch.warning_count or 0,
        "by_code": dict(sorted(by_code.items(), key=lambda kv: kv[1], reverse=True)),
        "samples": samples,
        "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
    }


def _format_import_report(report: dict[str, Any]) -> str:
    status_labels = {
        "validated": "tekshiruvdan o'tdi — tasdiqlash mumkin",
        "failed": "xatolar bor — tuzatish kerak",
        "committed": "bazaga yozilgan",
        "rolled_back": "bekor qilingan",
        "mapping": "ustunlar aniqlanmoqda",
    }
    lines = [
        f"Import hisoboti: {report['file']}",
        f"Holati: {status_labels.get(report['status'], report['status'])}",
        f"Jami qatorlar: {report['total_rows']} · yaroqli: {report['valid_rows']} · xatolar: {report['error_count']} · ogohlantirishlar: {report['warning_count']}",
    ]
    if report["by_code"]:
        lines.append("")
        lines.append("Xatoliklar toifalari bo'yicha:")
        for code, count in report["by_code"].items():
            label = IMPORT_ERROR_LABELS.get(code, code)
            lines.append(f"• {label} — {count} ta")
        lines.append("")
        lines.append("Namuna qatorlar:")
        for sample in report["samples"]:
            lines.append(f"  {sample['row']}-qator: {sample['message']}")
    if report["status"] == "validated" and report["error_count"] == 0:
        lines.append("")
        lines.append("Xatolar yo'q — importni tasdiqlash uchun quyidagi amalni ma'qullang yoki «Hujjatlar» bo'limida «Bazaga yozish» tugmasini bosing.")
    elif report["error_count"]:
        lines.append("")
        lines.append("Tavsiya: ko'rsatilgan qatorlarni faylda tuzatib qayta yuklang. Tizim mavjud fuqarolarni yangilaydi, yangilarini qo'shadi; noqulay natija bo'lsa importni bekor qilish mumkin.")
    return "\n".join(lines)


def _document_agent(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    text = message.lower()
    document_count = int(db.execute(select(func.count()).select_from(Document)).scalar_one())
    report = _import_report(db)
    wants_report = any(
        word in text
        for word in ("xatolik", "xato", "tahlil", "hisobot", "tekshir", "muammo", "dublikat", "sifat", "qayta qur")
    )
    has_recent_batch = report is not None and report["status"] in {"validated", "failed", "mapping"}
    if report is not None and (wants_report or ("import" in text or "excel" in text or "xlsx" in text or "fayl" in text)):
        drafts: list[dict[str, Any]] = []
        if report["status"] == "validated" and report["error_count"] == 0:
            drafts.append(
                {
                    "action_type": "commit_import",
                    "payload": {"batch_id": report["batch_id"]},
                    "label": f"Importni bazaga yozish: {report['file']}",
                }
            )
        return {
            "text": _format_import_report(report),
            "sources": [
                {
                    "type": "import_batch",
                    "label": report["file"],
                    "batch_id": report["batch_id"],
                    "as_of": _now().isoformat(),
                }
            ],
            "drafts": drafts,
            "data": {"report": report},
            "confidence": "high",
            "warnings": [],
        }
    if "import" in text or "yukla" in text or "excel" in text or "xlsx" in text:
        lines = [
            "Hujjat import qilish tartibi:",
            "1. «Hujjatlar» bo'limiga o'ting.",
            "2. Excel (.xlsx), CSV yoki Word (.docx) faylini yuklang.",
            "3. Tizim ustunlarni avtomatik aniqlaydi va xatoliklarni ko'rsatadi.",
            "4. Xatoliklar hisobotini ko'rib, faylni tuzatib qayta yuklashingiz yoki yaroqli qatorlarni tasdiqlashingiz mumkin.",
            "5. Tasdiqlangandan keyin importni bekor qilish (rollback) imkoniyati mavjud.",
            "",
            f"Bazada jami {document_count} ta hujjat mavjud.",
        ]
        return {
            "text": "\n".join(lines),
            "sources": [{"type": "database", "label": "Hujjatlar bazasi"}],
            "drafts": [],
            "data": {"documents": document_count},
            "confidence": "high",
            "warnings": [],
        }
    if "eksport" in text or "yuklab ol" in text:
        return {
            "text": (
                "Eksport qilish uchun «Hujjatlar» yoki «Hisobotlar» bo'limidagi eksport tugmasidan foydalaning. "
                "Fuqarolar, oilalar, murojaatlar va vazifalarni Excel yoki CSV formatida yuklab olish mumkin. "
                "Hisobotlar PDF va Word formatida ham eksport qilinadi."
            ),
            "sources": [],
            "drafts": [],
            "data": {},
            "confidence": "high",
            "warnings": [],
        }
    if has_recent_batch:
        return {
            "text": _format_import_report(report),
            "sources": [{"type": "import_batch", "label": report["file"], "batch_id": report["batch_id"]}],
            "drafts": [],
            "data": {"report": report},
            "confidence": "high",
            "warnings": [],
        }
    return {
        "text": (
            f"Hujjatlar bazasida {document_count} ta fayl mavjud. "
            "Excel faylingizni «Hujjatlar» bo'limida yuklang — men ustunlarni aniqlab, xatoliklar "
            "hisobotini shakllantiraman. Yoki aniq savol bering: «Excel faylni qanday import qilaman?»"
        ),
        "sources": [{"type": "database", "label": "Hujjatlar bazasi"}],
        "drafts": [],
        "data": {},
        "confidence": "medium",
        "warnings": [],
    }


SMALLTALK_SYSTEM = """Siz «Mahalla Assistant» — O'zbekiston mahallasi uchun rasmiy ish assistentisiz.
Faqat o'zbek lotin tilida, qisqa va xushmuomala javob bering (2-4 gap).
Siz quyidagi ishlarni bajara olasiz: fuqarolar va oilalar bo'yicha ma'lumot qidirish,
murojaat va vazifalarni nazorat qilish, kunlik/haftalik hisobot tayyorlash,
Lex.uz qonunchiligi bo'yicha manbali javob berish, kredit va subsidiya dasturlarini
faqat foydalanuvchi tanlagan bank bo'yicha tushuntirish, hujjat import/eksport.
Raqamlar, sanalar yoki qonun moddalarini o'zingizdan o'ylab topmang.
Foydalanuvchini «siz» deb hurmat bilan chaqiring."""


def _smalltalk(db: Session, message: str, context: dict[str, Any]) -> dict[str, Any]:
    result = ai_gateway.chat_completion(
        db,
        messages=[
            {"role": "system", "content": SMALLTALK_SYSTEM},
            {"role": "user", "content": message},
        ],
        agent="orchestrator",
        max_tokens=350,
        temperature=0.3,
    )
    return {
        "text": result.content.strip(),
        "sources": [],
        "drafts": [],
        "data": {},
        "confidence": "medium",
        "warnings": [],
        "model": result.model,
        "provider": result.provider,
        "latency_ms": result.latency_ms,
        "token_input": result.prompt_tokens,
        "token_output": result.completion_tokens,
        "fallback_used": result.fallback_used,
    }


HANDLERS = {
    "plan_control": _plan_control,
    "citizen_lookup": _citizen_lookup,
    "reporting": _reporting,
    "legislation": _legislation_agent,
    "credit_subsidy": _credit_subsidy,
    "document": _document_agent,
}

INTENT_AGENT = {
    "plan_control": "plan_control",
    "citizen_lookup": "plan_control",
    "reporting": "reporting",
    "legislation": "legislation",
    "credit_subsidy": "credit_subsidy",
    "document": "document",
    "smalltalk": "orchestrator",
    "multi": "orchestrator",
}


def _conversation_title(message: str) -> str:
    clean = re.sub(r"\s+", " ", message).strip()
    if not clean:
        return "Yangi suhbat"
    return clean[:70] + ("…" if len(clean) > 70 else "")


def _get_or_create_conversation(
    db: Session, conversation_id: str | None, message: str
) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            return conversation
    conversation = Conversation(title=_conversation_title(message))
    db.add(conversation)
    db.flush()
    return conversation


def _draft_row(
    db: Session, workflow: AgentWorkflow, run: AgentRun | None, draft: dict[str, Any]
) -> DraftAction:
    row = DraftAction(
        workflow_id=workflow.id,
        run_id=run.id if run else None,
        action_type=draft["action_type"],
        payload=draft.get("payload", {}),
        status="pending",
    )
    db.add(row)
    db.flush()
    return row


def chat(
    db: Session,
    *,
    message: str,
    conversation_id: str | None = None,
    actor: str | None = None,
    request_id: str | None = None,
    preferred_provider: str | None = None,
) -> dict[str, Any]:
    message = (message or "").strip()
    if not message:
        raise bad_request("Xabar matni bo'sh bo'lishi mumkin emas.")
    conversation = _get_or_create_conversation(db, conversation_id, message)
    if conversation.archived_at is not None:
        conversation.archived_at = None
    user_message = ConversationMessage(
        conversation_id=conversation.id, role="user", content=message
    )
    db.add(user_message)
    intent, intents = detect_intent(message)
    workflow = AgentWorkflow(
        request_id=request_id or uuid.uuid4().hex,
        conversation_id=conversation.id,
        intent=intent,
        status="running",
        input={"message": message, "intents": intents},
        context={"actor": actor},
    )
    db.add(workflow)
    db.flush()
    primary_intent = intents[0] if intents else intent
    agent_name = INTENT_AGENT.get(primary_intent, "orchestrator")
    run = AgentRun(
        workflow_id=workflow.id,
        agent=agent_name,
        task="chat",
        status="running",
        input={"message": message, "intent": primary_intent},
    )
    db.add(run)
    db.flush()
    started = time.perf_counter()
    result: dict[str, Any]
    handler = HANDLERS.get(primary_intent)
    warning_messages: list[str] = []
    try:
        if handler is None:
            result = _smalltalk(
                db,
                message,
                {"conversation_id": conversation.id, "actor": actor},
            )
        else:
            result = handler(
                db,
                message,
                {"conversation_id": conversation.id, "actor": actor},
            )
    except Exception as error:
        warning_messages.append(f"Agent javobini shakllantirishda xatolik: {_agent_error_message(error)}")
        result = {
            "text": (
                "So'rovingiz bo'yicha ma'lumot tayyorlab bo'lmadi. Iltimos, savolni aniqroq "
                "qayta yuboring yoki bo'limlar orqali qo'lda tekshiring."
            ),
            "sources": [],
            "drafts": [],
            "data": {},
            "confidence": "low",
            "warnings": warning_messages,
        }
    elapsed = int((time.perf_counter() - started) * 1000)
    run.status = "completed"
    run.output = {"text": result["text"], "data": result.get("data", {})}
    run.sources = result.get("sources", [])
    run.warnings = list(dict.fromkeys([*result.get("warnings", []), *warning_messages]))
    run.confidence = result.get("confidence", "medium")
    run.model = result.get("model", "Deterministik qoidalar + SQL")
    run.provider = result.get("provider", "local")
    run.latency_ms = result.get("latency_ms", elapsed)
    run.token_input = result.get("token_input", 0)
    run.token_output = result.get("token_output", 0)
    run.finished_at = _now()
    draft_rows = []
    for draft in result.get("drafts", []):
        draft_rows.append(_draft_row(db, workflow, run, draft))
        run.proposed_actions.append(draft)
    workflow.status = "completed"
    workflow.result = {
        "text": result["text"],
        "agents_used": [agent_name],
        "warnings": run.warnings,
        "data": result.get("data", {}),
    }
    workflow.requires_approval = bool(draft_rows)
    assistant_message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=result["text"],
        agent=agent_name,
        workflow_id=workflow.id,
        sources=result.get("sources", []),
        draft_actions=[draft.id for draft in draft_rows],
    )
    db.add(assistant_message)
    conversation.updated_at = _now()
    write_audit(
        db,
        action="agent.chat",
        entity_type="agent_workflow",
        entity_id=workflow.id,
        actor_id=actor,
        new_value={
            "intent": intent,
            "agent": agent_name,
            "provider": run.provider,
            "model": run.model,
            "requires_approval": workflow.requires_approval,
        },
    )
    db.commit()
    db.refresh(assistant_message)
    return {
        "conversation_id": conversation.id,
        "message": assistant_message,
        "workflow_id": workflow.id,
        "intent": intent,
        "agents_used": [agent_name],
        "sources": result.get("sources", []),
        "draft_actions": draft_rows,
        "warnings": run.warnings,
        "requires_approval": workflow.requires_approval,
    }


def list_conversations(db: Session, limit: int = 40) -> list[dict[str, Any]]:
    conversations = db.execute(
        select(Conversation)
        .where(Conversation.archived_at.is_(None))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    ).scalars().all()
    result = []
    for conversation in conversations:
        count = int(
            db.execute(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation.id)
            ).scalar_one()
        )
        last = db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        result.append(
            {
                "id": conversation.id,
                "title": conversation.title,
                "archived_at": conversation.archived_at,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
                "message_count": count,
                "last_message": (last.content[:140] if last else None),
            }
        )
    return result


def get_conversation(db: Session, conversation_id: str) -> dict[str, Any]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise not_found("Suhbat topilmadi.")
    messages = db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.created_at)
    ).scalars().all()
    workflows = {
        row.id: row
        for row in db.execute(
            select(AgentWorkflow).where(AgentWorkflow.conversation_id == conversation.id)
        ).scalars().all()
    }
    payload = []
    for message in messages:
        drafts = []
        for draft_id in message.draft_actions or []:
            draft = db.get(DraftAction, draft_id)
            if draft:
                drafts.append(_draft_out(draft))
        payload.append(
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "role": message.role,
                "content": message.content,
                "agent": message.agent,
                "workflow_id": message.workflow_id,
                "sources": message.sources or [],
                "draft_actions": drafts,
                "created_at": message.created_at,
            }
        )
    return {
        "id": conversation.id,
        "title": conversation.title,
        "archived_at": conversation.archived_at,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": payload,
        "workflows": len(workflows),
    }


def create_conversation(db: Session, title: str = "Yangi suhbat") -> Conversation:
    conversation = Conversation(title=(title or "Yangi suhbat")[:200])
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def archive_conversation(db: Session, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise not_found("Suhbat topilmadi.")
    conversation.archived_at = _now()
    db.commit()
    db.refresh(conversation)
    return conversation


def _draft_out(draft: DraftAction) -> dict[str, Any]:
    return {
        "id": draft.id,
        "workflow_id": draft.workflow_id,
        "run_id": draft.run_id,
        "action_type": draft.action_type,
        "payload": draft.payload or {},
        "status": draft.status,
        "created_at": draft.created_at,
        "decided_at": draft.decided_at,
        "decided_by": draft.decided_by,
        "result": draft.result or {},
        "error": draft.error,
    }


def list_drafts(db: Session, status: str | None = "pending", limit: int = 50) -> list[dict[str, Any]]:
    stmt = select(DraftAction).order_by(DraftAction.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(DraftAction.status == status)
    return [_draft_out(row) for row in db.execute(stmt).scalars().all()]


def _execute_draft(
    db: Session, draft: DraftAction, actor: str, request_id: str | None
) -> dict[str, Any]:
    payload = draft.payload or {}
    if draft.action_type == "create_task":
        task = cases.create_task(db, TaskCreate(**payload), actor, request_id)
        return {"entity_type": "task", "entity_id": task.id, "label": task.title}
    if draft.action_type == "create_case":
        case = cases.create_case(db, CaseCreate(**payload), actor, request_id)
        return {"entity_type": "case", "entity_id": case.id, "label": case.title}
    if draft.action_type == "create_worklog":
        log = cases.create_work_log(db, WorkLogCreate(**payload), actor, request_id)
        return {"entity_type": "work_log", "entity_id": log.id, "label": log.title}
    if draft.action_type == "generate_report":
        report = reports.generate_report(
            db, ReportGenerateRequest(**payload), actor=actor, request_id=request_id
        )
        return {"entity_type": "report", "entity_id": report.id, "label": report.title}
    if draft.action_type == "sync_legislation":
        if payload.get("url"):
            document = legislation.ingest_document(db, payload["url"], actor=actor)
            return {"entity_type": "legislation_document", "entity_id": document.id, "label": document.title}
        if payload.get("query"):
            synced_docs = legislation.sync_query(
                db, payload["query"], limit=int(payload.get("limit", 3)), actor=actor
            )
            return {
                "entity_type": "legislation_document",
                "entity_id": synced_docs[0].id if synced_docs else None,
                "label": f"{len(synced_docs)} ta hujjat sinxronlandi",
            }
        raise bad_request("Sinxronlash uchun query yoki url kerak.")
    if draft.action_type == "save_preference":
        programs.save_preference(
            db,
            conversation_id=payload.get("conversation_id"),
            organization=payload.get("organization", ""),
            program_id=payload.get("program_id"),
            program_name=payload.get("program_name"),
        )
        return {"entity_type": "memory_item", "label": payload.get("organization", "")}
    if draft.action_type == "commit_import":
        result = documents.commit_batch(
            db,
            payload["batch_id"],
            actor=actor,
            idempotency_key=payload.get("idempotency_key"),
            request_id=request_id,
        )
        return {
            "entity_type": "import_batch",
            "entity_id": payload["batch_id"],
            "label": f"Import: {result.get('created', 0)} yangi, {result.get('updated', 0)} yangilandi",
            "created": result.get("created", 0),
            "updated": result.get("updated", 0),
        }
    raise bad_request(f"«{draft.action_type}» amali qo'llab-quvvatlanmaydi.")


def decide_draft(
    db: Session,
    draft_id: str,
    *,
    approve: bool,
    actor: str,
    request_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    draft = db.get(DraftAction, draft_id)
    if draft is None:
        raise not_found("Taklif etilgan amal topilmadi.")
    if draft.status != "pending":
        raise bad_request("Bu amal bo'yicha qaror allaqachon qabul qilingan.")
    draft.decided_by = actor
    draft.decided_at = _now()
    if not approve:
        draft.status = "rejected"
        draft.result = {"note": note[:500]}
        write_audit(
            db,
            action="draft.rejected",
            entity_type="draft_action",
            entity_id=draft.id,
            actor_id=actor,
            new_value={"action_type": draft.action_type, "note": note[:200]},
            request_id=request_id,
        )
        db.commit()
        db.refresh(draft)
        return _draft_out(draft)
    try:
        result = _execute_draft(db, draft, actor, request_id)
        draft.status = "approved"
        draft.result = result
        draft.error = ""
    except Exception as error:
        db.rollback()
        draft = db.get(DraftAction, draft_id)
        if draft is None:
            raise not_found("Taklif etilgan amal topilmadi.") from error
        draft.status = "failed"
        draft.decided_by = actor
        draft.decided_at = _now()
        draft.error = _agent_error_message(error)
        db.commit()
        raise
    write_audit(
        db,
        action="draft.approved",
        entity_type="draft_action",
        entity_id=draft.id,
        actor_id=actor,
        new_value={"action_type": draft.action_type, "result": draft.result},
        request_id=request_id,
    )
    db.commit()
    db.refresh(draft)
    return _draft_out(draft)


def list_workflows(db: Session, limit: int = 50, status_filter: str | None = None) -> list[dict[str, Any]]:
    stmt = select(AgentWorkflow).order_by(AgentWorkflow.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(AgentWorkflow.status == status_filter)
    rows = db.execute(stmt).scalars().all()
    return [_workflow_out(db, row) for row in rows]


def get_workflow(db: Session, workflow_id: str) -> dict[str, Any]:
    workflow = db.get(AgentWorkflow, workflow_id)
    if workflow is None:
        raise not_found("Agent ish oqimi topilmadi.")
    return _workflow_out(db, workflow, include_runs=True)


def _workflow_out(db: Session, workflow: AgentWorkflow, include_runs: bool = False) -> dict[str, Any]:
    runs = db.execute(
        select(AgentRun).where(AgentRun.workflow_id == workflow.id).order_by(AgentRun.started_at)
    ).scalars().all()
    payload = {
        "id": workflow.id,
        "request_id": workflow.request_id,
        "conversation_id": workflow.conversation_id,
        "intent": workflow.intent,
        "status": workflow.status,
        "input": workflow.input or {},
        "result": workflow.result or {},
        "error": workflow.error,
        "requires_approval": workflow.requires_approval,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "runs": [],
    }
    if include_runs:
        payload["runs"] = [
            {
                "id": run.id,
                "workflow_id": run.workflow_id,
                "agent": run.agent,
                "task": run.task,
                "status": run.status,
                "input": run.input or {},
                "output": run.output or {},
                "sources": run.sources or [],
                "evidence_refs": run.evidence_refs or [],
                "warnings": run.warnings or [],
                "confidence": run.confidence,
                "proposed_actions": run.proposed_actions or [],
                "model": run.model,
                "provider": run.provider,
                "latency_ms": run.latency_ms,
                "token_input": run.token_input,
                "token_output": run.token_output,
                "error": run.error,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            for run in runs
        ]
    else:
        payload["runs"] = [
            {
                "id": run.id,
                "workflow_id": run.workflow_id,
                "agent": run.agent,
                "task": run.task,
                "status": run.status,
                "input": {},
                "output": {},
                "sources": run.sources or [],
                "evidence_refs": [],
                "warnings": run.warnings or [],
                "confidence": run.confidence,
                "proposed_actions": [],
                "model": run.model,
                "provider": run.provider,
                "latency_ms": run.latency_ms,
                "token_input": run.token_input,
                "token_output": run.token_output,
                "error": run.error,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
            for run in runs
        ]
    return payload


AGENT_DESCRIPTIONS = {
    "orchestrator": "So'rovni tahlil qiladi, tegishli agentni tanlaydi va javobni birlashtiradi.",
    "document": "Excel/CSV/Word hujjatlarini import qiladi, tekshiradi va eksport qiladi.",
    "reporting": "Kunlik, haftalik va oylik hisobotlarni ma'lumotlar bazasi asosida shakllantiradi.",
    "legislation": "Lex.uz dan amaldagi qonunchilikni yuklaydi va manbali javob beradi.",
    "credit_subsidy": "Kredit va subsidiya dasturlarini faqat tanlangan bank bo'yicha tushuntiradi.",
    "plan_control": "Murojaatlar, vazifalar, muddatlar va ish yozuvlarini nazorat qiladi.",
}


def agent_status(db: Session) -> dict[str, Any]:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    agents = []
    for name, label in AGENT_LABELS.items():
        last = db.execute(
            select(AgentRun).where(AgentRun.agent == name).order_by(AgentRun.started_at.desc()).limit(1)
        ).scalar_one_or_none()
        recent = db.execute(
            select(AgentRun).where(AgentRun.agent == name).order_by(AgentRun.started_at.desc()).limit(50)
        ).scalars().all()
        success = len([run for run in recent if run.status == "completed"])
        tokens_today = int(
            db.execute(
                select(func.coalesce(func.sum(AgentRun.token_input + AgentRun.token_output), 0)).where(
                    AgentRun.agent == name, AgentRun.started_at >= today_start
                )
            ).scalar_one()
        )
        agents.append(
            {
                "name": name,
                "label": label,
                "description": AGENT_DESCRIPTIONS.get(name, ""),
                "enabled": True,
                "provider": last.provider if last else "",
                "model": last.model if last else "",
                "last_run_at": last.started_at if last else None,
                "last_status": last.status if last else "idle",
                "latency_ms": last.latency_ms if last else 0,
                "tokens_today": tokens_today,
                "success_rate": round(success / len(recent) * 100, 1) if recent else 0.0,
                "fallback_used": False,
                "allowed_tools": [],
            }
        )
    usage = ai_gateway.usage_today(db)
    return {
        "agents": agents,
        "models": ai_gateway.available_models(),
        "budget": usage,
        "providers": ai_gateway.provider_status(),
    }
