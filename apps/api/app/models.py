from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType, utcnow


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}-{value}" if prefix else value


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("USR"))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160), default="Administrator")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    permissions: Mapped[list] = mapped_column(JSONType, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("SES"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship("User")


class RateLimit(Base):
    __tablename__ = "rate_limits"
    __table_args__ = (UniqueConstraint("key", "window_start", name="uq_rate_limit_key_window"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer, default=0)


class Mahalla(Base):
    __tablename__ = "mahallas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("MAH"))
    name: Mapped[str] = mapped_column(String(160), index=True)
    district: Mapped[str] = mapped_column(String(160), default="Urganch shahri")
    region: Mapped[str] = mapped_column(String(160), default="Xorazm viloyati")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    streets: Mapped[list[Street]] = relationship("Street", back_populates="mahalla")


class Street(Base):
    __tablename__ = "streets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("KO"))
    mahalla_id: Mapped[str] = mapped_column(ForeignKey("mahallas.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    mahalla: Mapped[Mahalla] = relationship("Mahalla", back_populates="streets")
    houses: Mapped[list[House]] = relationship("House", back_populates="street")


class House(Base):
    __tablename__ = "houses"
    __table_args__ = (UniqueConstraint("street_id", "house_number", name="uq_house_street_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("UY"))
    street_id: Mapped[str] = mapped_column(ForeignKey("streets.id", ondelete="RESTRICT"), index=True)
    house_number: Mapped[str] = mapped_column(String(32))
    address_label: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    street: Mapped[Street] = relationship("Street", back_populates="houses")
    families: Mapped[list[Family]] = relationship("Family", back_populates="house")


class Family(Base):
    __tablename__ = "families"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("OIL"))
    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="RESTRICT"), index=True)
    family_head_citizen_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), nullable=True
    )
    family_type: Mapped[str] = mapped_column(String(64), default="To'liq oila")
    social_status: Mapped[str] = mapped_column(String(64), default="Yo'q")
    notes: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    house: Mapped[House] = relationship("House", back_populates="families")
    head: Mapped[Optional[Citizen]] = relationship(
        "Citizen", foreign_keys=[family_head_citizen_id], post_update=True
    )
    members: Mapped[list[Citizen]] = relationship(
        "Citizen", back_populates="family", foreign_keys="Citizen.family_id"
    )


class Citizen(Base):
    __tablename__ = "citizens"
    __table_args__ = (
        Index("ix_citizens_name", "full_name"),
        Index("ix_citizens_phone", "phone"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("F"))
    family_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    gender: Mapped[str] = mapped_column(String(16), default="Erkak")
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    family_role: Mapped[str] = mapped_column(String(32), default="Farzand")
    education: Mapped[str] = mapped_column(String(64), default="O'rta")
    employment_status: Mapped[str] = mapped_column(String(64), default="Ishlamaydi", index=True)
    profession: Mapped[str] = mapped_column(String(120), default="Yo'q")
    social_status: Mapped[str] = mapped_column(String(64), default="Yo'q", index=True)
    needs: Mapped[list] = mapped_column(JSONType, default=list)
    needs_text: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    data_source: Mapped[str] = mapped_column(String(255), default="demo_seed")
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    family: Mapped[Optional[Family]] = relationship(
        "Family", back_populates="members", foreign_keys=[family_id]
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("CASE"))
    citizen_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    family_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(80), default="Boshqa")
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    responsible_user: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, default="")
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSONType, default=list)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    citizen: Mapped[Optional[Citizen]] = relationship("Citizen", foreign_keys=[citizen_id])
    family: Mapped[Optional[Family]] = relationship("Family", foreign_keys=[family_id])


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("TASK"))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    citizen_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    family_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(80), default="Boshqa")
    priority: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    assignee: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_note: Mapped[str] = mapped_column(Text, default="")
    evidence_document_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    citizen: Mapped[Optional[Citizen]] = relationship("Citizen", foreign_keys=[citizen_id])
    family: Mapped[Optional[Family]] = relationship("Family", foreign_keys=[family_id])
    case: Mapped[Optional[Case]] = relationship("Case", foreign_keys=[case_id])


class WorkLog(Base):
    __tablename__ = "work_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("WL"))
    citizen_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citizens.id", ondelete="SET NULL"), nullable=True, index=True
    )
    family_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True, index=True
    )
    case_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(40), default="murojaat", index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    approval_status: Mapped[str] = mapped_column(String(32), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    citizen: Mapped[Optional[Citizen]] = relationship("Citizen", foreign_keys=[citizen_id])
    case: Mapped[Optional[Case]] = relationship("Case", foreign_keys=[case_id])
    task: Mapped[Optional[Task]] = relationship("Task", foreign_keys=[task_id])


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("DOC"))
    filename: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    storage_backend: Mapped[str] = mapped_column(String(32), default="database")
    storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="pdf")
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    blob: Mapped[Optional[DocumentBlob]] = relationship(
        "DocumentBlob", back_populates="document", cascade="all, delete-orphan", uselist=False
    )


class DocumentBlob(Base):
    __tablename__ = "document_blobs"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[bytes] = mapped_column(LargeBinary)

    document: Mapped[Document] = relationship("Document", back_populates="blob")


class ImportBatch(Base):
    __tablename__ = "document_import_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("IMP"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    module: Mapped[str] = mapped_column(String(32), default="citizens")
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    mapping: Mapped[dict] = mapped_column(JSONType, default=dict)
    summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[Document] = relationship("Document")
    errors: Mapped[list[ImportError]] = relationship(
        "ImportError", back_populates="batch", cascade="all, delete-orphan"
    )


class ImportError(Base):
    __tablename__ = "document_import_errors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("IMPE"))
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("document_import_batches.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    column: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    code: Mapped[str] = mapped_column(String(64), default="INVALID")
    message: Mapped[str] = mapped_column(Text, default="")
    raw_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="error")

    batch: Mapped[ImportBatch] = relationship("ImportBatch", back_populates="errors")


class ImportChange(Base):
    __tablename__ = "document_import_changes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("IMPC"))
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("document_import_batches.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(16))
    before: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("REP"))
    type: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    filters: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)
    narrative: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSONType, default=list)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("RRUN"))
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(160), default="")


class AgentWorkflow(Base):
    __tablename__ = "agent_workflows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("WF"))
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    intent: Mapped[str] = mapped_column(String(40), default="smalltalk")
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    input: Mapped[dict] = mapped_column(JSONType, default=dict)
    context: Mapped[dict] = mapped_column(JSONType, default=dict)
    result: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("RUN"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agent_workflows.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    task: Mapped[str] = mapped_column(String(120), default="chat")
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    input: Mapped[dict] = mapped_column(JSONType, default=dict)
    output: Mapped[dict] = mapped_column(JSONType, default=dict)
    sources: Mapped[list] = mapped_column(JSONType, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSONType, default=list)
    warnings: Mapped[list] = mapped_column(JSONType, default=list)
    confidence: Mapped[str] = mapped_column(String(32), default="needs_review")
    proposed_actions: Mapped[list] = mapped_column(JSONType, default=list)
    model: Mapped[str] = mapped_column(String(160), default="")
    provider: Mapped[str] = mapped_column(String(40), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("TOOL"))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(120))
    args: Mapped[dict] = mapped_column(JSONType, default=dict)
    result: Mapped[dict] = mapped_column(JSONType, default=dict)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("CONV"))
    title: Mapped[str] = mapped_column(String(240), default="Yangi suhbat")
    # Egasining foydalanuvchi ID'si (NULL — egasi aniqlanmagan, faqat admin ko'radi).
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list[ConversationMessage]] = relationship(
        "ConversationMessage", back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("MSG"))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    agent: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sources: Mapped[list] = mapped_column(JSONType, default=list)
    draft_actions: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")


class DraftAction(Base):
    __tablename__ = "draft_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("DRAFT"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("agent_workflows.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("MEM"))
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="preference")
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict] = mapped_column(JSONType, default=dict)
    source: Mapped[str] = mapped_column(String(64), default="conversation")
    confidence: Mapped[str] = mapped_column(String(32), default="low")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class LegislationDocument(Base):
    __tablename__ = "legislation_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("LEX"))
    source_url: Mapped[str] = mapped_column(String(600), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    number: Mapped[str] = mapped_column(String(120), default="")
    doc_type: Mapped[str] = mapped_column(String(80), default="")
    adoption_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_revision_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    legal_status: Mapped[str] = mapped_column(String(80), default="tekshirilmagan")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    version_identifier: Mapped[str] = mapped_column(String(120), default="")
    raw_html: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LegislationVersion(Base):
    __tablename__ = "legislation_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("LVER"))
    document_id: Mapped[str] = mapped_column(
        ForeignKey("legislation_documents.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(120), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class LegislationChunk(Base):
    __tablename__ = "legislation_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("LCH"))
    document_id: Mapped[str] = mapped_column(
        ForeignKey("legislation_documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("legislation_versions.id", ondelete="CASCADE"), index=True
    )
    article: Mapped[str] = mapped_column(String(160), default="")
    heading: Mapped[str] = mapped_column(String(300), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    search_text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list] = mapped_column(JSONType, default=list)


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("PROG"))
    name: Mapped[str] = mapped_column(String(240), index=True)
    type: Mapped[str] = mapped_column(String(32), default="credit", index=True)
    organization: Mapped[str] = mapped_column(String(240), default="")
    target_group: Mapped[str] = mapped_column(Text, default="")
    region: Mapped[str] = mapped_column(String(160), default="O'zbekiston")
    eligibility: Mapped[dict] = mapped_column(JSONType, default=dict)
    amount: Mapped[str] = mapped_column(String(240), default="")
    interest_rate: Mapped[str] = mapped_column(String(120), default="")
    term_months: Mapped[str] = mapped_column(String(120), default="")
    grace_period: Mapped[str] = mapped_column(String(120), default="")
    required_documents: Mapped[list] = mapped_column(JSONType, default=list)
    application_channel: Mapped[str] = mapped_column(String(240), default="")
    official_url: Mapped[str] = mapped_column(String(600), default="")
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="verified", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProgramSource(Base):
    __tablename__ = "program_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("PSRC"))
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(600))
    title: Mapped[str] = mapped_column(String(240), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="verified")
    notes: Mapped[str] = mapped_column(Text, default="")


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("JOB"))
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80))
    schedule: Mapped[str] = mapped_column(String(120), default="daily")
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("JRUN"))
    job_id: Mapped[str] = mapped_column(ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSONType, default=dict)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("NOTIF"))
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(32), default="info")
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("AUD"))
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), default="api")
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(32), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AIUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("AIU"))
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(160))
    agent: Mapped[str] = mapped_column(String(40), default="", index=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("BAK"))
    kind: Mapped[str] = mapped_column(String(32), default="logical")
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    location: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # J-8: zaxira nusxa baytlari (sha256 `location` da saqlanadi).
    data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
