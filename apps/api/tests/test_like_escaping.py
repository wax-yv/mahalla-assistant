from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete

from app.core.db import SessionLocal
from app.core.search import escape_like, like_pattern
from app.models import Citizen

MARKER = "D5sinov"

@pytest.fixture()
def citizens():
    with SessionLocal() as db:
        db.execute(delete(Citizen).where(Citizen.full_name.like(f"{MARKER}%")))
        db.commit()
        db.add(
            Citizen(
                full_name=f"{MARKER} % belgili",
                gender="Erkak",
                birth_date=date(1990, 1, 1),
                phone="+998900000501",
            )
        )
        db.add(
            Citizen(
                full_name=f"{MARKER} _ belgili",
                gender="Ayol",
                birth_date=date(1991, 2, 2),
                phone="+998900000502",
            )
        )
        db.add(
            Citizen(
                full_name=f"{MARKER} oddiy",
                gender="Erkak",
                birth_date=date(1992, 3, 3),
                phone="+998900000503",
            )
        )
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(Citizen).where(Citizen.full_name.like(f"{MARKER}%")))
        db.commit()

def _names(q: str) -> list[str]:
    from app.services import citizens as service

    with SessionLocal() as db:
        rows, _meta = service.list_citizens(db, q=q, page_size=50)
    return [row["full_name"] for row in rows]

def test_escape_like_escapes_special_chars():
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("a\\b") == "a\\\\b"
    assert escape_like("oddiy") == "oddiy"

def test_like_pattern_wraps_with_percent():
    assert like_pattern("x") == "%x%"
    assert like_pattern("x%") == "%x\\%%"

def test_percent_does_not_match_everything(citizens):
    names = _names("%")
    assert names == [f"{MARKER} % belgili"]

def test_underscore_does_not_match_single_char(citizens):
    names = _names("_")
    assert names == [f"{MARKER} _ belgili"]

def test_normal_search_still_works(citizens):
    names = _names(MARKER)
    assert len(names) == 3
    assert f"{MARKER} oddiy" in names
