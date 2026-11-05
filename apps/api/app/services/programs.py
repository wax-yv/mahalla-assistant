from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import not_found, validation_error
from app.core.search import like_pattern
from app.core.time import age_from_birth
from app.models import Citizen, MemoryItem, Program
from app.services.serializers import program_out

MAX_MATCH_PROGRAMS = 50

def list_programs(
    db: Session, *, q: str | None = None, type: str | None = None, organization: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(Program).order_by(Program.organization, Program.name)
    if type:
        stmt = stmt.where(Program.type == type)
    if organization:
        stmt = stmt.where(
            Program.organization.ilike(like_pattern(organization.strip()), escape="\\")
        )
    if q:
        term = like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Program.name.ilike(term, escape="\\"),
                Program.organization.ilike(term, escape="\\"),
                Program.target_group.ilike(term, escape="\\"),
                Program.notes.ilike(term, escape="\\"),
            )
        )
    rows = db.execute(stmt).scalars().all()
    checked_at = datetime.now(timezone.utc)
    return [program_out(row, now=checked_at) for row in rows]

def get_program(db: Session, program_id: str) -> dict[str, Any]:
    program = db.get(Program, program_id)
    if program is None:
        raise not_found("Dastur topilmadi.")
    return program_out(program)

def organizations(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Program.organization, func.count())
        .group_by(Program.organization)
        .order_by(Program.organization)
    ).all()
    return [{"name": row[0], "program_count": int(row[1])} for row in rows]

def _match_one(citizen: Citizen, program: Program) -> dict[str, Any]:
    eligibility = program.eligibility or {}
    reasons: list[str] = []
    missing: list[str] = []
    fails = 0
    age = age_from_birth(citizen.birth_date)
    if eligibility.get("min_age") is not None or eligibility.get("max_age") is not None:
        if age is None:
            missing.append("tug'ilgan sana")
        else:
            minimum = eligibility.get("min_age")
            maximum = eligibility.get("max_age")
            if minimum is not None and age < int(minimum):
                fails += 1
                reasons.append(f"Yosh {age} — dastur uchun kamida {minimum} yosh talab qilinadi.")
            if maximum is not None and age > int(maximum):
                fails += 1
                reasons.append(f"Yosh {age} — dastur {maximum} yoshgacha mo'ljallangan.")
            if not fails:
                reasons.append(f"Yosh bo'yicha talab bajariladi ({age} yosh).")
    categories = eligibility.get("categories") or []
    if categories:
        if citizen.social_status in categories:
            reasons.append(f"Ijtimoiy toifa mos: {citizen.social_status}.")
        else:
            fails += 1
            reasons.append(
                f"Ijtimoiy toifa mos emas: {citizen.social_status or 'ko‘rsatilmagan'}."
            )
    if eligibility.get("requires_business"):
        if citizen.employment_status == "Tadbirkor":
            reasons.append("Tadbirkorlik holati tasdiqlangan.")
        else:
            fails += 1
            reasons.append("Tadbirkorlik faoliyati tasdiqlanmagan.")
    if (eligibility.get("min_age") is not None or eligibility.get("max_age") is not None) and not citizen.birth_date:
        missing.append("tug'ilgan sana")
    if eligibility.get("requires_phone") and not citizen.phone:
        missing.append("telefon raqami")
    if fails:
        result = "mos kelmaydi"
    elif missing:
        result = "ma'lumot yetarli emas"
    else:
        result = "mos kelishi mumkin"
    return {
        "program_id": program.id,
        "program_name": program.name,
        "result": result,
        "reasons": reasons,
        "missing_fields": missing,
        "verified_at": program.last_verified_at,
        "source_url": program.official_url,
    }

def match_citizen(
    db: Session, citizen_id: str, program_id: str | None = None
) -> list[dict[str, Any]]:
    citizen = db.get(Citizen, citizen_id)
    if citizen is None or citizen.archived_at is not None:
        raise not_found("Fuqaro topilmadi.")
    if program_id:
        program = db.get(Program, program_id)
        if program is None:
            raise not_found("Dastur topilmadi.")
        return [_match_one(citizen, program)]
    rows = db.execute(
        select(Program).order_by(Program.organization).limit(MAX_MATCH_PROGRAMS)
    ).scalars().all()
    return [_match_one(citizen, program) for program in rows]

def compare(db: Session, program_ids: list[str]) -> list[dict[str, Any]]:
    if not program_ids:
        raise validation_error("Taqqoslash uchun kamida bitta dastur tanlang.")
    ids = list(dict.fromkeys(program_ids))[:6]
    programs = {
        program.id: program
        for program in db.execute(select(Program).where(Program.id.in_(ids))).scalars().all()
    }
    missing = [pid for pid in ids if pid not in programs]
    if missing:
        raise validation_error(f"Bunday dasturlar topilmadi: {', '.join(missing)}")
    checked_at = datetime.now(timezone.utc)
    return [program_out(programs[pid], now=checked_at) for pid in ids]

def get_preference(db: Session, conversation_id: str | None) -> dict[str, Any] | None:
    stmt = select(MemoryItem).where(MemoryItem.key == "credit.bank_preference")
    if conversation_id:
        stmt = stmt.where(
            or_(MemoryItem.conversation_id == conversation_id, MemoryItem.conversation_id.is_(None))
        )
    row = db.execute(stmt.order_by(MemoryItem.created_at.desc())).scalars().first()
    return row.value if row else None

def save_preference(
    db: Session,
    *,
    conversation_id: str | None,
    organization: str,
    program_id: str | None = None,
    program_name: str | None = None,
) -> None:
    value = {
        "organization": organization,
        "program_id": program_id,
        "program_name": program_name,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    row = db.execute(
        select(MemoryItem).where(
            MemoryItem.key == "credit.bank_preference",
            MemoryItem.conversation_id == conversation_id if conversation_id else MemoryItem.conversation_id.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        row = MemoryItem(
            conversation_id=conversation_id,
            kind="preference",
            key="credit.bank_preference",
            value=value,
            source="credit_subsidy_agent",
            confidence="confirmed",
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            row = db.execute(
                select(MemoryItem).where(
                    MemoryItem.key == "credit.bank_preference",
                    MemoryItem.conversation_id == conversation_id
                    if conversation_id
                    else MemoryItem.conversation_id.is_(None),
                )
            ).scalar_one_or_none()
            if row is None:
                raise
            row.value = value
            row.confidence = "confirmed"
            row.created_at = datetime.now(timezone.utc)
            db.flush()
    else:
        row.value = value
        row.confidence = "confirmed"
        row.created_at = datetime.now(timezone.utc)
    db.flush()

def detect_organization(db: Session, text: str) -> dict[str, Any] | None:
    lowered = (text or "").lower()
    rows = db.execute(select(Program)).scalars().all()
    organizations_seen: dict[str, list[Program]] = {}
    for program in rows:
        organizations_seen.setdefault(program.organization, []).append(program)
    aliases = {
        "xalq banki": "Xalq banki",
        "xb.uz": "Xalq banki",
        "nbu": "O'zbekiston Milliy banki",
        "milliy bank": "O'zbekiston Milliy banki",
        "sqb": "Sanoat qurilish banki",
        "sanoat qurilish": "Sanoat qurilish banki",
        "agrobank": "Agrobank",
        "asakabank": "Asakabank",
        "ipoteka": "Ipoteka bank",
        "kapitalbank": "Kapitalbank",
        "trastbank": "Trastbank",
        "brb": "Biznesni rivojlantirish banki",
    }
    for alias, name in aliases.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered):
            programs = organizations_seen.get(name) or [
                p for p in rows if name.lower() in p.organization.lower()
            ]
            if programs:
                return {"organization": programs[0].organization, "programs": programs}
    for name, programs in organizations_seen.items():
        if name.lower() in lowered:
            return {"organization": name, "programs": programs}
    return None
