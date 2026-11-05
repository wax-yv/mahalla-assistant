from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import service_unavailable
from app.models import AIUsage

# O-9: registratsiya — (model_id, provider, label, context, rank) tuple'lari.
MODEL_REGISTRY: list[tuple[str, str, str, int, int]] = [
    ("nvidia/nemotron-3-ultra-550b-a55b", "nvidia", "Nemotron 3 Ultra 550B", 1_000_000, 1),
    ("deepseek-ai/deepseek-v4.1-flash", "nvidia", "DeepSeek V4.1 Flash", 128_000, 2),
    ("nvidia/nemotron-3-super-120b-a12b", "nvidia", "Nemotron 3 Super 120B", 1_000_000, 3),
    ("mistralai/mistral-large-4-1t-a52b", "nvidia", "Mistral Large 4", 128_000, 4),
    ("nvidia/nemotron-3-ultra-550b-a55b:free", "openrouter", "Nemotron 3 Ultra (OpenRouter)", 1_000_000, 5),
    ("nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia", "Nemotron 3.5 Super VL", 1_000_000, 6),
    ("thinkingmachines/inkling:free", "openrouter", "Inkling (OpenRouter)", 1_000_000, 7),
    ("nvidia/llama-3.1-nemotron-ultra-253b-v1", "nvidia", "Nemotron Ultra 253B", 128_000, 8),
    ("google/gemma-4-31b-it", "nvidia", "Gemma 4 31B", 256_000, 9),
    ("nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia", "Nemotron 3.5 Lightning", 1_000_000, 10),
    ("google/gemma-4-31b-it:free", "openrouter", "Gemma 4 31B (OpenRouter)", 256_000, 11),
    ("recursive/flint-v1.0:free", "openrouter", "Flint 1.0 (OpenRouter)", 262_144, 12),
]

# O-9: provayderning jonli model ro'yxati keshi (1 soat).
LIVE_MODELS_TTL_SECONDS = 3600
# Texlik bilan tugagan tekshiruvning keshi qisqa (1 daqiqa).
LIVE_MODELS_ERROR_TTL_SECONDS = 60
# (vaqt, ulanganmi, tushuntirish, model_id'lar)
_provider_models_cache: dict[str, tuple[float, bool, str, frozenset[str]]] = {}


@dataclass
class AIResult:
    content: str
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    attempts: list[dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False


def _provider_models(provider: str) -> tuple[bool, str, set[str]]:
    """Provayderning `/models` ro'yxatini oladi (O-9: 1 soat kesh).

    Qaytaradi: (ulanganmi, tushuntirish, model ID'lar). Texlik bo'lsa
    qisqa vaqtli keshga yoziladi — xato bir soat davom etmaydi.
    """
    now = time.monotonic()
    cached = _provider_models_cache.get(provider)
    if cached is not None:
        age = now - cached[0]
        ttl = LIVE_MODELS_TTL_SECONDS if cached[1] else LIVE_MODELS_ERROR_TTL_SECONDS
        if age < ttl:
            return cached[1], cached[2], set(cached[3])
    ok = False
    detail = ""
    ids: set[str] = set()
    try:
        url, headers = _endpoint(provider)
        models_url = url.rsplit("/chat/completions", 1)[0] + "/models"
        with httpx.Client(timeout=8) as client:
            response = client.get(models_url, headers=headers)
        if response.status_code == 200:
            payload = response.json()
            items = payload.get("data") or payload.get("models") or []
            ids = {
                str(item.get("id")).strip()
                for item in items
                if isinstance(item, dict) and item.get("id")
            }
            ok = True
            detail = f"Ulangan — {len(ids)} model mavjud"
        elif response.status_code in (401, 403):
            detail = "API kaliti rad etildi (401/403)"
        else:
            detail = f"Server javobi: HTTP {response.status_code}"
    except httpx.HTTPError as error:
        detail = f"Ulanmadi: {type(error).__name__}"
    except Exception as error:  # pragma: no cover - himoya
        detail = f"Ulanmadi: {type(error).__name__}"
    _provider_models_cache[provider] = (now, ok, detail, frozenset(ids))
    return ok, detail, ids


def _provider_model_ids(provider: str) -> set[str] | None:
    """Provayderning jonli model ID'lari (1 soat kesh).

    `None` — tekshiruv imkonsiz (API kaliti yo'q yoki tarmoq xatosi).
    """
    api_key = (
        settings.nvidia_nim_api_key if provider == "nvidia" else settings.openrouter_api_key
    )
    if not api_key:
        return None
    ok, _detail, ids = _provider_models(provider)
    if not ok or not ids:
        return None
    return ids


def _override_models() -> list[dict[str, Any]]:
    """`AI_MODEL_CONFIG_JSON` override'ini tekshirilgan model ro'yxatiga aylantiradi.

    O-9: har bir element turi va kaliti bo'yicha tekshiriladi — noto'g'ri
    element butun ro'yxatni buzmasligi uchun jimgina o'tkazib yuboriladi.
    """
    override = settings.ai_models_override or {}
    models: list[dict[str, Any]] = []
    for provider, items in override.items():
        if not isinstance(provider, str) or not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            model_id = ""
            label = ""
            context = 0
            if isinstance(item, str):
                model_id = item.strip()
            elif isinstance(item, dict):
                raw_id = item.get("id")
                if not isinstance(raw_id, str):
                    continue
                model_id = raw_id.strip()
                raw_label = item.get("label")
                label = raw_label.strip() if isinstance(raw_label, str) else ""
                raw_context = item.get("context", 0)
                if isinstance(raw_context, bool) or not isinstance(
                    raw_context, (int, float, str)
                ):
                    continue
                try:
                    context = int(raw_context)
                except (TypeError, ValueError):
                    continue
                if context < 0:
                    continue
            else:
                # Ro'yxat, satr yoki dict bo'lmagan element — e'tiborsiz.
                continue
            if not model_id:
                continue
            models.append(
                {
                    "id": model_id,
                    "provider": provider,
                    "label": label or model_id,
                    "context": context,
                    "free": True,
                    "capabilities": ["chat"],
                    "rank": index,
                }
            )
    return models


def resolve_model(models: list[dict[str, Any]], model_id: str) -> str:
    """Model ID faqat ro'yxatda mavjud bo'lsa qabul qilinadi (O-9).

    Mavjud bo'lmagan ID bo'sh qaytariladi — shunda tarmoq so'rovi
    bekor qolmaydi va kechikish paydo bo'lmaydi.
    """
    if not model_id:
        return ""
    known = {str(item.get("id") or "") for item in models}
    return model_id if model_id in known else ""


def available_models() -> list[dict[str, Any]]:
    """Sozlangan model ro'yxati (tarmoq so'rovisiz — so'rov yo'lida tez)."""
    override = settings.ai_models_override or {}
    if override:
        return _override_models()
    models = []
    for model_id, provider, label, context, rank in MODEL_REGISTRY:
        if provider == "nvidia" and not settings.nvidia_nim_api_key:
            continue
        if provider == "openrouter" and not settings.openrouter_api_key:
            continue
        models.append(
            {
                "id": model_id,
                "provider": provider,
                "label": label,
                "context": context,
                "free": True,
                "capabilities": ["chat", "uzbek", "json"],
                "rank": rank,
            }
        )
    return sorted(models, key=lambda item: item["rank"])


def refresh_models() -> list[dict[str, Any]]:
    """Faqat provayderda **mavjud** modellarni qaytaradi (O-9, 1 soat kesh).

    Admin model ro'yxati shundan olinadi — mavjud bo'lmagan model
    tanlanmasligi uchun.
    """
    models = available_models()
    result: list[dict[str, Any]] = []
    for model in models:
        ids = _provider_model_ids(model["provider"])
        if ids is None or model["id"] in ids:
            result.append(model)
    return result


def _live_provider_check(provider: str) -> tuple[bool, str]:
    """Provayder /models endpointini qisqa so'rov bilan tekshirish.

    O-9: so'rov natijasi 1 soat keshlanadi — har chaqiruvda tarmoqga
    chiqilmaydi.
    """
    ok, detail, _ids = _provider_models(provider)
    return ok, detail


def provider_status(live: bool = True) -> list[dict[str, Any]]:
    # O-9: admin ro'yxatida faqat provayderda mavjud modellar ko'rsatiladi.
    models = refresh_models() if live else available_models()
    result = []
    for key, label in (("nvidia", "NVIDIA NIM"), ("openrouter", "OpenRouter")):
        configured = bool(
            settings.nvidia_nim_api_key if key == "nvidia" else settings.openrouter_api_key
        )
        if not configured:
            ok, detail = False, "API kaliti sozlanmagan"
        elif live:
            ok, detail = _live_provider_check(key)
        else:
            ok, detail = True, "Ulangan (tezkor rejim)"
        result.append(
            {
                "id": key,
                "name": label,
                "label": label,
                "configured": configured,
                "ok": ok,
                "detail": detail,
                "model_count": len([m for m in models if m["provider"] == key]),
                "models": [m for m in models if m["provider"] == key],
            }
        )
    return result


def usage_today(db: Session) -> dict[str, int]:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = db.execute(
        select(
            func.coalesce(func.sum(AIUsage.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsage.completion_tokens), 0),
            func.coalesce(func.sum(AIUsage.total_tokens), 0),
            func.count(),
        ).where(AIUsage.created_at >= start)
    ).one()
    total = int(row[2])
    return {
        "prompt_tokens": int(row[0]),
        "completion_tokens": int(row[1]),
        "total_tokens": total,
        "requests": int(row[3]),
        "budget": settings.ai_daily_token_budget,
        "remaining": max(0, settings.ai_daily_token_budget - total),
    }


def _endpoint(provider: str) -> tuple[str, dict[str, str]]:
    if provider == "nvidia":
        return (
            f"{settings.nvidia_nim_base_url.rstrip('/')}/chat/completions",
            {
                "Authorization": f"Bearer {settings.nvidia_nim_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    return (
        f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
        {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": settings.app_base_url,
            "X-Title": "Mahalla Assistant",
        },
    )


def stored_model(db: Session) -> str:
    """Sozlamalarda saqlangan faol model id (bo'sh = registratsiya tartibi)."""
    from app.models import AppSetting

    row = db.get(AppSetting, "app")
    if row is None:
        return ""
    value = (row.value or {}).get("ai_model", "")
    return value if isinstance(value, str) else ""


def order_models(models: list[dict[str, Any]], primary: str) -> list[dict[str, Any]]:
    """Tanlangan modelni zanjir boshiga qo'yadi, qolganlari rank tartibida."""
    chosen = [m for m in models if m["id"] == primary]
    rest = [m for m in models if m["id"] != primary]
    return chosen + rest


def _record_usage(
    *,
    provider: str,
    model: str,
    agent: str,
    workflow_id: str | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    status: str = "success",
) -> None:
    """Token sarfini **alohida sessiyada** yozadi va commit qiladi (J-3).

    Chaqiruvchining tranzaksiyasi rollback bo'lsa ham sarflangan tokenlar
    saqlanib qoladi — kunlik byudjet nazorati ishlaydi.
    """
    from app.core.db import SessionLocal

    def _write(session, link: str | None) -> None:
        session.add(
            AIUsage(
                provider=provider,
                model=model,
                agent=agent,
                workflow_id=link,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                status=status,
            )
        )
        session.commit()

    try:
        with SessionLocal() as session:
            _write(session, workflow_id)
    except Exception:
        # Workflow hali commit qilinmagan bo'lishi mumkin (FK xatosi) —
        # sarfni link-siz yozib qo'yamiz, asosiy javob buzilmasin.
        try:
            with SessionLocal() as session:
                _write(session, None)
        except Exception:
            pass


def chat_completion(
    db: Session,
    *,
    messages: list[dict[str, str]],
    agent: str = "orchestrator",
    workflow_id: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
    preferred_provider: str | None = None,
    preferred_model: str | None = None,
) -> AIResult:
    budget = usage_today(db)
    if budget["remaining"] <= 0:
        raise service_unavailable("Kunlik AI token budjeti tugagan. Sozlamalarda limitni oshiring.")
    candidates = available_models()
    # O-9: faqat ro'yxatda mavjud bo'lgan model tanlanadi — mavjud bo'lmagan
    # ID har chaqiruvda bekor tarmoq so'rovi va kechikish keltirardi.
    active_model = resolve_model(candidates, preferred_model or stored_model(db))
    if active_model:
        candidates = order_models(candidates, active_model)
    if preferred_provider in {"nvidia", "openrouter"}:
        head = [m for m in candidates if m["provider"] == preferred_provider]
        tail = [m for m in candidates if m["provider"] != preferred_provider]
        candidates = head + tail
    if not candidates:
        raise service_unavailable("AI provayderlari sozlanmagan.")

    # J-1: umumiy vaqt chegarasi — 12 model × 55 s = 660 s bo'lishi mumkin emas.
    max_attempts = max(1, settings.ai_max_attempts)
    candidates = candidates[:max_attempts]
    deadline = time.monotonic() + max(5, settings.ai_chain_deadline_seconds)
    attempts: list[dict[str, Any]] = []
    last_error = "Model javob bermadi."
    started_all = time.perf_counter()
    for index, candidate in enumerate(candidates):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            last_error = "AI so'rov vaqti chegarasi tugadi."
            break
        url, headers = _endpoint(candidate["provider"])
        body: dict[str, Any] = {
            "model": candidate["id"],
            "messages": messages,
            "temperature": settings.ai_temperature if temperature is None else max(0.0, min(1.0, temperature)),
            "max_tokens": max_tokens or settings.ai_max_output_tokens,
            "stream": False,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        attempt_timeout = max(3.0, min(float(settings.ai_attempt_timeout_seconds), remaining))
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=attempt_timeout) as client:
                response = client.post(url, headers=headers, json=body)
            elapsed = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                detail = ""
                try:
                    payload = response.json()
                    error = payload.get("error")
                    detail = error.get("message") if isinstance(error, dict) else str(error or payload.get("detail") or "")
                except Exception:
                    detail = response.text[:200]
                attempts.append(
                    {
                        "provider": candidate["provider"],
                        "model": candidate["id"],
                        "status": response.status_code,
                        "error": str(detail)[:300],
                    }
                )
                last_error = f"{candidate['id']}: {response.status_code} {detail}"[:300]
                # J-3: muvaffaqiyatsiz urinish ham hisoblanadi
                _record_usage(
                    provider=candidate["provider"],
                    model=candidate["id"],
                    agent=agent,
                    workflow_id=workflow_id,
                    latency_ms=elapsed,
                    status="error",
                )
                continue
            payload = response.json()
            message = (payload.get("choices") or [{}])[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            # J-2: `reasoning_content` javob sifatida qaytarilmaydi — bu modelning
            # ichki mulohazasi, foydalanuvchiga javob bo'lib chiqmasligi kerak.
            content = (content or "").strip()
            if not content:
                attempts.append({"provider": candidate["provider"], "model": candidate["id"], "status": "empty"})
                last_error = f"{candidate['id']}: bo'sh javob"
                _record_usage(
                    provider=candidate["provider"],
                    model=candidate["id"],
                    agent=agent,
                    workflow_id=workflow_id,
                    latency_ms=elapsed,
                    status="empty",
                )
                continue
            if json_mode and extract_json(content) is None:
                # J-2: JSONMode'da JSON bo'lmagan javob keyingi modelga uzatiladi.
                attempts.append(
                    {
                        "provider": candidate["provider"],
                        "model": candidate["id"],
                        "status": "invalid_json",
                    }
                )
                last_error = f"{candidate['id']}: JSON formatida javob kelmadi"
                _record_usage(
                    provider=candidate["provider"],
                    model=candidate["id"],
                    agent=agent,
                    workflow_id=workflow_id,
                    latency_ms=elapsed,
                    status="invalid_json",
                )
                continue
            usage = payload.get("usage") or {}
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or prompt + completion)
            result = AIResult(
                content=content,
                provider=candidate["provider"],
                model=str(payload.get("model") or candidate["id"]),
                latency_ms=int((time.perf_counter() - started_all) * 1000),
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                attempts=attempts
                + [{"provider": candidate["provider"], "model": candidate["id"], "status": 200, "latency_ms": elapsed}],
                fallback_used=index > 0,
            )
            # J-3: sarf alohida sessiyada yoziladi (rollback'dan qat'i nazar).
            _record_usage(
                provider=result.provider,
                model=result.model,
                agent=agent,
                workflow_id=workflow_id,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                latency_ms=result.latency_ms,
                status="success",
            )
            return result
        except httpx.TimeoutException:
            attempts.append(
                {
                    "provider": candidate["provider"],
                    "model": candidate["id"],
                    "status": "timeout",
                    "error": f"{attempt_timeout:.0f}s ichida javob yo'q",
                }
            )
            last_error = f"{candidate['id']}: timeout"
            _record_usage(
                provider=candidate["provider"],
                model=candidate["id"],
                agent=agent,
                workflow_id=workflow_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status="timeout",
            )
        except Exception as error:
            attempts.append(
                {
                    "provider": candidate["provider"],
                    "model": candidate["id"],
                    "status": "error",
                    "error": str(error)[:300],
                }
            )
            last_error = f"{candidate['id']}: {error}"[:300]
            _record_usage(
                provider=candidate["provider"],
                model=candidate["id"],
                agent=agent,
                workflow_id=workflow_id,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status="error",
            )
    raise service_unavailable(f"Barcha AI modellari javob bermadi. Oxirgi xato: {last_error}")


def extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    for candidate in (text, text[text.find("{") : text.rfind("}") + 1] if "{" in text else ""):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None
