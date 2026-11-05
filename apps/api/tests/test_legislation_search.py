from __future__ import annotations

import pytest
from app.core.db import SessionLocal
from app.models import LegislationChunk, LegislationDocument, LegislationVersion
from app.services import legislation as service
from sqlalchemy import delete, select

DOC_URL = "https://lex.uz/docs/J11-sinov-hujjati"

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
    with SessionLocal() as db:
        document = LegislationDocument(
            source_url=DOC_URL,
            title="J11 sinov hujjati",
            number="J11-2022",
            legal_status="amaldagi",
            content_hash="j11-test-hash",
        )
        db.add(document)
        db.flush()
        version = LegislationVersion(
            document_id=document.id,
            version_label="J11 v1",
            content_hash="j11-test-hash",
            raw_text="J11TEST korpus",
        )
        db.add(version)
        db.flush()
        chunks = [
            ("19-modda", "Ijara shartlari", "J11TEST ijara haqidagi asosiy qoida."),
            ("7-modda", "Boshqa qoida", "J11TEST 123-son bilan bog'liq izoh matni."),
            ("3-modda", "Kirillcha izoh", "J11TEST вопрос по закону детали."),
            ("11-modda", "Fuqaro huquqlari", "J11TEST fuqaro majburiyatlari ro'yxati."),
        ]
        for index, (article, heading, content) in enumerate(chunks):
            db.add(
                LegislationChunk(
                    document_id=document.id,
                    version_id=version.id,
                    article=article,
                    heading=heading,
                    content=content,
                    chunk_index=index,
                    search_text=f"{document.title} {article} {heading} {content}".lower(),
                )
            )
        db.commit()
    yield
    _cleanup()

def test_tokens_include_numbers():
    tokens = service._tokens("19-moddada 2022 yil 123-son")
    assert "19" in tokens
    assert "2022" in tokens
    assert "123" in tokens

def test_tokens_include_cyrillic():
    tokens = service._tokens("вопрос по закону")
    assert "вопрос" in tokens
    assert "закону" in tokens

def test_tokens_strip_simple_suffixes():
    tokens = service._tokens("fuqarolarning huquqlari")
    assert "fuqaro" in tokens
    assert "fuqarolarning" not in tokens

def test_article_is_extracted_from_query():
    assert service._article_from_query("19-moddaga nima deyilgan?") == "19-modda"
    assert service._article_from_query("7-modda") == "7-modda"
    assert service._article_from_query("bank hizmati") is None

def test_search_finds_by_article(clean_legislation):
    with SessionLocal() as db:
        hits = service.search_chunks(db, "19-modda", limit=5)
    assert hits, "modda bo'yicha natija topilmadi"
    assert hits[0]["chunk"]["article"] == "19-modda"

def test_search_finds_number(clean_legislation):
    with SessionLocal() as db:
        hits = service.search_chunks(db, "123", limit=5)
    assert hits, "raqam bo'yicha natija topilmadi"
    assert any("123" in hit["chunk"]["content"] for hit in hits)

def test_search_finds_cyrillic(clean_legislation):
    with SessionLocal() as db:
        hits = service.search_chunks(db, "вопрос", limit=5)
    assert hits, "kirill so'z bo'yicha natija topilmadi"

def test_search_matches_stemmed_word(clean_legislation):
    with SessionLocal() as db:
        hits = service.search_chunks(db, "fuqarolarning", limit=5)
    assert hits, "kesilgan so'z bo'yicha natija topilmadi"

def test_search_limits_candidates():
    import inspect

    source = inspect.getsource(service.search_chunks)
    assert "limit(SEARCH_CANDIDATE_LIMIT)" in source
