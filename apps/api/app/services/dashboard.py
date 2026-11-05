from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.pagination import PageMeta, paginate
from app.core.time import minus_years, today_local
from app.models import AuditLog, Case, Citizen, Family, House, Mahalla, Street, Task
from app.services.serializers import case_out, task_out

# N-2: barcha audit amallari uchun insoniy o'zbekcha yorliq. Texnik kalit
# (`case.created`) foydalanuvchiga ko'rinmasligi kerak.
ACTION_LABELS: dict[str, str] = {
    "auth.login": "Tizimga kirdi",
    "auth.logout": "Tizimdan chiqdi",
    "auth.login_failed": "Muvaffaqiyatsiz kirish urinish",
    "citizen.created": "Yangi fuqaro qo'shildi",
    "citizen.updated": "Fuqaro ma'lumoti yangilandi",
    "citizen.archived": "Fuqaro arxivlandi",
    "case.created": "Yangi case ochildi",
    "case.updated": "Case holati yangilandi",
    "task.created": "Yangi vazifa yaratildi",
    "task.updated": "Vazifa yangilandi",
    "task.completed": "Vazifa bajarildi",
    "task.cancelled": "Vazifa bekor qilindi",
    "work_log.created": "Ish tarixi yozildi",
    "document.uploaded": "Hujjat yuklandi",
    "document.imported": "Import yakunlandi",
    "document.import_rolled_back": "Import qaytarildi",
    "document.analyzed": "Hujjat tahlil qilindi",
    "document.archived": "Hujjat arxivlandi",
    "report.generated": "Hisobot yaratildi",
    "report.approved": "Hisobot tasdiqlandi",
    "agent.chat": "AI so'rov bajarildi",
    "settings.updated": "Sozlamalar o'zgartirildi",
    "family.created": "Yangi oila qo'shildi",
    "family.updated": "Oila ma'lumoti yangilandi",
    "draft.approved": "Amal tasdiqlandi",
    "draft.rejected": "Amal rad etildi",
    "backup.created": "Zaxira nusxa yaratildi",
    "conversation.archived": "Suhbat arxivlandi",
    "conversation.deleted": "Suhbat o'chirildi",
    "job.completed": "Vazifa bajarildi",
    "legislation.checked": "Qonunchilik tekshirildi",
    "legislation.synced": "Qonunchilik yangilandi",
}

ACTION_TONES: dict[str, str] = {
    "created": "positive",
    "completed": "positive",
    "approved": "positive",
    "archived": "warning",
    "cancelled": "warning",
    "updated": "neutral",
    "login": "neutral",
    "failed": "warning",
}

# N-2: ustuvorlik tartibi — string bo'yicha emas, aniq tartibda.
PRIORITY_RANK = case(
    (Task.priority == "urgent", 4),
    (Task.priority == "high", 3),
    (Task.priority == "normal", 2),
    (Task.priority == "low", 1),
    else_=0,
)

# N-2: ehtiyoj matnlarini o'qish chegarasi (xotira xavfsizligi).
NEEDS_CHUNK_SIZE = 1000


def _action_title(action: str) -> str:
    """Audit amali uchun insoniy sarlavha."""
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    return action.replace(".", " ").capitalize()


def _incomplete_condition():
    """To'liq emas deb hisoblanadigan fuqarolar sharti (N-2).

    `phone == ""` faqat bo'sh satrni aniqlaydi — `NULL` telefon ham bo'sh
    hisoblanadi.
    """
    return or_(
        Citizen.phone == "",
        Citizen.phone.is_(None),
        Citizen.birth_date.is_(None),
        Citizen.family_id.is_(None),
    )


def _citizen_base():
    return select(Citizen).where(Citizen.archived_at.is_(None))


def summary(db: Session) -> dict:
    today = today_local()
    # N-1: metrikalar 14+ alohida COUNT so'rovi emas, 3 ta agregatsiya
    # so'rovi (fuqaro / tuzilma / operatsiya) orqali olinadi.
    youth_cutoff = minus_years(today, 30)
    updated_since = datetime.now(timezone.utc) - timedelta(days=1)

    citizen_row = db.execute(
        select(
            func.count().label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (Citizen.employment_status.in_(["Ishlaydi", "Tadbirkor", "Pensioner"]), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("employed"),
            func.coalesce(
                func.sum(case((Citizen.employment_status == "Ishsiz", 1), else_=0)), 0
            ).label("unemployed"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Citizen.birth_date.is_not(None),
                                Citizen.birth_date > youth_cutoff,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("youth"),
            func.coalesce(
                func.sum(case((Citizen.social_status != "Yo'q", 1), else_=0)), 0
            ).label("social"),
            func.coalesce(
                func.sum(case((_incomplete_condition(), 1), else_=0)), 0
            ).label("incomplete"),
            func.coalesce(
                func.sum(case((Citizen.updated_at >= updated_since, 1), else_=0)), 0
            ).label("updated_today"),
            select(func.max(Citizen.updated_at)).scalar_subquery().label("last_sync"),
        )
        .select_from(Citizen)
        .where(Citizen.archived_at.is_(None))
    ).one()

    structure_row = db.execute(
        select(
            select(func.count()).select_from(Family).scalar_subquery().label("families"),
            select(func.count()).select_from(House).scalar_subquery().label("houses"),
            select(func.count()).select_from(Street).scalar_subquery().label("streets"),
            select(func.count()).select_from(Mahalla).scalar_subquery().label("mahallas"),
        )
    ).one()

    ops_row = db.execute(
        select(
            select(func.count())
            .select_from(Case)
            .where(Case.status.notin_(["closed", "cancelled"]))
            .scalar_subquery()
            .label("open_cases"),
            select(func.count())
            .select_from(Task)
            .where(Task.due_date == today, Task.status.notin_(["completed", "cancelled"]))
            .scalar_subquery()
            .label("today_tasks"),
            select(func.count())
            .select_from(Task)
            .where(Task.status == "completed")
            .scalar_subquery()
            .label("completed_tasks"),
            select(func.count())
            .select_from(Task)
            .where(Task.due_date < today, Task.status.notin_(["completed", "cancelled"]))
            .scalar_subquery()
            .label("overdue_tasks"),
        )
    ).one()

    total_citizens = int(citizen_row.total)
    total_families = int(structure_row.families)
    total_houses = int(structure_row.houses)
    total_streets = int(structure_row.streets)
    total_mahallas = int(structure_row.mahallas)
    employed = int(citizen_row.employed)
    unemployed = int(citizen_row.unemployed)
    youth = int(citizen_row.youth)
    social_categories = int(citizen_row.social)
    open_cases = int(ops_row.open_cases)
    today_tasks = int(ops_row.today_tasks)
    completed_tasks = int(ops_row.completed_tasks)
    overdue_tasks = int(ops_row.overdue_tasks)

    metrics = [
        {"key": "citizens", "label": "Jami fuqarolar", "value": total_citizens, "hint": "Faol yozuvlar"},
        {"key": "families", "label": "Jami oilalar", "value": total_families, "hint": f"{total_houses} uy"},
        {"key": "houses", "label": "Jami uylar", "value": total_houses, "hint": f"{total_streets} ko'cha"},
        {"key": "streets", "label": "Ko'chalar", "value": total_streets, "hint": f"{total_mahallas} mahalla"},
        {"key": "employed", "label": "Bandlar", "value": employed, "hint": "Ishlaydi, tadbirkor, pensioner"},
        {"key": "unemployed", "label": "Ishsizlar", "value": unemployed, "hint": "Bandlik ustida ishlash kerak"},
        {"key": "youth", "label": "30 yoshgacha", "value": youth, "hint": "Yoshlar auditi"},
        {"key": "social", "label": "Ijtimoiy toifalar", "value": social_categories, "hint": "Daftarlar va nafaqalar"},
        {"key": "open_cases", "label": "Ochiq case'lar", "value": open_cases, "hint": "Nazoratda"},
        {"key": "today_tasks", "label": "Bugungi vazifalar", "value": today_tasks, "hint": "Bugungi muddat"},
        {"key": "completed_tasks", "label": "Bajarilgan vazifalar", "value": completed_tasks, "hint": "Dalil bilan"},
        {"key": "overdue_tasks", "label": "Kechikkan vazifalar", "value": overdue_tasks, "hint": "Muddat o'tgan"},
    ]

    employment = _distribution(db, Citizen.employment_status, total=total_citizens)
    social = _distribution(db, Citizen.social_status, total=total_citizens)
    education = _distribution(db, Citizen.education, total=total_citizens)
    needs = _needs_distribution(db)
    streets = _street_rows(db)

    today_rows = db.execute(
        select(Task)
        .options(joinedload(Task.citizen))
        .where(Task.due_date == today, Task.status.notin_(["completed", "cancelled"]))
        .order_by(PRIORITY_RANK.desc(), Task.due_date.asc())
        .limit(8)
    ).scalars().all()
    overdue_rows = db.execute(
        select(Task)
        .options(joinedload(Task.citizen))
        .where(Task.due_date < today, Task.status.notin_(["completed", "cancelled"]))
        .order_by(Task.due_date.asc())
        .limit(8)
    ).scalars().all()
    case_rows = db.execute(
        select(Case)
        .options(joinedload(Case.citizen))
        .where(Case.status.notin_(["closed", "cancelled"]))
        .order_by(Case.opened_at.desc())
        .limit(6)
    ).scalars().all()
    activity = recent_activity(db, limit=10)

    incomplete = int(citizen_row.incomplete)
    # N-2: raqam va ulush mos kelishi uchun arxivlanganlar chiqariladi.
    updated_today = int(citizen_row.updated_today)
    data_quality = {
        "complete": total_citizens - incomplete,
        "incomplete": incomplete,
        "score": round((total_citizens - incomplete) / total_citizens * 100) if total_citizens else 0,
        "updated_today": updated_today,
        "last_sync": citizen_row.last_sync,
    }

    return {
        "metrics": metrics,
        "employment": employment,
        "social": social,
        "education": education,
        "needs": needs,
        "streets": streets,
        "today_tasks": [task_out(row) for row in today_rows],
        "overdue_tasks": [task_out(row) for row in overdue_rows],
        "open_cases": [case_out(row) for row in case_rows],
        "recent_activity": activity,
        "data_quality": data_quality,
        "as_of": datetime.now(timezone.utc),
        "timezone": "Asia/Tashkent",
    }


def _distribution(db: Session, column, limit: int = 12, total: int | None = None) -> list[dict]:
    """Taqsimot (N-2): foiz haqiqiy jami fuqaro bo'yicha hisoblanadi.

    Eski kodda `total` faqat **top-12** qatorlar yig'indisi edi — foizlar
    100% ga yetmasdi va ko'rsatkich boshqa qiymat bilan kelishardi.

    N-1: jami (`total`) tashqaridan berilsa — qo'shimcha COUNT so'rovi
    bajarilmaydi.
    """
    rows = db.execute(
        select(column, func.count())
        .select_from(Citizen)
        .where(Citizen.archived_at.is_(None))
        .group_by(column)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    if total is None:
        total = int(
            db.execute(
                select(func.count()).select_from(Citizen).where(Citizen.archived_at.is_(None))
            ).scalar_one()
        )
    total = int(total) or 1
    return [
        {
            "label": row[0] or "Ko'rsatilmagan",
            "value": int(row[1]),
            "percent": round(int(row[1]) / total * 100, 1),
        }
        for row in rows
    ]


def _iter_needs_text(db: Session, chunk_size: int = NEEDS_CHUNK_SIZE):
    """`needs_text` matnlarini bo'laklab o'qish (N-2).

    Butun matnlar bir vaqtda yuklanmasligi kerak — katta bazada bu xotira
    (OOM) xavfini tug'diradi. Kalit bo'yicha (keyset) sahifalanish
    `OFFSET` dan tez va barqaror ishlaydi.
    """
    last_id = ""
    while True:
        rows = db.execute(
            select(Citizen.id, Citizen.needs_text)
            .where(
                Citizen.archived_at.is_(None),
                Citizen.needs_text != "",
                Citizen.id > last_id,
            )
            .order_by(Citizen.id)
            .limit(chunk_size)
        ).all()
        if not rows:
            return
        yield [row[1] for row in rows]
        if len(rows) < chunk_size:
            return
        last_id = rows[-1][0]


def _needs_distribution(db: Session) -> list[dict]:
    counts: dict[str, int] = {}
    for chunk in _iter_needs_text(db):
        for text in chunk:
            for item in str(text).split(","):
                item = item.strip()
                if item:
                    counts[item] = counts.get(item, 0) + 1
    total = sum(counts.values()) or 1
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
    return [
        {"label": label, "value": value, "percent": round(value / total * 100, 1)}
        for label, value in ordered
    ]


def _street_rows(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            Street.id,
            Street.name,
            func.count(func.distinct(House.id)),
            func.count(func.distinct(Citizen.id)),
        )
        .select_from(Street)
        .outerjoin(House, House.street_id == Street.id)
        .outerjoin(Family, Family.house_id == House.id)
        .outerjoin(Citizen, (Citizen.family_id == Family.id) & (Citizen.archived_at.is_(None)))
        .group_by(Street.id, Street.name)
        .order_by(Street.name)
    ).all()
    return [
        {
            "id": row[0],
            "label": row[1],
            "houses": int(row[2]),
            "citizens": int(row[3]),
        }
        for row in rows
    ]


def recent_activity(db: Session, limit: int = 20) -> list[dict]:
    rows = db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ).scalars().all()
    items = []
    for row in rows:
        tone = "neutral"
        for key, value in ACTION_TONES.items():
            if key in row.action:
                tone = value
                break
        items.append(
            {
                "id": row.id,
                "action": row.action,
                "title": _action_title(row.action),
                "description": _audit_description(row),
                "actor": "Administrator" if row.actor_type == "user" else row.actor_type,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "created_at": row.created_at,
                "tone": tone,
            }
        )
    return items


def _audit_description(row: AuditLog) -> str:
    value = row.new_value or row.old_value or {}
    for key in ("title", "full_name", "username", "filename", "name", "key"):
        if isinstance(value, dict) and value.get(key):
            return str(value[key])[:160]
    if isinstance(value, dict) and value.get("status"):
        return f"Holat: {value['status']}"
    return ""


def activity_page(db: Session, page: int, page_size: int) -> tuple[list[dict], PageMeta]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    rows, meta = paginate(db, stmt, page, page_size)
    items = []
    for row in rows:
        tone = "neutral"
        for key, value in ACTION_TONES.items():
            if key in row.action:
                tone = value
                break
        items.append(
            {
                "id": row.id,
                "action": row.action,
                "title": _action_title(row.action),
                "description": _audit_description(row),
                "actor": "Administrator" if row.actor_type == "user" else row.actor_type,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "created_at": row.created_at,
                "tone": tone,
            }
        )
    return items, meta


def dashboard_tasks(db: Session) -> dict:
    today = today_local()
    statuses = ["new", "in_progress", "waiting"]
    today_rows = db.execute(
        select(Task).options(joinedload(Task.citizen)).where(
            Task.due_date == today, Task.status.in_(statuses)
        ).order_by(PRIORITY_RANK.desc(), Task.due_date.asc())
    ).scalars().all()
    overdue_rows = db.execute(
        select(Task).options(joinedload(Task.citizen)).where(
            Task.due_date < today, Task.status.in_(statuses)
        ).order_by(Task.due_date.asc())
    ).scalars().all()
    week_rows = db.execute(
        select(Task).options(joinedload(Task.citizen)).where(
            Task.due_date >= today,
            Task.due_date <= today + timedelta(days=7),
            Task.status.in_(statuses),
        ).order_by(Task.due_date.asc())
    ).scalars().all()
    return {
        "today": [task_out(row) for row in today_rows],
        "overdue": [task_out(row) for row in overdue_rows],
        "week": [task_out(row) for row in week_rows],
        "as_of": datetime.now(timezone.utc),
    }
