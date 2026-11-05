from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.errors import bad_request, not_found, service_unavailable
from app.models import (
    LegislationChunk,
    LegislationDocument,
    LegislationVersion,
)
from app.services import ai_gateway
from app.services.serializers import legislation_document_out

LEX_BASE = "https://lex.uz"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
NOISE = (
    "Hujjatga taklif yuborish",
    "Audioni tinglash",
    "Hujjat elementidan havola olish",
)
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
STOP = {
    "uchun", "bilan", "yoki", "hamda", "bo'lgan", "bo'lishi", "kerak", "mavjud",
    "qanday", "qaysi", "men", "biz", "siz", "u", "bu", "va", "da", "dan", "ga",
    "ni", "ning", "bir", "eng", "haqida", "bo'yicha", "holda", "olar", "edi",
}


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=25,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "uz,ru;q=0.8,en;q=0.5"},
    )


def _clean_lines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        value = line.strip()
        if not value or value in NOISE:
            continue
        if value.startswith("[OKOZ:") or value.startswith("[TSZ:") or value in {"[", "]"}:
            continue
        if value.startswith("OKOZ:") or value.startswith("TSZ:"):
            continue
        lines.append(value)
    return "\n".join(lines)


def _parse_search(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for row in soup.select("tr.dd-table__main-item"):
        anchor = row.select_one(".dd-table__main-left-desc a.lx_link")
        if anchor is None:
            continue
        href = anchor.get("href", "")
        if "/docs/" not in href:
            continue
        doc_id = href.split("/docs/")[1].split("?")[0].split("#")[0]
        badge = row.select_one(".badge")
        state = row.select_one(".lx_act_state i")
        status_class = " ".join(state.get("class", [])) if state else ""
        results.append(
            {
                "doc_id": doc_id,
                "url": urljoin(LEX_BASE, f"/uz/docs/{doc_id}"),
                "title": anchor.get_text(" ", strip=True),
                "meta": badge.get_text(" ", strip=True) if badge else "",
                "active": "status_code_y" in status_class,
                "status_class": status_class,
            }
        )
    return results


def search_lex(query: str, limit: int = 5) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if len(query) < 2:
        raise bad_request("Qidiruv so'zi kamida 2 belgidan iborat bo'lishi kerak.")
    url = f"{LEX_BASE}/uz/search/all?query={quote(query)}"
    try:
        with _client() as client:
            response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise service_unavailable(f"Lex.uz bilan aloqa o'rnatilmadi: {error}") from error
    data = _parse_search(response.text)
    if not data:
        raise service_unavailable(
            "Lex.uz qidiruv natijalari topilmadi. Sayt vaqtincha javob bermayotgan bo'lishi mumkin."
        )
    return data[: max(1, min(20, limit))]


def _parse_date(text: str) -> date | None:
    match = DATE_RE.search(text or "")
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def fetch_document(url: str) -> dict[str, Any]:
    try:
        with _client() as client:
            response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise service_unavailable(f"Lex.uz hujjati yuklanmadi: {error}") from error
    soup = BeautifulSoup(response.text, "lxml")
    body = soup.select_one(".document") or soup.select_one("#doc_body")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.get_text(strip=True)
        title = re.sub(r"^\d+(-\d+)?-сон\s*", "", title)
        title = re.sub(r"^\d{2}\.\d{2}\.\d{4}\.\s*", "", title)
    if body is None:
        raise service_unavailable("Lex.uz sahifasida hujjat matni topilmadi.")
    text = _clean_lines(body.get_text("\n", strip=True))
    if len(text) < 120:
        raise service_unavailable("Lex.uz hujjat matni juda qisqa — sahifa o'zgargan bo'lishi mumkin.")
    header = text[:1200]
    number_match = re.search(r"(\d+(-\d+)?)-son", title + " " + header)
    number = number_match.group(1) if number_match else ""
    doc_type = ""
    for candidate in ("Konstitutsiya", "Kodeks", "Qonun", "Farmon", "Qaror", "Buyruq", "Nizom"):
        if candidate.lower() in (title + " " + header).lower():
            doc_type = candidate
            break
    effective = None
    eff_match = re.search(r"(\d{4}-yil\s+\d{1,2}-[a-z]+dan)\s+e[ʼ']tiboran kuchga kiradi", text)
    if eff_match:
        effective = None
    return {
        "url": url,
        "title": title[:480] or "Lex.uz hujjati",
        "text": text,
        "number": number,
        "doc_type": doc_type,
        "adoption_date": _parse_date(header),
        "effective_date": effective,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "raw_html": response.text[:400000],
        "legal_status": "amaldagi" if "status_code_y" in response.text[:20000] else "tekshirilgan",
    }


ARTICLE_RE = re.compile(r"^\s*(\d{1,4}(?:-\d{1,3})?)-modda\b", re.IGNORECASE)


def split_chunks(text: str, max_len: int = 1100) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current = {"article": "", "heading": "", "content": ""}
    for line in text.splitlines():
        match = ARTICLE_RE.match(line)
        if match:
            if current["content"].strip():
                sections.append(current)
            current = {"article": f"{match.group(1)}-modda", "heading": line[:300], "content": line}
            continue
        if not current["heading"] and len(line) < 200:
            current["heading"] = line[:300]
        current["content"] = (current["content"] + "\n" + line).strip()
    if current["content"].strip():
        sections.append(current)
    chunks: list[dict[str, str]] = []
    for section in sections:
        content = section["content"].strip()
        if not content:
            continue
        if len(content) <= max_len:
            chunks.append(section)
            continue
        paragraphs = [p for p in content.split("\n") if p.strip()]
        buffer = ""
        for paragraph in paragraphs:
            if len(buffer) + len(paragraph) + 1 > max_len and buffer:
                chunks.append({**section, "content": buffer.strip()})
                buffer = paragraph
            else:
                buffer = f"{buffer}\n{paragraph}".strip()
        if buffer:
            chunks.append({**section, "content": buffer.strip()})
    return chunks or [{"article": "", "heading": text[:120], "content": text[:max_len]}]


def ingest_document(db: Session, url: str, *, actor: str | None = None) -> LegislationDocument:
    payload = fetch_document(url)
    document = db.execute(
        select(LegislationDocument).where(LegislationDocument.source_url == payload["url"])
    ).scalar_one_or_none()
    if document is None:
        document = LegislationDocument(source_url=payload["url"], title=payload["title"])
        db.add(document)
        db.flush()
    document.title = payload["title"]
    document.number = payload["number"] or document.number
    document.doc_type = payload["doc_type"] or document.doc_type
    document.adoption_date = payload["adoption_date"] or document.adoption_date
    document.effective_date = payload["effective_date"] or document.effective_date
    document.legal_status = payload["legal_status"]
    document.retrieved_at = datetime.now(timezone.utc)
    document.content_hash = payload["content_hash"]
    document.version_identifier = payload["content_hash"][:16]
    document.raw_html = payload["raw_html"]
    db.flush()
    versions = db.execute(
        select(LegislationVersion).where(LegislationVersion.document_id == document.id)
    ).scalars().all()
    for version in versions:
        version.is_current = False
    version = LegislationVersion(
        document_id=document.id,
        version_label=document.version_identifier,
        content_hash=document.content_hash,
        raw_text=payload["text"],
        retrieved_at=document.retrieved_at,
        is_current=True,
    )
    db.add(version)
    db.flush()
    db.execute(
        LegislationChunk.__table__.delete().where(LegislationChunk.document_id == document.id)
    )
    for index, chunk in enumerate(split_chunks(payload["text"])):
        db.add(
            LegislationChunk(
                document_id=document.id,
                version_id=version.id,
                article=chunk["article"],
                heading=chunk["heading"],
                content=chunk["content"],
                chunk_index=index,
                search_text=f"{document.title} {chunk['article']} {chunk['heading']} {chunk['content']}".lower(),
            )
        )
    write_audit(
        db,
        action="legislation.synced",
        entity_type="legislation_document",
        entity_id=document.id,
        actor_id=actor,
        new_value={"title": document.title, "url": document.source_url, "chunks": index + 1},
    )
    db.commit()
    db.refresh(document)
    return document


def sync_query(db: Session, query: str, limit: int = 3, actor: str | None = None) -> list[LegislationDocument]:
    results = search_lex(query, limit=limit)
    documents: list[LegislationDocument] = []
    errors: list[str] = []
    for item in results:
        try:
            documents.append(ingest_document(db, item["url"], actor=actor))
        except Exception as error:  # one broken page must not stop the batch
            db.rollback()
            errors.append(f"{item['title'][:80]}: {error}")
    if not documents and errors:
        raise service_unavailable("Lex.uz hujjatlari yuklanmadi. " + " | ".join(errors[:2]))
    return documents


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zʻʼ\u2019']{3,}", (text or "").lower())
        if token not in STOP
    ]


def search_chunks(db: Session, query: str, limit: int = 6) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    if not tokens:
        return []
    rows = db.execute(
        select(LegislationChunk, LegislationDocument)
        .join(LegislationDocument, LegislationDocument.id == LegislationChunk.document_id)
        .where(LegislationDocument.legal_status.notin_(["arxivlangan"]))
    ).all()
    scored: list[dict[str, Any]] = []
    phrase = " ".join(tokens)
    for chunk, document in rows:
        haystack = (chunk.search_text or f"{chunk.heading} {chunk.content}").lower()
        score = 0.0
        matched = 0
        for token in set(tokens):
            count = haystack.count(token)
            if count:
                matched += 1
                score += 1.0 + min(count, 6) * 0.25
        if not matched:
            continue
        if phrase and phrase in haystack:
            score += 6.0
        if len(tokens) > 1:
            coverage = matched / len(set(tokens))
            score *= 1.0 + coverage
        scored.append(
            {
                "document": legislation_document_out(document),
                "chunk": {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "article": chunk.article,
                    "heading": chunk.heading,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                },
                "score": round(score, 2),
                "match": "keyword",
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def document_detail(db: Session, document_id: str) -> dict[str, Any]:
    document = db.get(LegislationDocument, document_id)
    if document is None:
        raise not_found("Qonunchilik hujjati topilmadi.")
    chunks = db.execute(
        select(LegislationChunk)
        .where(LegislationChunk.document_id == document_id)
        .order_by(LegislationChunk.chunk_index)
    ).scalars().all()
    return {
        "document": legislation_document_out(document),
        "chunks": [
            {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "article": chunk.article,
                "heading": chunk.heading,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ],
        "source_url": document.source_url,
    }


SYSTEM = """Siz O'zbekiston qonunchiligi bo'yicha mahalla xodimi uchun yuridik tahlilchi assistentsiz.
Faqat o'zbek lotin tilida yozing. Faqat BERILGAN manbalar asosida ishlang.

JAVOB STRUKTURASI (majburiy, aynan shu sarlavhalar bilan):
1. «JAVOB:» — savolga to'g'ridan-to'g'ri aniq javob bering (Ha / Yo'q / Shartli — va 1-2 gapda mohiyati). Umuman javob bermang deb aytmang.
2. «ASOS:» — bu xulosani qaysi norma beradi; manbadan matnni O'ZGARTIRMASDAN iqtibos keltiring («...» qo'shtirnoq ichida) va manba raqamini ko'rsating [1]. Ikkita asosiy manba bo'lsa, ikkalasidan qisqa iqtibos keltiring.
3. «IZOH:» — qo'shimcha shartlar, istisnolar yoki cheklovlar (agar manbalarda mavjud bo'lsa). Agar manbalar savolning barcha jihatlarini yopmasa, qaysi qism aniq asoslangan va qaysi qism rasmiy tasdiq talab qilishini ochiq ajratib ko'rsating.

QAT'IY QOIDALAR:
- Iqtibos faqat manbada AYNAN yozilgan matndan bo'lishi shart; o'zingiz matn tuzmang.
- O'ylab topilgan modda raqami, muddat, summa yozmang — manbada bo'lsa keltiring, bo'lmasa yozmang.
- Manbalar asosida mantiqiy xulosa chiqarishga intiling: masalan, ta'rif normasi bor bo'lsa, uni savol holatiga qo'llab aniq javob bering.
- «Javob yo'q» kabi umumiy rad etish yozmang — eng yaqin amaldagi normani keltirib, chegarasini tushuntiring.
- Oxirida doim: "Rasmiy tasdiq uchun Lex.uz dagi amaldagi tahrirni tekshiring."
- Umumiy hajm: 6-10 gap."""


def ask(db: Session, question: str, *, use_ai: bool = True, sync_if_empty: bool = True) -> dict[str, Any]:
    question = (question or "").strip()
    if len(question) < 3:
        raise bad_request("Savol matni juda qisqa.")
    hits = search_chunks(db, question, limit=8)
    synced: list[str] = []
    warnings: list[str] = []
    if not hits and sync_if_empty:
        try:
            documents = sync_query(db, question, limit=3)
            synced = [document.title for document in documents]
            hits = search_chunks(db, question, limit=8)
        except Exception as error:
            warnings.append(f"Lex.uz dan jonli yuklash amalga oshmadi: {error}")
    documents = []
    seen = set()
    for hit in hits:
        if hit["document"]["id"] not in seen:
            seen.add(hit["document"]["id"])
            documents.append(hit["document"])
    if not hits:
        answer = (
            "Taqdim etilgan manbalarda bu savolga to'liq javob topilmadi. "
            "Lex.uz bo'yicha qidiruvni aniqroq so'z bilan qayta yuboring yoki "
            "Qonunchilik bo'limida hujjatni sinxronlashtiring."
        )
        return {
            "answer": answer,
            "sources": [],
            "documents": documents,
            "warnings": warnings,
            "verified": False,
            "retrieved_at": datetime.now(timezone.utc),
            "synced": synced,
        }
    context_parts = []
    sources = []
    for index, hit in enumerate(hits, start=1):
        document = hit["document"]
        chunk = hit["chunk"]
        sources.append(
            {
                "index": index,
                "document_id": document["id"],
                "title": document["title"],
                "number": document["number"],
                "article": chunk["article"],
                "url": document["source_url"],
                "retrieved_at": document["retrieved_at"],
                "excerpt": chunk["content"][:240],
            }
        )
        context_parts.append(
            f"[{index}] {document['title']} ({document['number'] or 'raqamsiz'}), "
            f"{chunk['article'] or 'umumiy qoida'}:\n{chunk['content'][:1600]}"
        )
    context = "\n\n".join(context_parts)
    answer = ""
    verified = False
    if use_ai:
        try:
            result = ai_gateway.chat_completion(
                db,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": f"Savol: {question}\n\nManbalar:\n{context}",
                    },
                ],
                agent="legislation",
                max_tokens=1600,
                temperature=0.1,
            )
            answer = result.content.strip()
            verified = True
        except Exception as error:
            warnings.append(f"AI javobi olinmadi, manbalar ko'rsatildi: {error}")
    if not answer:
        best = hits[0]
        answer = (
            f"Topilgan manba: {best['document']['title']} "
            f"({best['chunk']['article'] or 'umumiy qoida'}).\n\n"
            f"{best['chunk']['content'][:900]}\n\n"
            "Rasmiy tasdiq uchun Lex.uz dagi amaldagi tahrirni tekshiring."
        )
    return {
        "answer": answer,
        "sources": sources,
        "documents": documents,
        "warnings": warnings,
        "verified": verified,
        "retrieved_at": datetime.now(timezone.utc),
        "synced": synced,
    }


def list_documents(db: Session, q: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    stmt = select(LegislationDocument).order_by(LegislationDocument.retrieved_at.desc()).limit(limit)
    if q:
        stmt = stmt.where(LegislationDocument.title.ilike(f"%{q.strip()}%"))
    rows = db.execute(stmt).scalars().all()
    counts = dict(
        db.execute(
            select(LegislationChunk.document_id, func.count())
            .where(LegislationChunk.document_id.in_([row.id for row in rows]))
            .group_by(LegislationChunk.document_id)
        ).all()
    ) if rows else {}
    return [
        {**legislation_document_out(row), "chunk_count": int(counts.get(row.id, 0))}
        for row in rows
    ]


def status(db: Session) -> dict[str, Any]:
    documents = int(
        db.execute(select(func.count()).select_from(LegislationDocument)).scalar_one()
    )
    chunks = int(db.execute(select(func.count()).select_from(LegislationChunk)).scalar_one())
    last = db.execute(select(func.max(LegislationDocument.retrieved_at))).scalar_one()
    return {
        "documents": documents,
        "chunks": chunks,
        "last_synced_at": last,
        "source": "lex.uz",
        "live": True,
    }
