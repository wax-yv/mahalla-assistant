from __future__ import annotations

PERMISSIONS: tuple[str, ...] = (
    "citizens.read",
    "citizens.create",
    "citizens.update",
    "citizens.archive",
    "families.read",
    "families.update",
    "tasks.read",
    "tasks.create",
    "tasks.update",
    "tasks.complete",
    "documents.read",
    "documents.import",
    "documents.export",
    "reports.read",
    "reports.generate",
    "reports.approve",
    "reports.export",
    "agents.use",
    "agents.configure",
    "settings.manage",
    "audit.read",
)

CASE_STATUSES = ("open", "in_progress", "waiting", "resolved", "closed", "cancelled")
CASE_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "waiting", "resolved", "cancelled"},
    "in_progress": {"waiting", "resolved", "cancelled"},
    "waiting": {"in_progress", "resolved", "cancelled"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
    "cancelled": set(),
}

TASK_STATUSES = ("new", "in_progress", "waiting", "completed", "cancelled")
TASK_TRANSITIONS: dict[str, set[str]] = {
    "new": {"in_progress", "waiting", "completed", "cancelled"},
    "in_progress": {"waiting", "completed", "cancelled"},
    "waiting": {"in_progress", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

PRIORITIES = ("low", "normal", "high", "urgent")
EMPLOYMENT_STATUSES = ("Ishlaydi", "Ishsiz", "Ishlamaydi", "O'qiydi", "Tadbirkor", "Pensioner")
EDUCATION_LEVELS = ("Maktabgacha", "Maktab o'quvchisi", "O'rta", "O'rta maxsus", "Oliy")
FAMILY_TYPES = (
    "To'liq oila",
    "To'liq bo'lmagan oila (ona)",
    "To'liq bo'lmagan oila (ota)",
    "To'liq bo'lmagan oila (ona), uch avlod",
    "To'liq bo'lmagan oila (ota), uch avlod",
    "Uch avlodli oila",
    "Yosh er-xotin",
    "Keksa er-xotin",
)
SOCIAL_STATUSES = (
    "Yo'q",
    "Ko'p bolali oila",
    "To'liq bo'lmagan oila",
    "Kam ta'minlangan oila",
    "Ayollar daftari",
    "Yoshlar daftari",
    "Temir daftar",
    "Nogironligi bor (I guruh)",
    "Nogironligi bor (II guruh)",
    "Nogironligi bor (III guruh)",
    "Mehnat faxriysi",
    "Ijtimoiy himoyaga muhtoj",
)
NEEDS = (
    "Yo'q",
    "Ish",
    "Ta'lim yordami",
    "Kasb-hunarga o'qitish",
    "Ijtimoiy yordam",
    "Tibbiy yordam",
    "Tibbiy yordam, reabilitatsiya",
    "Kredit",
    "Kredit (uy-joy, iste'mol)",
    "Tadbirkorlik krediti",
    "Ta'lim kontrakti krediti",
    "Subsidiya",
    "Uy-joy sharoitini yaxshilash",
    "Ish, subsidiya",
    "Ijtimoiy yordam, subsidiya",
)

WORK_LOG_TYPES = (
    "murojaat",
    "uchrashuv",
    "telefon",
    "tavsiya",
    "hujjat",
    "vazifa",
    "bajarilgan ish",
    "natija",
    "keyingi qadam",
)

DOCUMENT_KINDS = ("xlsx", "csv", "docx", "pdf", "generated")
DOCUMENT_STATUSES = ("uploaded", "parsed", "validated", "committed", "failed", "archived")
IMPORT_STATUSES = ("uploaded", "mapping", "validated", "committed", "failed", "rolled_back")

REPORT_TYPES = (
    "daily",
    "weekly",
    "monthly",
    "employment",
    "unemployed",
    "education",
    "social",
    "needs",
    "territory",
    "cases",
    "tasks",
    "overdue",
    "data_quality",
)

PROGRAM_TYPES = ("credit", "subsidy", "grant", "benefit")
PROGRAM_STATUSES = ("verified", "stale", "unavailable")

DRAFT_ACTION_TYPES = (
    "create_task",
    "update_task_status",
    "create_case",
    "create_work_log",
    "generate_report",
    "commit_import",
)

AGENT_NAMES = (
    "document",
    "reporting",
    "legislation",
    "credit_subsidy",
    "plan_control",
)

INTENTS = (
    "citizen_lookup",
    "greeting",
    "document",
    "reporting",
    "data_stats",
    "agent_status",
    "legislation",
    "credit_subsidy",
    "plan_control",
    "multi",
    "smalltalk",
)

CONFIDENCE_LEVELS = ("high", "medium", "needs_review", "low")
