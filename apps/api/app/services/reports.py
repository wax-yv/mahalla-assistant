from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import model_snapshot, write_audit
from app.core.downloads import safe_cell, safe_filename_part
from app.core.errors import forbidden, not_found, validation_error
from app.core.pagination import paginate
from app.core.time import minus_years, period_bounds, today_local
from app.models import Case, Citizen, Family, House, Report, ReportRun, Street, Task, User, WorkLog
from app.schemas import ReportGenerateRequest
from app.services import ai_gateway

TYPE_LABELS = {
    "daily": "Kunlik ishlar hisoboti",
    "weekly": "Haftalik hisobot",
    "monthly": "Oylik faoliyat hisoboti",
    "employment": "Bandlik hisoboti",
    "unemployed": "Ishsizlar hisoboti",
    "education": "Ta'lim hisoboti",
    "social": "Ijtimoiy toifalar hisoboti",
    "needs": "Ehtiyojlar hisoboti",
    "territory": "Hudud kesimidagi hisobot",
    "cases": "Murojaatlar hisoboti",
    "tasks": "Vazifalar hisoboti",
    "overdue": "Kechikkan vazifalar hisoboti",
    "data_quality": "Ma'lumot sifati hisoboti",
}

# O-17: ruxsat etilgan hisobot eksport formatlari.
REPORT_EXPORT_FORMATS: frozenset[str] = frozenset({"xlsx", "docx", "pdf"})


def _distribution(
    db: Session, column, limit: int = 20, base: list | None = None
) -> list[dict]:
    """Taqsimot (N-3): agregatsiya SQL da, filtrlar qo'llaniladi."""
    conditions = list(base) if base else [Citizen.archived_at.is_(None)]
    rows = db.execute(
        select(column, func.count())
        .select_from(Citizen)
        .where(*conditions)
        .group_by(column)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [{"label": row[0] or "Ko'rsatilmagan", "value": int(row[1])} for row in rows]


def _needs(db: Session, base: list | None = None) -> list[dict]:
    """Ehtiyojlar taqsimoti (N-3): filtrlar qo'llaniladi."""
    conditions = list(base) if base else [Citizen.archived_at.is_(None)]
    texts = db.execute(
        select(Citizen.needs_text).where(*conditions, Citizen.needs_text != "")
    ).scalars().all()
    counts: dict[str, int] = {}
    for text in texts:
        for item in str(text).split(","):
            item = item.strip()
            if item:
                counts[item] = counts.get(item, 0) + 1
    return [
        {"label": label, "value": value}
        for label, value in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
    ]


def _status_counts(db: Session, model, *conditions) -> dict[str, int]:
    """Holatlar soni — SQL `GROUP BY` agregatsiyasi (N-3).

    Eski kod butun obyektlarni Python'ga yuklab hisoblardi (`scalars().all()`)
    — katta davrda sekin va xotira yeydi. Endi agregatsiya bazada bajariladi.
    """
    rows = db.execute(
        select(model.status, func.count()).where(*conditions).group_by(model.status)
    ).all()
    return {str(row[0]): int(row[1]) for row in rows}


def _incomplete_condition():
    """To'liq emas deb hisoblanadigan fuqarolar sharti (N-3).

    `phone == ""` faqat bo'sh satrni aniqlaydi — `NULL` telefon ham bo'sh
    hisoblanadi.
    """
    return or_(
        Citizen.phone == "",
        Citizen.phone.is_(None),
        Citizen.birth_date.is_(None),
        Citizen.family_id.is_(None),
    )


def _scoped_totals(db: Session, base: list) -> dict[str, int]:
    """Filtrga mos oilalar / uylar / ko'chalar soni (N-3).

    Oila — kamida bitta mos fuqarosi bor oila; uy — o'sha oilalardan kamida
    bittasi bor uy; ko'cha — o'sha uylardan kamida bittasi bor ko'cha.
    """
    family_ids = (
        select(Family.id)
        .join(Citizen, Citizen.family_id == Family.id)
        .where(*base)
        .group_by(Family.id)
    )
    families = int(
        db.execute(select(func.count()).select_from(family_ids.subquery())).scalar_one()
    )
    house_ids = (
        select(House.id)
        .join(Family, Family.house_id == House.id)
        .where(Family.id.in_(family_ids.scalar_subquery()))
    )
    houses = int(
        db.execute(select(func.count()).select_from(house_ids.subquery())).scalar_one()
    )
    street_ids = (
        select(Street.id)
        .join(House, House.street_id == Street.id)
        .where(House.id.in_(house_ids.scalar_subquery()))
    )
    streets = int(
        db.execute(select(func.count()).select_from(street_ids.subquery())).scalar_one()
    )
    return {"families": families, "houses": houses, "streets": streets}


def compute_metrics(
    db: Session, report_type: str, period_start: date, period_end: date, filters: dict[str, Any]
) -> dict[str, Any]:
    today = today_local()
    base = [Citizen.archived_at.is_(None)]
    if filters.get("street_id"):
        base.append(Citizen.family.has(Family.house.has(House.street_id == filters["street_id"])))
    if filters.get("employment_status"):
        base.append(Citizen.employment_status == filters["employment_status"])
    if filters.get("social_status"):
        base.append(Citizen.social_status == filters["social_status"])
    # N-3: filtr qo'llangan bo'lsa — oilalar/uylar/ko'chalar ham filtrga
    # moslashtiriladi. Filtrsiz hisobotda global hisob saqlanadi.
    filtered = len(base) > 1

    total_citizens = int(db.execute(select(func.count()).select_from(Citizen).where(*base)).scalar_one())
    if filtered:
        scoped = _scoped_totals(db, base)
    else:
        scoped = {
            "families": int(
                db.execute(
                    select(func.count())
                    .select_from(Family)
                    .where(Family.members.any(Citizen.archived_at.is_(None)))
                ).scalar_one()
            ),
            "houses": int(db.execute(select(func.count()).select_from(House)).scalar_one()),
            "streets": int(db.execute(select(func.count()).select_from(Street)).scalar_one()),
        }
    total_families = scoped["families"]
    total_houses = scoped["houses"]
    total_streets = scoped["streets"]

    def count_citizens(*conditions) -> int:
        return int(db.execute(select(func.count()).select_from(Citizen).where(*base, *conditions)).scalar_one())

    employed = count_citizens(Citizen.employment_status.in_(["Ishlaydi", "Tadbirkor", "Pensioner"]))
    unemployed = count_citizens(Citizen.employment_status == "Ishsiz")
    youth = count_citizens(
        Citizen.birth_date.is_not(None), Citizen.birth_date > minus_years(today, 30)
    )
    social = count_citizens(Citizen.social_status != "Yo'q")
    start_dt = datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, datetime.max.time(), tzinfo=timezone.utc)
    # N-3: holatlar soni SQL `GROUP BY` agregatsiyasi bilan (Python'da
    # butun obyektlarni yuklash o'rniga).
    case_by_status = _status_counts(
        db, Case, Case.opened_at >= start_dt, Case.opened_at <= end_dt
    )
    cases_total = sum(case_by_status.values())
    cases_open = sum(
        value for status, value in case_by_status.items() if status not in {"closed", "cancelled"}
    )
    task_by_status = _status_counts(
        db, Task, Task.created_at >= start_dt, Task.created_at <= end_dt
    )
    tasks_total = sum(task_by_status.values())
    completed = task_by_status.get("completed", 0)
    # N-3: kechikkan vazifalar faqat **hisobot davri** ichida sanaladi.
    overdue = int(
        db.execute(
            select(func.count()).select_from(Task).where(
                Task.due_date >= period_start,
                Task.due_date <= period_end,
                Task.due_date < today,
                Task.status.notin_(["completed", "cancelled"]),
            )
        ).scalar_one()
    )
    logs = int(
        db.execute(
            select(func.count()).select_from(WorkLog).where(
                WorkLog.occurred_at >= start_dt, WorkLog.occurred_at <= end_dt
            )
        ).scalar_one()
    )
    incomplete = count_citizens(_incomplete_condition())
    # N-3: hudud kesimi `Street.id` bo'yicha guruhlanadi (bir nomli ikki
    # ko'cha birlashtirilmaydi) va filtrlarga mos bo'ladi.
    citizen_conditions = [Citizen.archived_at.is_(None)]
    if filters.get("employment_status"):
        citizen_conditions.append(Citizen.employment_status == filters["employment_status"])
    if filters.get("social_status"):
        citizen_conditions.append(Citizen.social_status == filters["social_status"])
    street_stmt = (
        select(Street.id, Street.name, func.count(func.distinct(Citizen.id)))
        .select_from(Street)
        .outerjoin(House, House.street_id == Street.id)
        .outerjoin(Family, Family.house_id == House.id)
        .outerjoin(Citizen, and_(Citizen.family_id == Family.id, *citizen_conditions))
        .group_by(Street.id, Street.name)
        .order_by(Street.name)
    )
    if filters.get("street_id"):
        street_stmt = street_stmt.where(Street.id == filters["street_id"])
    street_rows = db.execute(street_stmt).all()
    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "filters": filters,
        "totals": {"citizens": total_citizens, "families": total_families, "houses": total_houses, "streets": total_streets},
        "employment": {
            "employed": employed,
            "unemployed": unemployed,
            "employment_rate": round(employed / total_citizens * 100, 1) if total_citizens else 0,
            "distribution": _distribution(db, Citizen.employment_status, base=base),
        },
        "demographics": {
            "youth_under_30": youth,
            "social_categories": social,
            "education": _distribution(db, Citizen.education, base=base),
        },
        "social": _distribution(db, Citizen.social_status, base=base),
        "needs": _needs(db, base=base),
        "cases": {
            "total": cases_total,
            "by_status": case_by_status,
            "open": cases_open,
        },
        "tasks": {
            "total": tasks_total,
            "by_status": task_by_status,
            "completed": completed,
            "overdue": overdue,
            "completion_rate": round(completed / tasks_total * 100, 1) if tasks_total else 0,
        },
        "work_logs": logs,
        "data_quality": {
            "incomplete": incomplete,
            "score": round((total_citizens - incomplete) / total_citizens * 100, 1) if total_citizens else 0,
        },
        "territory": [
            {"street_id": row[0], "street": row[1], "citizens": int(row[2])}
            for row in street_rows
        ],
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "calculation_note": "Barcha ko'rsatkichlar SQL so'rovlari orqali database'dan hisoblandi.",
    }


SYSTEM_PROMPT = """Siz O'zbekiston mahalla tizimi uchun rasmiy hisobot muharririsiniz.
Faqat o'zbek lotin tilida yozing. Berilgan raqamlardan boshqa raqam uydirmang.
Raqamlarni o'zgartirmang, qo'shmang, ayirmang. Har bir xulosa berilgan metrikaga tayanishi kerak.
Matn: qisqa kirish, asosiy ko'rsatkichlar tahlili, aniqlangan muammolar va amaliy tavsiyalar.
4-6 paragrafdan oshmasin. Markdown sarlavhalar ishlatmang, oddiy matn yozing.
Agar ma'lumot yetishmasa "ma'lumot mavjud emas" deb yozing. Rasmiy qaror vakolatini da'vo qilmang."""


def _fallback_narrative(report_type: str, metrics: dict[str, Any]) -> str:
    """Deterministik xulosa — har doim metrikaga asoslanadi (O-13).

    Kalitlar bo'lmasa ham xato bermaydi (`0` bilan to'ldiriladi) — hisobot
    so'rovi 500 bilan uzilmasligi kerak.
    """
    totals = metrics.get("totals") or {}
    employment = metrics.get("employment") or {}
    tasks = metrics.get("tasks") or {}
    cases = metrics.get("cases") or {}
    quality = metrics.get("data_quality") or {}
    period = metrics.get("period") or {}
    return "\n\n".join(
        [
            f"{TYPE_LABELS.get(report_type, 'Hisobot')} {period.get('start', '')} — {period.get('end', '')} davri uchun shakllantirildi.",
            f"Hisobot davrida {totals.get('citizens', 0)} nafar fuqaro, {totals.get('families', 0)} ta oila, {totals.get('houses', 0)} ta uy va {totals.get('streets', 0)} ta ko'cha hisobga olindi.",
            f"Bandlik bo'yicha {employment.get('employed', 0)} nafar fuqaro band, {employment.get('unemployed', 0)} nafar fuqaro ishsiz. Bandlik darajasi {employment.get('employment_rate', 0)} foizni tashkil etdi.",
            f"Davr ichida {cases.get('total', 0)} ta murojaat qayd etildi, ulardan {cases.get('open', 0)} tasi hali yopilmagan. Vazifalar bo'yicha jami {tasks.get('total', 0)} ta yozuv mavjud, {tasks.get('completed', 0)} tasi bajarilgan, {tasks.get('overdue', 0)} tasi muddatidan oshgan.",
            f"Ma'lumotlar sifati ko'rsatkichi {quality.get('score', 0)} foiz. {quality.get('incomplete', 0)} nafar fuqaro yozuvida to'ldirilmagan maydonlar mavjud.",
            "Ushbu hisobot draft holatida. Rasmiy tasdiqlashdan oldin mas'ul xodim tomonidan tekshirilishi shart.",
        ]
    )


# O-13: prompt uchun metriklar JSON'i — zich, kesilmaydigan.
METRICS_PROMPT_LIMIT = 12000
# O-13: matndagi sonlarni topish uchun andoza.
NUMBER_RE = re.compile(r"\d[\d\s., ]*")


def _metrics_payload(metrics: dict[str, Any]) -> str | None:
    """Metriklarni zich JSON ko'rinishida beradi (O-13).

    Eski kod `json.dumps(..., indent=2)[:12000]` ishlatardi — JSON o'rtasidan
    kesilib, model buzuq kirish olardi. Endi JSON kompakt yig'iladi va
    hajm chegaradan oshsa `None` qaytariladi (AI chaqirilmaydi).
    """
    payload = json.dumps(metrics, ensure_ascii=False, separators=(",", ":"))
    if len(payload) > METRICS_PROMPT_LIMIT:
        return None
    return payload


def _to_number(raw: str) -> float | None:
    """Matndagi son qiymatini float'ga aylantiradi (`1 258`, `1,258`, `62,5%`)."""
    cleaned = re.sub(r"[\s ]", "", raw or "").rstrip(".")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        # "1,234.56" — minglik ajratgich + kasr
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        head, _, tail = cleaned.rpartition(",")
        if cleaned.count(",") == 1 and tail.isdigit() and len(tail) == 3 and len(head) <= 3:
            # "1,258" — minglik ajratgich
            cleaned = cleaned.replace(",", "")
        else:
            # "62,5" — kasrli yozuv
            cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _metric_numbers(metrics: Any) -> set[float]:
    """Metrik ichidagi barcha sonlar (o'z ichiga qaragan holda)."""
    found: set[float] = set()
    if isinstance(metrics, bool):
        return found
    if isinstance(metrics, (int, float)):
        found.add(float(metrics))
        return found
    if isinstance(metrics, str):
        for raw in NUMBER_RE.findall(metrics):
            value = _to_number(raw)
            if value is not None:
                found.add(value)
        return found
    if isinstance(metrics, dict):
        for item in metrics.values():
            found |= _metric_numbers(item)
        return found
    if isinstance(metrics, (list, tuple)):
        for item in metrics:
            found |= _metric_numbers(item)
    return found


def _has_unknown_number(text: str, metrics: dict[str, Any]) -> bool:
    """Matnda metrikaga tegilmagan son bormi? (O-13)

    `True` — uydirilgan son topildi (matn qabul qilinmasligi kerak).
    """
    allowed = _metric_numbers(metrics)
    for raw in NUMBER_RE.findall(text or ""):
        value = _to_number(raw)
        if value is None:
            continue
        if any(abs(value - item) <= 0.01 for item in allowed):
            continue
        return True
    return False


def generate_report(
    db: Session,
    payload: ReportGenerateRequest,
    *,
    actor: str,
    request_id: str | None = None,
    use_ai: bool = True,
    commit: bool = True,
) -> Report:
    if payload.type not in TYPE_LABELS:
        raise validation_error("Hisobot turi qo'llab-quvvatlanmaydi.")
    default_start, default_end = period_bounds(payload.type, payload.period_end or today_local())
    start = payload.period_start or default_start
    end = payload.period_end or default_end
    if start > end:
        raise validation_error("Davr boshlanishi tugash sanasidan katta bo'lmasligi kerak.")
    metrics = compute_metrics(db, payload.type, start, end, payload.filters or {})
    title = f"{TYPE_LABELS[payload.type]}: {start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}"
    report = Report(
        type=payload.type,
        period_start=start,
        period_end=end,
        filters=payload.filters or {},
        status="draft",
        title=title,
        summary="",
        metrics=metrics,
        narrative="",
        sources=[{"type": "database", "label": "Mahalla Assistant PostgreSQL", "note": "Ko'rsatkichlar SQL orqali hisoblandi"}],
        created_by=actor,
    )
    db.add(report)
    db.flush()
    run = ReportRun(report_id=report.id, status="running")
    db.add(run)
    db.flush()
    narrative, model, provider = "", "", ""
    verified = False
    metrics_payload = _metrics_payload(metrics) if use_ai else None
    if use_ai and metrics_payload is None:
        # O-13: metrikalar prompt chegarasidan oshdi — modelga buzuq JSON
        # berish o'rniga deterministik xulosa ishlatiladi.
        run.status = "fallback"
        run.error = "Metrikalar hajmi prompt chegarasidan oshdi."
        narrative = _fallback_narrative(payload.type, metrics)
        model, provider = "deterministic-fallback", "local"
    elif use_ai:
        try:
            result = ai_gateway.chat_completion(
                db,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": "Quyidagi tasdiqlangan metrikalar asosida hisobot matnini yoz. Faqat shu raqamlardan foydalan.\n\n"
                        + metrics_payload,
                    },
                ],
                agent="reporting",
                max_tokens=1400,
                temperature=0.2,
            )
            candidate = result.content.strip()
            # O-13: model yozgan sonlar metrikaga mos kelishi shart —
            # aks holda deterministik xulosaga qaytamiz.
            if _has_unknown_number(candidate, metrics):
                run.status = "fallback"
                run.error = "Model matnida metrikaga tegilmagan son topildi."
                narrative = _fallback_narrative(payload.type, metrics)
                model, provider = "deterministic-fallback", "local"
            else:
                narrative = candidate
                model, provider = result.model, result.provider
                verified = True
                run.status = "completed"
                run.token_usage = result.total_tokens
                run.model = result.model
        except Exception as error:
            run.status = "fallback"
            run.error = str(error)[:500]
            narrative = _fallback_narrative(payload.type, metrics)
            model, provider = "deterministic-fallback", "local"
    else:
        narrative = _fallback_narrative(payload.type, metrics)
        run.status = "completed"
        model, provider = "deterministic", "local"
    run.finished_at = datetime.now(timezone.utc)
    report.narrative = narrative
    report.summary = narrative.split("\n\n")[0][:500]
    report.metrics = {
        **metrics,
        "ai": {"model": model, "provider": provider, "verified": verified},
    }
    db.flush()
    write_audit(
        db,
        action="report.generated",
        entity_type="report",
        entity_id=report.id,
        actor_id=actor,
        new_value={"type": payload.type, "period": [start.isoformat(), end.isoformat()], "model": model},
        request_id=request_id,
    )
    if commit:
        db.commit()
        db.refresh(report)
    return report


def list_reports(db: Session, *, type: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20):
    stmt = select(Report).order_by(Report.created_at.desc())
    if type:
        stmt = stmt.where(Report.type == type)
    if status:
        stmt = stmt.where(Report.status == status)
    return paginate(db, stmt, page, page_size)


def get_report(db: Session, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise not_found("Hisobot topilmadi.")
    return report


def approve_report(db: Session, report_id: str, actor: str, note: str = "", request_id: str | None = None) -> Report:
    report = get_report(db, report_id)
    if report.status == "approved":
        return report
    # O-16: "segregation of duties" — muallif o'z hisobotini tasdiqlay
    # olmaydi. Administrator — tizimda yakuniy mas'ul shaxs — o'z
    # hisobotini tasdiqlashi mumkin.
    if report.created_by and report.created_by == actor:
        approver = db.get(User, actor)
        if approver is None or approver.role != "admin":
            raise forbidden(
                "Hisobotni tasdiqlash uchun boshqa mas'ul xodim kerak: "
                "muallif o'z hisobotini tasdiqlay olmaydi."
            )
    before = model_snapshot(report)
    report.status = "approved"
    report.approved_by = actor
    report.approved_at = datetime.now(timezone.utc)
    if note:
        report.narrative = f"{report.narrative}\n\nTasdiqlash izohi: {note}"
    db.flush()
    write_audit(
        db,
        action="report.approved",
        entity_type="report",
        entity_id=report.id,
        actor_id=actor,
        old_value=before,
        new_value=model_snapshot(report),
        request_id=request_id,
    )
    db.commit()
    db.refresh(report)
    return report


def _report_rows(report: Report) -> list[tuple[str, list[tuple[str, Any]]]]:
    metrics = report.metrics or {}
    totals = metrics.get("totals", {})
    employment = metrics.get("employment", {})
    tasks = metrics.get("tasks", {})
    cases = metrics.get("cases", {})
    quality = metrics.get("data_quality", {})
    demographics = metrics.get("demographics", {})
    rows = [
        ("Umumiy ko'rsatkichlar", [
            ("Fuqarolar", totals.get("citizens", 0)),
            ("Oilalar", totals.get("families", 0)),
            ("Uylar", totals.get("houses", 0)),
            ("Ko'chalar", totals.get("streets", 0)),
        ]),
        ("Bandlik", [
            ("Bandlar", employment.get("employed", 0)),
            ("Ishsizlar", employment.get("unemployed", 0)),
            ("Bandlik darajasi", f"{employment.get('employment_rate', 0)}%"),
        ]),
        ("Ijtimoiy ko'rsatkichlar", [
            ("30 yoshgacha", demographics.get("youth_under_30", 0)),
            ("Ijtimoiy toifalar", demographics.get("social_categories", 0)),
            ("Ma'lumot sifati", f"{quality.get('score', 0)}%"),
            ("To'liq bo'lmagan yozuvlar", quality.get("incomplete", 0)),
        ]),
        ("Vazifalar va murojaatlar", [
            ("Murojaatlar", cases.get("total", 0)),
            ("Ochiq murojaatlar", cases.get("open", 0)),
            ("Vazifalar", tasks.get("total", 0)),
            ("Bajarilgan", tasks.get("completed", 0)),
            ("Kechikkan", tasks.get("overdue", 0)),
            ("Bajarilish darajasi", f"{tasks.get('completion_rate', 0)}%"),
        ]),
    ]
    if metrics.get("territory"):
        rows.append(("Hudud kesimi", [(item["street"], f"{item['citizens']} fuqaro") for item in metrics["territory"]]))
    return rows


def export_report(db: Session, report_id: str, fmt: str) -> tuple[bytes, str, str]:
    import io

    # O-17: format oldindan tekshiriladi — noma'lum formatda aniq xato.
    if fmt not in REPORT_EXPORT_FORMATS:
        raise validation_error(
            "Format qo'llab-quvvatlanmaydi. Ruxsat etilgan formatlar: "
            + ", ".join(sorted(REPORT_EXPORT_FORMATS))
            + "."
        )
    report = get_report(db, report_id)
    stamp = report.period_end.strftime("%Y%m%d")
    # O-17: hisobot turi fayl nomiga xavfsiz tarzda o'tadi.
    base = f"hisobot-{safe_filename_part(report.type, fallback='hisobot')}-{stamp}"
    rows = _report_rows(report)
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Hisobot"
        # O-15: har bir yozuv formula inyeksiyasidan himoyalangan holda
        # yoziladi (`=` bilan boshlanuvchi matn formula bo'lib ketmasin).
        sheet["A1"] = safe_cell(report.title)
        sheet["A1"].font = Font(size=14, bold=True, color="1F3D2E")
        sheet["A2"] = safe_cell(
            f"Holat: {report.status} · Davr: {report.period_start} — {report.period_end}"
        )
        row_index = 4
        for section, values in rows:
            cell = sheet.cell(row=row_index, column=1, value=safe_cell(section))
            cell.font = Font(bold=True, color="F7F3E8")
            cell.fill = PatternFill("solid", fgColor="1F3D2E")
            sheet.cell(row=row_index, column=2).fill = PatternFill("solid", fgColor="1F3D2E")
            row_index += 1
            for label, value in values:
                sheet.cell(row=row_index, column=1, value=safe_cell(label))
                sheet.cell(row=row_index, column=2, value=safe_cell(value))
                row_index += 1
            row_index += 1
        sheet.column_dimensions["A"].width = 42
        sheet.column_dimensions["B"].width = 60
        narrative_row = row_index + 1
        sheet.cell(row=narrative_row, column=1, value="Tahliliy xulosa").font = Font(bold=True)
        for offset, paragraph in enumerate(report.narrative.split("\n\n")):
            cell = sheet.cell(
                row=narrative_row + 1 + offset, column=1, value=safe_cell(paragraph)
            )
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue(), f"{base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt == "docx":
        from docx import Document as DocxDocument

        doc = DocxDocument()
        doc.add_heading(report.title, level=0)
        doc.add_paragraph(f"Davr: {report.period_start.strftime('%d.%m.%Y')} — {report.period_end.strftime('%d.%m.%Y')} · Holat: {report.status}")
        doc.add_heading("Asosiy ko'rsatkichlar", level=1)
        for section, values in rows:
            doc.add_heading(section, level=2)
            table = doc.add_table(rows=0, cols=2)
            table.style = "Light Grid Accent 1"
            for label, value in values:
                cells = table.add_row().cells
                cells[0].text = str(label)
                cells[1].text = str(value)
        doc.add_heading("Tahliliy xulosa", level=1)
        for paragraph in report.narrative.split("\n\n"):
            doc.add_paragraph(paragraph)
        doc.add_paragraph("")
        doc.add_paragraph("Hisobot Mahalla Assistant tomonidan avtomatik shakllantirildi. Rasmiy tasdiqlash talab etiladi.")
        buffer = io.BytesIO()
        doc.save(buffer)
        return buffer.getvalue(), f"{base}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, title=report.title)
        styles = getSampleStyleSheet()
        story = [Paragraph(report.title, styles["Title"]), Spacer(1, 8)]
        story.append(Paragraph(f"Davr: {report.period_start.strftime('%d.%m.%Y')} — {report.period_end.strftime('%d.%m.%Y')} · Holat: {report.status}", styles["Normal"]))
        for section, values in rows:
            story.append(Spacer(1, 10))
            story.append(Paragraph(section, styles["Heading2"]))
            table = Table(
                [[Paragraph(str(label), styles["BodyText"]), Paragraph(str(value), styles["BodyText"])] for label, value in values],
                colWidths=[190, 300],
            )
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D8D2C2")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0ECE0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(table)
        story.append(Spacer(1, 14))
        story.append(Paragraph("Tahliliy xulosa", styles["Heading2"]))
        for paragraph in report.narrative.split("\n\n"):
            story.append(Paragraph(paragraph, styles["BodyText"]))
            story.append(Spacer(1, 6))
        story.append(Paragraph("Hisobot Mahalla Assistant tomonidan avtomatik shakllantirildi. Rasmiy tasdiqlash talab etiladi.", styles["Italic"]))
        doc.build(story)
        return buffer.getvalue(), f"{base}.pdf", "application/pdf"
    raise validation_error("Format qo'llab-quvvatlanmaydi.")
