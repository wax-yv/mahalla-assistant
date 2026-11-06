from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class MessageResponse(BaseModel):
    message: str
    ok: bool = True

class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] = []
    request_id: str | None = None

class ErrorResponse(BaseModel):
    error: ErrorBody

class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=2, max_length=200)

class UserOut(ORMModel):
    id: str
    username: str
    display_name: str
    role: str
    permissions: list[str] = []
    is_active: bool
    last_login_at: datetime | None = None

class MeResponse(BaseModel):
    user: UserOut
    csrf_token: str
    demo_mode: bool
    version: str

class AddressOut(BaseModel):
    mahalla_id: str | None = None
    mahalla: str | None = None
    street_id: str | None = None
    street: str | None = None
    house_id: str | None = None
    house_number: str | None = None
    address_label: str | None = None

class MahallaOut(ORMModel):
    id: str
    name: str
    district: str
    region: str
    street_count: int = 0
    house_count: int = 0
    family_count: int = 0
    citizen_count: int = 0

class StreetOut(ORMModel):
    id: str
    mahalla_id: str
    name: str
    house_count: int = 0
    family_count: int = 0
    citizen_count: int = 0

class HouseOut(ORMModel):
    id: str
    street_id: str
    house_number: str
    address_label: str
    family_count: int = 0
    citizen_count: int = 0

class FamilyOut(ORMModel):
    id: str
    house_id: str
    family_head_citizen_id: str | None = None
    family_head_name: str | None = None
    family_type: str
    social_status: str
    member_count: int = 0
    notes: str = ""
    address: AddressOut | None = None
    version: int = 1

class FamilyDetail(FamilyOut):
    members: list[CitizenOut] = []
    cases: list[CaseOut] = []
    tasks: list[TaskOut] = []
    work_logs: list[WorkLogOut] = []

class DataQualityOut(BaseModel):
    score: int = Field(ge=0, le=100)
    missing_fields: list[str] = []
    duplicate_risk: str = "low"
    notes: str = ""

class CitizenOut(ORMModel):
    id: str
    family_id: str | None = None
    full_name: str
    gender: str
    birth_date: date | None = None
    age: int | None = None
    phone: str = ""
    family_role: str = "Farzand"
    education: str = ""
    employment_status: str = ""
    profession: str = ""
    social_status: str = ""
    needs: list[str] = []
    notes: str = ""
    data_source: str = "demo_seed"
    last_verified_at: datetime | None = None
    archived_at: datetime | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    address: AddressOut | None = None
    family: FamilyOut | None = None
    data_quality: DataQualityOut | None = None

class CitizenDetail(CitizenOut):
    cases: list[CaseOut] = []
    tasks: list[TaskOut] = []
    work_logs: list[WorkLogOut] = []
    documents: list[DocumentOut] = []
    timeline: list[TimelineItem] = []
    audit_history: list[AuditOut] = []

class CitizenCreate(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)
    gender: Literal["Erkak", "Ayol"]
    birth_date: date | None = None
    phone: str = Field(default="", max_length=40)
    family_id: str | None = None
    family_role: str = "Farzand"
    education: str = "O'rta"
    employment_status: str = "Ishlamaydi"
    profession: str = "Yo'q"
    social_status: str = "Yo'q"
    needs: list[str] = []
    notes: str = ""

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith("+"):
            value = "+" + value
        return value

class CitizenUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=200)
    gender: Literal["Erkak", "Ayol"] | None = None
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    family_id: str | None = None
    family_role: str | None = None
    education: str | None = None
    employment_status: str | None = None
    profession: str | None = None
    social_status: str | None = None
    needs: list[str] | None = None
    notes: str | None = None
    version: int

class FamilyCreate(BaseModel):
    house_id: str
    family_head_citizen_id: str | None = None
    family_type: str = "To'liq oila"
    social_status: str = "Yo'q"
    notes: str = ""

class FamilyUpdate(BaseModel):
    family_head_citizen_id: str | None = None
    family_type: str | None = None
    social_status: str | None = None
    notes: str | None = None
    version: int

class CaseOut(ORMModel):
    id: str
    citizen_id: str | None = None
    family_id: str | None = None
    citizen_name: str | None = None
    category: str
    title: str
    description: str = ""
    opened_at: datetime
    status: str
    priority: str
    responsible_user: str | None = None
    target_date: date | None = None
    outcome: str = ""
    closed_at: datetime | None = None
    evidence_refs: list[Any] = []
    version: int = 1
    created_at: datetime
    updated_at: datetime
    task_count: int = 0

class CaseCreate(BaseModel):
    citizen_id: str | None = None
    family_id: str | None = None
    category: str = "Boshqa"
    title: str = Field(min_length=3, max_length=240)
    description: str = ""
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    responsible_user: str | None = None
    target_date: date | None = None

class CaseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    status: str | None = None
    responsible_user: str | None = None
    target_date: date | None = None
    outcome: str | None = None
    version: int

class TaskOut(ORMModel):
    id: str
    title: str
    description: str = ""
    citizen_id: str | None = None
    citizen_name: str | None = None
    family_id: str | None = None
    case_id: str | None = None
    category: str
    priority: str
    status: str
    due_date: date | None = None
    assignee: str | None = None
    completed_at: datetime | None = None
    evidence_note: str = ""
    evidence_document_id: str | None = None
    is_overdue: bool = False
    days_until_due: int | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime

class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = ""
    citizen_id: str | None = None
    family_id: str | None = None
    case_id: str | None = None
    category: str = "Boshqa"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_date: date | None = None
    assignee: str | None = None

class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    status: str | None = None
    due_date: date | None = None
    assignee: str | None = None
    version: int

class TaskCompleteRequest(BaseModel):
    evidence_note: str = Field(min_length=3, max_length=4000)
    evidence_document_id: str | None = None
    version: int | None = None

class WorkLogOut(ORMModel):
    id: str
    citizen_id: str | None = None
    family_id: str | None = None
    case_id: str | None = None
    task_id: str | None = None
    type: str
    title: str
    description: str = ""
    occurred_at: datetime
    author_id: str | None = None
    source: str
    approval_status: str
    created_at: datetime

class WorkLogCreate(BaseModel):
    citizen_id: str | None = None
    family_id: str | None = None
    case_id: str | None = None
    task_id: str | None = None
    type: str = "murojaat"
    title: str = Field(min_length=3, max_length=240)
    description: str = ""
    occurred_at: datetime | None = None

class TimelineItem(BaseModel):
    id: str
    kind: str
    title: str
    description: str = ""
    occurred_at: datetime
    status: str | None = None
    entity_type: str
    entity_id: str
    source: str = "database"

class DocumentOut(ORMModel):
    id: str
    filename: str
    original_name: str
    mime_type: str
    size: int
    content_hash: str
    storage_backend: str
    kind: str
    status: str
    meta: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

class ImportErrorOut(ORMModel):
    id: str
    row_number: int
    column: str | None = None
    code: str
    message: str
    raw_value: str | None = None
    severity: str

class ImportBatchOut(ORMModel):
    id: str
    document_id: str
    module: str
    status: str
    mapping: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    error_count: int = 0
    warning_count: int = 0
    created_at: datetime
    updated_at: datetime
    committed_at: datetime | None = None
    rolled_back_at: datetime | None = None

class ImportPreview(BaseModel):
    batch: ImportBatchOut
    headers: list[str] = []
    mapping: dict[str, str] = {}
    detected_module: str = "citizens"
    preview_rows: list[dict[str, Any]] = []
    errors: list[ImportErrorOut] = []
    warnings: list[ImportErrorOut] = []
    summary: dict[str, Any] = {}
    can_commit: bool = False

class ImportCommitRequest(BaseModel):
    mapping: dict[str, str] | None = None
    idempotency_key: str | None = None
    sheet: str | None = None

class ExportRequest(BaseModel):
    module: Literal["citizens", "families", "houses", "cases", "tasks", "report"] = "citizens"
    format: Literal["xlsx", "csv", "docx", "pdf"] = "xlsx"
    fields: list[str] | None = None
    filters: dict[str, Any] = {}
    report_id: str | None = None

class ReportOut(ORMModel):
    id: str
    type: str
    period_start: date
    period_end: date
    filters: dict[str, Any] = {}
    status: str
    title: str
    summary: str
    metrics: dict[str, Any] = {}
    narrative: str
    sources: list[Any] = []
    created_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

class ReportGenerateRequest(BaseModel):
    type: str = "daily"
    period_start: date | None = None
    period_end: date | None = None
    filters: dict[str, Any] = {}

class ReportApproveRequest(BaseModel):
    note: str = ""

class ChatRequest(BaseModel):
    # E-band: suhbat xabari uzunligi cheklangan — AI suiiste'mol va
    # prompt hajmi hujumiga qarshi.
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    model: str | None = None
    provider: str | None = None
    context: dict[str, Any] = {}

class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageOut
    workflow_id: str
    intent: str
    agents_used: list[str] = []
    sources: list[Any] = []
    draft_actions: list[DraftActionOut] = []
    warnings: list[str] = []
    requires_approval: bool = False

class MessageOut(ORMModel):
    id: str
    conversation_id: str
    role: str
    content: str
    agent: str | None = None
    workflow_id: str | None = None
    sources: list[Any] = []
    draft_actions: list[Any] = []
    created_at: datetime

class ConversationOut(ORMModel):
    id: str
    title: str
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: str | None = None

class DraftActionOut(ORMModel):
    id: str
    workflow_id: str
    run_id: str | None = None
    action_type: str
    payload: dict[str, Any]
    status: str
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    result: dict[str, Any] = {}
    error: str = ""

class AgentRunOut(ORMModel):
    id: str
    workflow_id: str
    agent: str
    task: str
    status: str
    input: dict[str, Any] = {}
    output: dict[str, Any] = {}
    sources: list[Any] = []
    evidence_refs: list[Any] = []
    warnings: list[str] = []
    confidence: str
    proposed_actions: list[Any] = []
    model: str
    provider: str
    latency_ms: int
    token_input: int
    token_output: int
    error: str
    started_at: datetime
    finished_at: datetime | None = None

class WorkflowOut(ORMModel):
    id: str
    request_id: str
    conversation_id: str | None = None
    intent: str
    status: str
    input: dict[str, Any] = {}
    result: dict[str, Any] = {}
    error: str
    requires_approval: bool
    created_at: datetime
    updated_at: datetime
    runs: list[AgentRunOut] = []

class AgentInfo(BaseModel):
    name: str
    label: str
    description: str
    enabled: bool = True
    provider: str = ""
    model: str = ""
    last_run_at: datetime | None = None
    last_status: str = "idle"
    latency_ms: int = 0
    tokens_today: int = 0
    success_rate: float = 0.0
    fallback_used: bool = False
    allowed_tools: list[str] = []

class ModelInfo(BaseModel):
    id: str
    provider: str
    label: str
    context: int = 0
    free: bool = True
    capabilities: list[str] = []
    rank: int = 0

class AgentStatusResponse(BaseModel):
    agents: list[AgentInfo]
    models: list[ModelInfo]
    budget: dict[str, Any] = {}

class LegislationDocumentOut(ORMModel):
    id: str
    source_url: str
    title: str
    number: str
    doc_type: str
    adoption_date: date | None = None
    effective_date: date | None = None
    last_revision_date: date | None = None
    legal_status: str
    retrieved_at: datetime
    content_hash: str
    version_identifier: str

class LegislationChunkOut(ORMModel):
    id: str
    document_id: str
    article: str
    heading: str
    content: str
    chunk_index: int

class LegislationSearchItem(BaseModel):
    document: LegislationDocumentOut
    chunk: LegislationChunkOut
    score: float = 0.0
    match: str = "keyword"

class LegislationAnswer(BaseModel):
    answer: str
    sources: list[Any] = []
    documents: list[LegislationDocumentOut] = []
    warnings: list[str] = []
    verified: bool = False
    retrieved_at: datetime | None = None

class LegislationSyncRequest(BaseModel):
    query: str | None = None
    url: str | None = None
    limit: int = 5

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        from app.core.urls import validate_lex_url

        return validate_lex_url(value)

class ProgramOut(ORMModel):
    id: str
    name: str
    type: str
    organization: str
    target_group: str
    region: str
    eligibility: dict[str, Any] = {}
    amount: str
    interest_rate: str
    term_months: str
    grace_period: str
    required_documents: list[str] = []
    application_channel: str
    official_url: str
    valid_from: date | None = None
    valid_to: date | None = None
    last_verified_at: datetime | None = None
    status: str
    notes: str
    stale: bool = False

class ProgramMatch(BaseModel):
    program_id: str
    program_name: str
    result: Literal["mos kelishi mumkin", "mos kelmaydi", "ma'lumot yetarli emas"]
    reasons: list[str] = []
    missing_fields: list[str] = []
    verified_at: datetime | None = None
    source_url: str = ""

class ProgramMatchRequest(BaseModel):
    citizen_id: str
    program_id: str | None = None

class ProgramCompareRequest(BaseModel):
    program_ids: list[str]

class DashboardMetric(BaseModel):
    key: str
    label: str
    value: int | float | str
    change: float | None = None
    hint: str | None = None

class ActivityItem(BaseModel):
    id: str
    action: str
    title: str
    description: str = ""
    actor: str = "Administrator"
    entity_type: str
    entity_id: str | None = None
    created_at: datetime
    tone: str = "neutral"

class DashboardSummary(BaseModel):
    metrics: list[DashboardMetric] = []
    employment: list[dict[str, Any]] = []
    social: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    streets: list[dict[str, Any]] = []
    today_tasks: list[TaskOut] = []
    overdue_tasks: list[TaskOut] = []
    open_cases: list[CaseOut] = []
    recent_activity: list[ActivityItem] = []
    data_quality: dict[str, Any] = {}
    as_of: datetime
    timezone: str = "Asia/Tashkent"

class AuditOut(ORMModel):
    id: str
    actor_type: str
    actor_id: str | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    request_id: str | None = None
    workflow_id: str | None = None
    source: str
    ip: str | None = None
    result: str
    created_at: datetime

class AppSettingsOut(BaseModel):
    theme: str = "system"
    language: str = "uz-Latn"
    timezone: str = "Asia/Tashkent"
    ai_provider: str = "nvidia"
    ai_model: str = ""
    ai_budget: int = 300000
    agents_enabled: dict[str, bool] = {}
    scheduler_time: str = "21:00"
    backup_status: str = "unknown"
    demo_mode: bool = True
    mahalla: str = "Navbahor mahallasi"
    district: str = "Urganch shahri"
    region: str = "Xorazm viloyati"

class AppSettingsUpdate(BaseModel):
    theme: str | None = None
    language: str | None = None
    timezone: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_budget: int | None = None
    agents_enabled: dict[str, bool] | None = None
    scheduler_time: str | None = None
    demo_mode: bool | None = None
    mahalla: str | None = None
    district: str | None = None
    region: str | None = None

class HealthResponse(BaseModel):
    status: str
    version: str
    database: bool
    ai_provider: str
    demo_mode: bool
    timezone: str
    timestamp: datetime

class PageMetaOut(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int

class PagedResponse(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMetaOut
