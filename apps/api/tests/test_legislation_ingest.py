"""J-12: qonunchilik sinxronlash — versiyalar soni va `raw_html` hajmi.

Muqova:
- Har sinxronlashda yangi `LegislationVersion` (to'liq `raw_text`) yaratilardi
  va chunk'lar qayta qayta yozilardi — kontent o'zgarmagan bo'lsa ham.
- `document.raw_html` ga 400 KB HTML saqlanardi (bazaning bepul tarifi
  tez to'ladi).
- Versiyalar soni cheklanmagan edi — tarix yig'ilib borardi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select

from app.core.db import SessionLocal
from app.models import LegislationChunk, LegislationDocument, LegislationVersion
from app.services import legislation as service

DOC_URL = "https://lex.uz/docs/J12-sinov-hujjati"


@pytest.fixture()
def clean_legislation():
    def _cleanup():
        with SessionLocal() as db:
            doc = db.execute(
                select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
            ).scalar_one_or_none()
            if doc is not None:
                db.execute(
                    delete(LegislationChunk).where(LegislationChunk.document_id == doc.id)
                )
                db.execute(
                    delete(LegislationVersion).where(
                        LegislationVersion.document_id == doc.id
                    )
                )
                db.delete(doc)
            db.commit()

    _cleanup()
    yield
    _cleanup()


def _payload(text: str, title: str = "J12 sinov hujjati") -> dict:
    import hashlib

    body = text if len(text) > 150 else (text + " " + "J12TEST qo'ldirma matn. " * 30)
    return {
        "url": DOC_URL,
        "title": title,
        "text": body,
        "number": "J12-2022",
        "doc_type": "Qonun",
        "adoption_date": None,
        "effective_date": None,
        "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "raw_html": "<html>" + ("x" * 400_000) + "</html>",
        "legal_status": "amaldagi",
    }


def _ingest(monkeypatch, text: str, title: str = "J12 sinov hujjati"):
    payload = _payload(text, title)
    monkeypatch.setattr(
        service, "fetch_document", lambda url, timeout=25: payload
    )
    with SessionLocal() as db:
        document = service.ingest_document(db, DOC_URL, actor="tester")
        return document.id


def test_unchanged_content_creates_no_new_version(clean_legislation, monkeypatch):
    """Kontent o'zgarmasa — yangi versiya qatori yaratilmasligi kerak."""
    _ingest(monkeypatch, "birinchi kontent")
    _ingest(monkeypatch, "birinchi kontent")

    with SessionLocal() as db:
        doc = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
        ).scalar_one()
        versions = db.execute(
            select(LegislationVersion).where(LegislationVersion.document_id == doc.id)
        ).scalars().all()
        chunks = db.execute(
            select(LegislationChunk).where(LegislationChunk.document_id == doc.id)
        ).scalars().all()

    assert len(versions) == 1, f"kutilgan 1 versiya, topildi: {len(versions)}"
    assert chunks, "chunk'lar saqlanib qolishi kerak"


def test_unchanged_content_only_updates_retrieved_at(clean_legislation, monkeypatch):
    """Kontent o'zgarmasa — faqat `retrieved_at` yangilanadi."""
    _ingest(monkeypatch, "birinchi kontent")
    with SessionLocal() as db:
        doc = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
        ).scalar_one()
        first_retrieved = doc.retrieved_at
        version_id = db.execute(
            select(LegislationVersion).where(
                LegislationVersion.document_id == doc.id
            )
        ).scalar_one().id

    import time

    time.sleep(0.01)
    _ingest(monkeypatch, "birinchi kontent")

    with SessionLocal() as db:
        doc = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
        ).scalar_one()
        version = db.get(LegislationVersion, version_id)
        assert version is not None, "eski versiya o'chib ketmishi kerak emas"
        assert doc.retrieved_at >= first_retrieved
        assert version.is_current is True


def test_changed_content_creates_new_version(clean_legislation, monkeypatch):
    """Kontent o'zgarsa — yangi versiya yaratilishi kerak."""
    _ingest(monkeypatch, "birinchi kontent")
    _ingest(monkeypatch, "ikkinchi kontent boshqacha")

    with SessionLocal() as db:
        doc = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
        ).scalar_one()
        versions = db.execute(
            select(LegislationVersion).where(LegislationVersion.document_id == doc.id)
        ).scalars().all()
        current = [v for v in versions if v.is_current]

    assert len(versions) == 2, f"kutilgan 2 versiya, topildi: {len(versions)}"
    assert len(current) == 1, "faqat bitta joriy versiya bo'lishi kerak"


def test_only_last_three_versions_are_kept(clean_legislation, monkeypatch):
    """Faqat oxirgi 3 versiya saqlanishi kerak."""
    for index in range(5):
        _ingest(monkeypatch, f"kontent-{index}-boshqacha")

    with SessionLocal() as db:
        doc = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
        ).scalar_one()
        count = db.execute(
            select(func.count())
            .select_from(LegislationVersion)
            .where(LegislationVersion.document_id == doc.id)
        ).scalar_one()

    assert count == 3, f"kutilgan 3 versiya, topildi: {count}"


def test_raw_html_is_not_stored(clean_legislation, monkeypatch):
    """400 KB `raw_html` bazada saqlanmasligi kerak."""
    _ingest(monkeypatch, "birinchi kontent")

    with SessionLocal() as db:
        doc = db.execute(
            select(LegislationDocument).where(LegislationDocument.source_url == DOC_URL)
        ).scalar_one()
        assert len(doc.raw_html or "") < 1000, (
            f"raw_html saqlangan: {len(doc.raw_html or '')} belgi"
        )
