from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")

class PageMeta(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0

class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

def paginate(db: Session, stmt: Select, page: int, page_size: int) -> tuple[list[Any], PageMeta]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one())
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    total_pages = (total + page_size - 1) // page_size if total else 0
    return list(rows), PageMeta(
        page=page, page_size=page_size, total=total, total_pages=total_pages
    )
