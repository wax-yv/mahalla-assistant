from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import minus_years
from app.models import Case, Citizen, Family, House, Street, Task

COUNT_WORDS: tuple[str, ...] = (
    "nechta", "qancha", "soni", "necha", "nafar", "miqdori", "miqdor",
    "raqami", "nechchi", "umumiy son", "aniq son", "qancha kishi", "necha ta",
)

LIST_WORDS: tuple[str, ...] = (
    "ro'yxat", "ro'yxati", "ro'yxatini", "ismi", "ism-familiya", "ism familiya",
    "ismlar", "familiyalar", "familiya", "kimlar", "kim bor", "kim bor",
    "chiqarib ber", "ko'rsat", "tarkibi", "barcha fuqaro", "butun ro'yxat",
)

DATA_SUBJECT_WORDS: tuple[str, ...] = (
    "fuqaro", "fuqarolar", "kishi", "kishilar", "odam", "odamlar", "shaxs",
    "shaxslar", "yashovchi", "yashovchilar", "oila", "oilalar", "mahalla",
)

FOREIGN_SUBJECT_WORDS: tuple[str, ...] = (
    "murojaat", "murojaatlar", "vazifa", "vazifalar", "hujjat", "hujjatlar",
    "hisobot", "hisobotlar", "agent", "agentlar", "dastur", "dasturlar",
    "qonun", "qonunchilik", "modda", "moddalar", "kredit", "subsidiya",
    "bank", "programma", "jarayon", "ish", "ishlar",
)

LEGAL_WORDS: tuple[str, ...] = (
    "qonun", "qonunchilik", "modda", "moddalar", "lex.uz", "lexuz", "farmon",
    "kodeks", "konstitutsiya", "huquqiy", "qoidalar", "hujjat qonun",
)

CREDIT_WORDS: tuple[str, ...] = (
    "kredit", "subsidiya", "ipoteka", "grant", "foizsiz yordam", "bank",
    "moliyalashtirish",
)

DISABILITY_WORDS: tuple[str, ...] = (
    "nogiron", "nogironlik", "nogironligi", "invalid", "majburiy", "harakatsiz",
)

GROUP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:\b1\b|\bi\b|birinchi|1-)\s*-?\s*guruh", "I"),
    (r"(?:\b2\b|\bii\b|ikkinchi|2-)\s*-?\s*guruh", "II"),
    (r"(?:\b3\b|\biii\b|uchinchi|3-)\s*-?\s*guruh", "III"),
    (r"(?:\b4\b|\biv\b|to'rtinchi|4-)\s*-?\s*guruh", "IV"),
)

ROMAN_TO_ARABIC: dict[str, str] = {"I": "1", "II": "2", "III": "3", "IV": "4"}

_APOSTROPHES = "ʻʼ‘’«»'`"

def normalize(text: str) -> str:
    out = (text or "").lower()
    for ch in _APOSTROPHES:
        out = out.replace(ch, "'")
    out = out.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", out).strip()

def _strip_suffix(value: str) -> str:
    v = normalize(value)
    v = re.sub(r"\bko'?chasi\b", " ", v)
    v = re.sub(r"\bko'?cha\b", " ", v)
    return re.sub(r"\s+", " ", v).strip()

def _word_hit(text: str, phrase: str, min_len: int = 3) -> bool:
    phrase = normalize(phrase)
    if not phrase:
        return False
    if len(phrase) < min_len:
        return False
    if " " in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}", text) is not None

@dataclass
class Facets:

    social: list[str] = field(default_factory=list)
    employment: list[str] = field(default_factory=list)
    gender: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    street: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    needs: list[str] = field(default_factory=list)
    entity: str = "citizens"
    list_mode: bool = False
    count_mode: bool = False
    status: str | None = None
    breakdown_by: str | None = None
    rank_top: bool = False
    aggregate: str | None = None

    def labels(self) -> list[str]:
        out: list[str] = []
        if self.social:
            out.append("ijtimoiy holat: " + ", ".join(self.social))
        if self.employment:
            out.append("bandlik: " + ", ".join(self.employment))
        if self.gender:
            out.append("jins: " + ", ".join(self.gender))
        if self.education:
            out.append("ma'lumoti: " + ", ".join(self.education))
        if self.street:
            out.append(f"ko'cha: {self.street}")
        if self.age_min is not None or self.age_max is not None:
            if self.age_min is not None and self.age_max is not None:
                out.append(f"yosh: {self.age_min}–{self.age_max}")
            elif self.age_max is not None:
                out.append(f"yosh: {self.age_max} gacha")
            else:
                out.append(f"yosh: {self.age_min} dan katta")
        if self.needs:
            out.append("ehtiyoj: " + ", ".join(self.needs))
        if self.status == "overdue":
            out.append("holat: kechikkan")
        elif self.status == "today":
            out.append("holat: bugungi")
        elif self.status == "done":
            out.append("holat: bajarilgan")
        elif self.status == "open":
            out.append("holat: ochiq")
        elif self.status == "closed":
            out.append("holat: yopilgan")
        return out

    def is_empty(self) -> bool:
        return not (self.social or self.employment or self.gender or self.education
                    or self.street or self.age_min or self.age_max or self.needs
                    or self.status)

@dataclass
class Row:
    id: str
    title: str
    subtitle: str = ""
    meta: str = ""
    badges: list[str] = field(default_factory=list)

@dataclass
class DataAnswer:
    text: str
    total: int
    rows: list[Row]
    facets: Facets
    breakdown: list[tuple[str, int]]
    entity_label: str
    as_of: str
    warnings: list[str]

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "entity": self.facets.entity,
            "total": self.total,
            "count": self.total,
            "rows": [
                {
                    "id": r.id,
                    "title": r.title,
                    "subtitle": r.subtitle,
                    "meta": r.meta,
                    "badges": r.badges,
                }
                for r in self.rows
            ],
            "breakdown": [{"label": k, "value": v} for k, v in self.breakdown],
            "facets": {
                "social": self.facets.social,
                "employment": self.facets.employment,
                "gender": self.facets.gender,
                "education": self.facets.education,
                "street": self.facets.street,
                "age_min": self.facets.age_min,
                "age_max": self.facets.age_max,
                "needs": self.facets.needs,
                "entity": self.facets.entity,
                "list_mode": self.facets.list_mode,
                "count_mode": self.facets.count_mode,
                "status": self.facets.status,
                "breakdown_by": self.facets.breakdown_by,
                "rank_top": self.facets.rank_top,
                "aggregate": self.facets.aggregate,
            },
            "as_of": self.as_of,
            "source": "database",
        }

def _distinct(db: Session, column: Any, limit: int = 80) -> list[str]:
    rows = (
        db.execute(
            select(column)
            .where(column.is_not(None))
            .distinct()
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [str(r) for r in rows if r and str(r).strip()]

def _discover(db: Session) -> dict[str, list[str]]:
    social = _distinct(db, Citizen.social_status)
    employment = _distinct(db, Citizen.employment_status)
    gender = _distinct(db, Citizen.gender)
    education = _distinct(db, Citizen.education)
    streets = _distinct(db, Street.name)
    return {
        "social": social,
        "employment": employment,
        "gender": gender,
        "education": education,
        "streets": streets,
    }

def _match_group(text: str) -> str | None:
    for pattern, roman in GROUP_PATTERNS:
        if re.search(pattern, text):
            return roman
    return None

def _value_group(value: str) -> str | None:
    v = normalize(value)
    for pattern, roman in GROUP_PATTERNS:
        if re.search(pattern, v):
            return roman
    return None

def _match_social(text: str, values: list[str]) -> list[str]:
    matched: list[str] = []
    disability = any(w in text for w in DISABILITY_WORDS)
    group = _match_group(text)

    for value in values:
        v = normalize(value)
        if not v or v in {"yo'q", "-", "yoq", "noma'lum", "nomalum"}:
            continue

        if disability and group:
            value_group = _value_group(value)
            if value_group is not None:
                if value_group == group and value not in matched:
                    matched.append(value)
                continue
            if "nogiron" in v:
                continue

        hit = False
        if v in text:
            hit = True
        else:
            tokens = [t for t in re.split(r"[^a-z0-9']+", v) if len(t) >= 3]
            significant = [t for t in tokens if t not in {"bor", "va", "guruh", "ro'yxatida"}]
            if significant and all(_word_hit(text, t) for t in significant):
                hit = True
        if hit and value not in matched:
            matched.append(value)

    if disability and not matched:
        for value in values:
            if "nogiron" in normalize(value) and value not in matched:
                matched.append(value)
    return matched

def _match_simple(text: str, values: list[str], exclude_contains: tuple[str, ...] = ()) -> list[str]:
    matched: list[str] = []
    for value in values:
        v = normalize(value)
        if not v or v in {"yo'q", "-", "yoq", "noma'lum", "nomalum"}:
            continue
        if exclude_contains and any(ex in text for ex in exclude_contains):
            continue
        if _word_hit(text, v):
            matched.append(value)
    return matched

def _match_street(text: str, values: list[str]) -> str | None:
    best: str | None = None
    best_len = 0
    for value in values:
        base = _strip_suffix(value)
        if len(base) < 4:
            continue
        if base in text and len(base) > best_len:
            best = value
            best_len = len(base)
    return best

def _match_age(text: str) -> tuple[int | None, int | None]:
    match = re.search(r"(\d{1,2})\s*yoshdan\s+(\d{1,2})\s*(?:yosh)?gacha", text)
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*yosh", text)
    if match:
        return int(match.group(1)), int(match.group(2))

    if "yosh" in text:
        match = re.search(r"(\d{1,2})\s*dan\s+(\d{1,2})\s*gacha", text)
        if match:
            return int(match.group(1)), int(match.group(2))

    match = re.search(r"(\d{1,2})\s*yoshgacha", text)
    if match:
        return None, int(match.group(1))

    if "yosh" in text:
        match = re.search(r"(\d{1,2})\s*gacha\b", text)
        if match:
            return None, int(match.group(1))

    match = re.search(r"(\d{1,2})\s*yoshdan\s*(?:katta|yuqori|ortiq|kattaroq)", text)
    if match:
        return int(match.group(1)), None

    match = re.search(r"(\d{1,2})\s*yoshdan\s*(?:kichik|past|quyi|kichikroq)", text)
    if match:
        value = int(match.group(1))
        return (None, value - 1) if value > 0 else (None, 0)

    match = re.search(r"(\d{1,2})\s*yoshli", text)
    if match:
        return int(match.group(1)), int(match.group(1))

    match = re.search(r"yosh(?:i)?\s*(\d{1,2})\b", text)
    if match:
        return int(match.group(1)), int(match.group(1))
    return None, None

EMPLOYMENT_ALIASES: dict[str, str] = {
    "talaba": "O'qiydi",
    "talabalar": "O'qiydi",
    "o'quvchi": "O'qiydi",
    "o'quvchilar": "O'qiydi",
    "ishlaydigan": "Ishlaydi",
    "ishchi": "Ishlaydi",
    "nafaqada": "Pensioner",
    "nafaqaxo'r": "Pensioner",
}

def _match_needs(text: str) -> list[str]:
    candidates: list[str] = []
    for token in re.findall(r"[a-z']{5,}", text):
        if token in {"guruh", "ro'yxat", "fuqaro", "fuqarolar", "nafar", "soni"}:
            continue
        if token not in candidates:
            candidates.append(token)
    return candidates[:4]

def analyze(db: Session, message: str, base: "Facets | None" = None) -> Facets:
    text = normalize(message)
    vocab = _discover(db)

    facets = Facets()

    if re.search(r"\boila(?:lar)?(?:i|ning|da|dan)?\b", text) and "fuqaro" not in text:
        facets.entity = "families"
    elif re.search(r"\bmurojaat\w*\b", text):
        facets.entity = "cases"
    elif re.search(r"\bvazifal?\w*\b", text):
        facets.entity = "tasks"
    elif re.search(r"\buy(?:lar)?\b", text):
        facets.entity = "houses"
    elif re.search(r"\bko'?cha(?:lar)?\b", text):
        facets.entity = "streets"

    facets.social = _match_social(text, vocab["social"])
    facets.employment = _match_simple(text, vocab["employment"])
    if not facets.employment:
        for alias, value in EMPLOYMENT_ALIASES.items():
            if re.search(rf"\b{alias}\w*\b", text):
                facets.employment = [value]
                break
    facets.education = _match_simple(text, vocab["education"])
    gender_exclude = ("ayollar daftari", "ayollar daftar") if "ayollar" in text and "daftar" in text else ()
    facets.gender = _match_simple(text, vocab["gender"], exclude_contains=gender_exclude)
    facets.street = _match_street(text, vocab["streets"])
    facets.age_min, facets.age_max = _match_age(text)
    if facets.entity == "citizens" and facets.social:
        facets.needs = []

    if facets.entity == "tasks":
        if re.search(r"kechikk\w*|muddati o'?tgan", text):
            facets.status = "overdue"
        elif re.search(r"\bbugungi\b", text):
            facets.status = "today"
        elif re.search(r"bajarilg\w*", text):
            facets.status = "done"
    elif facets.entity == "cases":
        if re.search(r"\bochiq\b", text):
            facets.status = "open"
        elif re.search(r"yopilg\w*|yakunlangan", text):
            facets.status = "closed"

    dimension = re.search(
        r"(jins\w*|bandlik(?:\s+holati)?|ijtimoiy\s+holat\w*|ta'?lim\w*|ma'?lumot\w*|"
        r"ko'?cha(?:lar)?|holati|ustuvorlik\w*|oilalar?)\s+bo'?yicha",
        text,
    )
    if dimension:
        facet_word = dimension.group(1)
        if facet_word.startswith("jins"):
            facets.breakdown_by = "gender"
        elif facet_word.startswith("bandlik"):
            facets.breakdown_by = "employment"
        elif facet_word.startswith("ijtimoiy"):
            facets.breakdown_by = "social"
        elif facet_word.startswith("ta'lim") or facet_word.startswith("ma'lumot") or facet_word.startswith("ta'lim"):
            facets.breakdown_by = "education"
        elif facet_word.startswith("ko'cha") or facet_word.startswith("ko'cha"):
            facets.breakdown_by = "street"
        elif facet_word == "holati":
            facets.breakdown_by = "status"
        elif facet_word.startswith("ustuvorlik"):
            facets.breakdown_by = "priority"
        elif facet_word.startswith("oila"):
            facets.breakdown_by = "family_type"

    if re.search(r"eng\s+ko'?p", text) and re.search(r"ko'?cha", text):
        facets.rank_top = True

    if re.search(r"o'?rtacha", text) and re.search(r"yosh", text):
        facets.aggregate = "avg_age"

    facets.list_mode = any(w in text for w in LIST_WORDS) or bool(
        re.search(r"ism[\s\-]familiy", text)
    )
    facets.count_mode = any(w in text for w in COUNT_WORDS)

    if not facets.list_mode and not facets.count_mode:
        facets.count_mode = True

    if base is not None:
        facets = _inherit_context(text, facets, base)
    return facets

RESET_WORDS: tuple[str, ...] = (
    "barcha", "butun", "hammasi", "hamma", "umumiy", "barchasi",
)

def _inherit_context(text: str, facets: Facets, base: Facets) -> Facets:
    if any(word in text for word in RESET_WORDS):
        return facets
    if not facets.list_mode:
        return facets
    has_own_filter = bool(
        facets.social
        or facets.employment
        or facets.education
        or facets.gender
        or facets.street
        or facets.age_min is not None
        or facets.age_max is not None
        or facets.status
    )
    if not has_own_filter:
        facets.social = list(base.social)
        facets.employment = list(base.employment)
        facets.education = list(base.education)
        facets.gender = list(base.gender)
        facets.street = base.street
        facets.status = base.status
        facets.age_min = base.age_min
        facets.age_max = base.age_max
        facets.needs = list(base.needs)
        facets.entity = base.entity
    return facets

def _citizen_conditions(db: Session, facets: Facets) -> list[Any]:
    today = date_cls.today()
    conditions: list[Any] = [Citizen.archived_at.is_(None)]

    if facets.social:
        conditions.append(Citizen.social_status.in_(facets.social))
    if facets.employment:
        conditions.append(Citizen.employment_status.in_(facets.employment))
    if facets.gender:
        conditions.append(Citizen.gender.in_(facets.gender))
    if facets.education:
        conditions.append(Citizen.education.in_(facets.education))
    if facets.street:
        conditions.append(
            Citizen.family.has(
                Family.house.has(House.street.has(Street.name == facets.street))
            )
        )
    if facets.age_min is not None or facets.age_max is not None:
        conditions.append(Citizen.birth_date.is_not(None))
        if facets.age_max is not None:
            conditions.append(
                Citizen.birth_date > minus_years(today, facets.age_max + 1)
            )
        if facets.age_min is not None:
            conditions.append(
                Citizen.birth_date <= minus_years(today, facets.age_min)
            )
    return conditions

def _age_of(birth: date_cls | None) -> int | None:
    if not birth:
        return None
    today = date_cls.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))

def _query_citizens(db: Session, facets: Facets, limit: int) -> tuple[int, list[Row], list[tuple[str, int]]]:
    conditions = _citizen_conditions(db, facets)

    total = int(
        db.execute(select(func.count()).select_from(Citizen).where(*conditions)).scalar_one()
    )

    breakdown: list[tuple[str, int]] = []
    if facets.social and len(facets.social) > 1:
        rows = db.execute(
            select(Citizen.social_status, func.count())
            .where(*conditions)
            .group_by(Citizen.social_status)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]
    elif facets.employment and len(facets.employment) > 1:
        rows = db.execute(
            select(Citizen.employment_status, func.count())
            .where(*conditions)
            .group_by(Citizen.employment_status)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]
    elif facets.gender and len(facets.gender) > 1:
        rows = db.execute(
            select(Citizen.gender, func.count())
            .where(*conditions)
            .group_by(Citizen.gender)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]
    elif facets.social:
        rows = db.execute(
            select(Citizen.social_status, func.count())
            .where(*conditions)
            .group_by(Citizen.social_status)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in rows if k]
    elif facets.employment:
        rows = db.execute(
            select(Citizen.employment_status, func.count())
            .where(*conditions)
            .group_by(Citizen.employment_status)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in rows if k]
    else:
        rows = db.execute(
            select(Citizen.social_status, func.count())
            .where(*conditions, Citizen.social_status.notin_(["Yo'q", "-", ""]))
            .group_by(Citizen.social_status)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]

    rows_out: list[Row] = []
    if facets.list_mode and total:
        citizens = (
            db.execute(
                select(Citizen)
                .where(*conditions)
                .order_by(Citizen.family_role.asc(), Citizen.full_name.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for citizen in citizens:
            age = _age_of(citizen.birth_date)
            bits: list[str] = []
            if age is not None:
                bits.append(f"{age} yosh")
            if citizen.gender:
                bits.append(citizen.gender)
            address = ""
            try:
                if citizen.family and citizen.family.house:
                    address = citizen.family.house.address_label or ""
            except Exception:
                address = ""
            badges: list[str] = []
            if citizen.social_status and normalize(citizen.social_status) not in {"yo'q", "-", ""}:
                badges.append(citizen.social_status)
            if citizen.employment_status:
                badges.append(citizen.employment_status)
            rows_out.append(
                Row(
                    id=citizen.id,
                    title=citizen.full_name,
                    subtitle=" · ".join(bits),
                    meta=address or citizen.phone or "",
                    badges=badges,
                )
            )
    return total, rows_out, breakdown

def _query_families(db: Session, facets: Facets, limit: int) -> tuple[int, list[Row], list[tuple[str, int]]]:
    conditions: list[Any] = []
    if facets.social:
        conditions.append(
            or_(
                Family.social_status.in_(facets.social),
                Family.members.any(
                    and_(
                        Citizen.social_status.in_(facets.social),
                        Citizen.archived_at.is_(None),
                    )
                ),
            )
        )
    if facets.street:
        conditions.append(
            Family.house.has(House.street.has(Street.name == facets.street))
        )
    total = int(
        db.execute(select(func.count()).select_from(Family).where(*conditions)).scalar_one()
    )
    rows = db.execute(
        select(Family.social_status, func.count()).where(*conditions).group_by(Family.social_status)
    ).all()
    breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]

    out: list[Row] = []
    if facets.list_mode and total:
        families = (
            db.execute(select(Family).where(*conditions).order_by(Family.id.asc()).limit(limit))
            .scalars()
            .all()
        )
        for family in families:
            head = ""
            address = ""
            members = 0
            try:
                if family.head:
                    head = family.head.full_name
                if family.house:
                    address = family.house.address_label or ""
                members = len(family.members)
            except Exception:
                pass
            out.append(
                Row(
                    id=family.id,
                    title=head or family.id,
                    subtitle=f"{family.family_type} · {members} nafar a'zo",
                    meta=address,
                    badges=[family.social_status] if family.social_status else [],
                )
            )
    return total, out, breakdown

def _case_conditions(facets: Facets) -> list[Any]:
    conditions: list[Any] = []
    if facets.status == "open":
        conditions.append(Case.status.notin_(["closed", "cancelled"]))
    elif facets.status == "closed":
        conditions.append(Case.status.in_(["closed", "cancelled"]))
    return conditions

def _task_conditions(facets: Facets) -> list[Any]:
    from app.core.time import today_local

    today = today_local()
    conditions: list[Any] = []
    if facets.status == "overdue":
        conditions.append(Task.due_date < today)
        conditions.append(Task.status.notin_(["completed", "cancelled"]))
    elif facets.status == "today":
        conditions.append(Task.due_date == today)
        conditions.append(Task.status.notin_(["completed", "cancelled"]))
    elif facets.status == "done":
        conditions.append(Task.status == "completed")
    return conditions

def _query_cases(db: Session, facets: Facets, limit: int) -> tuple[int, list[Row], list[tuple[str, int]]]:
    conditions = _case_conditions(facets)
    total = int(
        db.execute(select(func.count()).select_from(Case).where(*conditions)).scalar_one()
    )
    rows = db.execute(
        select(Case.status, func.count()).where(*conditions).group_by(Case.status)
    ).all()
    breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]
    out: list[Row] = []
    if facets.list_mode and total:
        cases = (
            db.execute(
                select(Case).where(*conditions).order_by(Case.opened_at.desc()).limit(limit)
            )
            .scalars()
            .all()
        )
        for case in cases:
            out.append(
                Row(
                    id=case.id,
                    title=case.title,
                    subtitle=case.category or "",
                    meta=case.priority or "",
                    badges=[case.status] if case.status else [],
                )
            )
    return total, out, breakdown

def _query_houses(db: Session, facets: Facets, limit: int) -> tuple[int, list[Row], list[tuple[str, int]]]:
    conditions: list[Any] = []
    if facets.street:
        conditions.append(House.street.has(Street.name == facets.street))
    total = int(
        db.execute(select(func.count()).select_from(House).where(*conditions)).scalar_one()
    )
    breakdown: list[tuple[str, int]] = []
    if not facets.street:
        rows = db.execute(
            select(Street.name, func.count(House.id))
            .select_from(Street)
            .outerjoin(House, House.street_id == Street.id)
            .group_by(Street.name)
            .order_by(func.count(House.id).desc())
            .limit(10)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in rows if k]
    out: list[Row] = []
    if facets.list_mode and total:
        houses = (
            db.execute(
                select(House).where(*conditions).order_by(House.house_number.asc()).limit(limit)
            )
            .scalars()
            .all()
        )
        for house in houses:
            street_name = ""
            try:
                if house.street:
                    street_name = house.street.name
            except Exception:
                street_name = ""
            out.append(
                Row(
                    id=house.id,
                    title=f"{house.house_number}-uy",
                    subtitle=street_name,
                    meta=house.address_label or "",
                )
            )
    return total, out, breakdown

def _query_streets(db: Session, facets: Facets, limit: int) -> tuple[int, list[Row], list[tuple[str, int]]]:
    total = int(db.execute(select(func.count()).select_from(Street)).scalar_one())
    rows = db.execute(
        select(Street.name, func.count(House.id))
        .select_from(Street)
        .outerjoin(House, House.street_id == Street.id)
        .group_by(Street.name)
        .order_by(func.count(House.id).desc())
        .limit(12)
    ).all()
    breakdown = [(str(k), int(v)) for k, v in rows if k]
    out: list[Row] = []
    if facets.list_mode and total:
        streets = db.execute(select(Street).order_by(Street.name.asc()).limit(limit)).scalars().all()
        for street in streets:
            out.append(Row(id=street.id, title=street.name, subtitle=street.mahalla_id or ""))
    return total, out, breakdown

def _query_tasks(db: Session, facets: Facets, limit: int) -> tuple[int, list[Row], list[tuple[str, int]]]:
    conditions = _task_conditions(facets)
    total = int(
        db.execute(select(func.count()).select_from(Task).where(*conditions)).scalar_one()
    )
    rows = db.execute(
        select(Task.status, func.count()).where(*conditions).group_by(Task.status)
    ).all()
    breakdown = [(str(k), int(v)) for k, v in sorted(rows, key=lambda x: -x[1]) if k]
    out: list[Row] = []
    if facets.list_mode and total:
        tasks = (
            db.execute(
                select(Task)
                .where(*conditions)
                .order_by(Task.due_date.asc().nullslast())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        for task in tasks:
            out.append(
                Row(
                    id=task.id,
                    title=task.title,
                    subtitle=task.category or "",
                    meta=str(task.due_date or ""),
                    badges=[task.status] if task.status else [],
                )
            )
    return total, out, breakdown

def facets_from_payload(payload: dict[str, Any] | None) -> "Facets | None":
    if not payload:
        return None
    raw = payload.get("facets") or {}
    if not isinstance(raw, dict):
        return None

    def _as_list(key: str) -> list[str]:
        value = raw.get(key)
        if isinstance(value, list):
            return [str(v) for v in value if v]
        return []

    entity = str(raw.get("entity") or "citizens")
    if entity not in ENTITY_LABELS:
        entity = "citizens"
    return Facets(
        social=_as_list("social"),
        employment=_as_list("employment"),
        gender=_as_list("gender"),
        education=_as_list("education"),
        street=(str(raw["street"]) if raw.get("street") else None),
        age_min=(int(raw["age_min"]) if raw.get("age_min") is not None else None),
        age_max=(int(raw["age_max"]) if raw.get("age_max") is not None else None),
        needs=_as_list("needs"),
        entity=entity,
        list_mode=bool(raw.get("list_mode")),
        count_mode=bool(raw.get("count_mode")),
        status=(str(raw["status"]) if raw.get("status") else None),
        breakdown_by=(str(raw["breakdown_by"]) if raw.get("breakdown_by") else None),
        rank_top=bool(raw.get("rank_top")),
        aggregate=(str(raw["aggregate"]) if raw.get("aggregate") else None),
    )

ENTITY_LABELS = {
    "citizens": "fuqaro",
    "families": "oila",
    "cases": "murojaat",
    "tasks": "vazifa",
    "houses": "uy",
    "streets": "ko'cha",
}

def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

def today_local() -> "date_cls":
    from app.core.time import today_local as _today

    return _today()

_BREAKDOWN_COLUMNS = {
    "gender": Citizen.gender,
    "employment": Citizen.employment_status,
    "social": Citizen.social_status,
    "education": Citizen.education,
}

def _breakdown_by_dimension(db: Session, facets: Facets) -> list[tuple[str, int]]:
    dimension = facets.breakdown_by
    if not dimension:
        return []
    if entity_is_citizen_dimension(dimension) and facets.entity in {"citizens", ""}:
        column = _BREAKDOWN_COLUMNS[dimension]
        rows = db.execute(
            select(column, func.count())
            .select_from(Citizen)
            .where(Citizen.archived_at.is_(None))
            .group_by(column)
            .order_by(func.count().desc())
            .limit(12)
        ).all()
        return [(str(k), int(v)) for k, v in rows if k]
    if dimension == "street":
        rows = db.execute(
            select(Street.name, func.count(Citizen.id))
            .select_from(Street)
            .join(House, House.street_id == Street.id)
            .join(Family, Family.house_id == House.id)
            .join(Citizen, (Citizen.family_id == Family.id) & (Citizen.archived_at.is_(None)))
            .group_by(Street.name)
            .order_by(func.count(Citizen.id).desc())
            .limit(12)
        ).all()
        return [(str(k), int(v)) for k, v in rows if k]
    if dimension == "status" and facets.entity == "cases":
        rows = db.execute(
            select(Case.status, func.count()).group_by(Case.status).order_by(func.count().desc())
        ).all()
        return [(str(k), int(v)) for k, v in rows if k]
    if dimension in {"status", "priority"} and facets.entity == "tasks":
        column = Task.status if dimension == "status" else Task.priority
        rows = db.execute(
            select(column, func.count()).group_by(column).order_by(func.count().desc())
        ).all()
        return [(str(k), int(v)) for k, v in rows if k]
    if dimension == "social" and facets.entity == "families":
        rows = db.execute(
            select(Family.social_status, func.count())
            .where(Family.social_status.is_not(None))
            .group_by(Family.social_status)
            .order_by(func.count().desc())
            .limit(12)
        ).all()
        return [(str(k), int(v)) for k, v in rows if k]
    if dimension == "family_type" and facets.entity == "families":
        rows = db.execute(
            select(Family.family_type, func.count())
            .group_by(Family.family_type)
            .order_by(func.count().desc())
            .limit(12)
        ).all()
        return [(str(k), int(v)) for k, v in rows if k]
    return []

def entity_is_citizen_dimension(dimension: str) -> bool:
    return dimension in _BREAKDOWN_COLUMNS

def _filter_hint(facets: Facets) -> str:
    if facets.entity not in {"citizens", "families"}:
        return ""
    parts: list[str] = []
    if len(facets.social) == 1:
        parts.append(f"social_status={facets.social[0]}")
    if len(facets.employment) == 1:
        parts.append(f"employment_status={facets.employment[0]}")
    if len(facets.gender) == 1:
        parts.append(f"gender={facets.gender[0]}")
    if facets.street:
        parts.append(f"street={facets.street}")
    if not parts:
        return ""
    query = "&".join(parts)
    route = "/citizens" if facets.entity == "citizens" else "/families"
    return f"Qo'shimcha: to'liq ro'yxatni `{route}?{query}` filtri orqali ko'rish mumkin."

def build_answer(
    db: Session,
    message: str,
    limit: int = 40,
    base_facets: "Facets | None" = None,
) -> DataAnswer:
    from datetime import datetime, timezone

    facets = analyze(db, message, base=base_facets)
    entity = facets.entity

    if entity == "families":
        total, rows, breakdown = _query_families(db, facets, limit)
        label = ENTITY_LABELS[entity]
    elif entity == "cases":
        total, rows, breakdown = _query_cases(db, facets, limit)
        label = ENTITY_LABELS[entity]
    elif entity == "tasks":
        total, rows, breakdown = _query_tasks(db, facets, limit)
        label = ENTITY_LABELS[entity]
    elif entity == "houses":
        total, rows, breakdown = _query_houses(db, facets, limit)
        label = ENTITY_LABELS[entity]
    elif entity == "streets":
        total, rows, breakdown = _query_streets(db, facets, limit)
        label = ENTITY_LABELS[entity]
    else:
        total, rows, breakdown = _query_citizens(db, facets, limit)
        label = ENTITY_LABELS[entity]

    if facets.aggregate == "avg_age" and entity == "citizens":
        birth_rows = db.execute(
            select(Citizen.birth_date).where(
                Citizen.archived_at.is_(None), Citizen.birth_date.is_not(None)
            )
        ).all()
        today = today_local()
        ages = [
            today.year - row[0].year - ((today.month, today.day) < (row[0].month, row[0].day))
            for row in birth_rows
        ]
        average = round(sum(ages) / len(ages), 1) if ages else 0.0
        lines: list[str] = [f"**O'rtacha yosh: {average} yosh.**"]
        if ages:
            lines.append("")
            lines.append(f"Hisobda {len(ages)} nafar fuqaro qatnashdi (tug'ilgan sanasi ma'lum).")
        lines.append("")
        lines.append(
            f"_Manba: fuqaro bazasi — so'rov aynan shu bazada bajarildi ({now_iso()})._"
        )
        return DataAnswer(
            text="\n".join(lines),
            total=len(ages),
            rows=[],
            facets=facets,
            breakdown=[],
            entity_label="fuqaro",
            as_of=now_iso(),
            warnings=[],
        )

    if facets.rank_top and entity == "citizens":
        street_rows = db.execute(
            select(Street.name, func.count(Citizen.id))
            .select_from(Street)
            .join(House, House.street_id == Street.id)
            .join(Family, Family.house_id == House.id)
            .join(Citizen, (Citizen.family_id == Family.id) & (Citizen.archived_at.is_(None)))
            .group_by(Street.name)
            .order_by(func.count(Citizen.id).desc())
            .limit(5)
        ).all()
        breakdown = [(str(k), int(v)) for k, v in street_rows if k]
        lines: list[str] = []
        if breakdown:
            top_name, top_value = breakdown[0]
            lines.append(f"**Eng ko'p fuqaro — {top_name}: {top_value} nafar.**")
            lines.append("")
            lines.append("Ko'chalar bo'yicha taqsimot (top 5):")
            for name, value in breakdown:
                lines.append(f"- {name}: {value} nafar")
        else:
            lines.append("Ko'chalar bo'yicha ma'lumot topilmadi.")
        lines.append("")
        lines.append(
            f"_Manba: fuqaro bazasi — so'rov aynan shu bazada bajarildi ({now_iso()})._"
        )
        return DataAnswer(
            text="\n".join(lines),
            total=total,
            rows=[],
            facets=facets,
            breakdown=breakdown,
            entity_label="fuqaro",
            as_of=now_iso(),
            warnings=[],
        )

    if facets.breakdown_by:
        breakdown = _breakdown_by_dimension(db, facets) or breakdown

    facet_labels = facets.labels()
    scope = " (" + "; ".join(facet_labels) + ")" if facet_labels else ""
    lines: list[str] = []

    if facets.list_mode:
        heading = f"**{scope.strip() or 'Bazadagi barcha ' + label + 'lar'} — {total} nafar**".replace("()", "")
        lines.append(heading)
        lines.append("")
        if total == 0:
            lines.append(
                "Bazada bu mezonga mos yozuv topilmadi. Boshqa toifa yoki shart bilan urinib ko'ring."
            )
        else:
            for index, row in enumerate(rows, start=1):
                parts = [f"{index}. **{row.title}**"]
                if row.subtitle:
                    parts.append(f"({row.subtitle})")
                lines.append(" ".join(parts))
                detail: list[str] = []
                if row.meta:
                    detail.append(row.meta)
                if row.badges:
                    detail.append(" · ".join(row.badges))
                if detail:
                    lines.append(f"   {' · '.join(detail)}")
            if total > len(rows):
                lines.append("")
                lines.append(
                    f"_Jami {total} ta yozuvdan {len(rows)} tasi ko'rsatildi. "
                    f"Qolganini filtr orqali ko'rish mumkin._"
                )
    else:
        lines.append(f"**Jami {total} nafar {label}.**")
        if facet_labels:
            lines.append("")
            lines.append(f"Shart: {'; '.join(facet_labels)}")
        if breakdown and len(breakdown) > 1:
            lines.append("")
            lines.append("Taqsimot:")
            for name, value in breakdown:
                lines.append(f"- {name}: {value}")
        elif total == 0:
            lines.append("")
            lines.append("Bu mezonga mos yozuv bazada topilmadi.")

    hint = _filter_hint(facets)
    if hint:
        lines.append("")
        lines.append(hint)

    lines.append("")
    lines.append(
        f"_Manba: {label} bazasi — so'rov aynan shu bazada bajarildi "
        f"({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)._"
    )

    return DataAnswer(
        text="\n".join(lines),
        total=total,
        rows=rows,
        facets=facets,
        breakdown=breakdown,
        entity_label=label,
        as_of=datetime.now(timezone.utc).isoformat(),
        warnings=[],
    )
