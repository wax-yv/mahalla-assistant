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

MODEL_REGISTRY: list[dict[str, Any]] = [
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


def available_models() -> list[dict[str, Any]]:
    override = settings.ai_models_override or {}
    if override:
        models = []
        for provider, items in override.items():
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                model_id = item if isinstance(item, str) else item.get("id")
                if not model_id:
                    continue
                models.append(
                    {
                        "id": model_id,
                        "provider": provider,
                        "label": model_id if isinstance(item, str) else item.get("label", model_id),
                        "context": 0 if isinstance(item, str) else int(item.get("context", 0)),
                        "free": True,
                        "capabilities": ["chat"],
                        "rank": index,
                    }
                )
        return models
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


def _live_provider_check(provider: str) -> tuple[bool, str]:
    """Provayder /models endpointini qisqa so'rov bilan tekshirish."""
    try:
        url, headers = _endpoint(provider)
        models_url = url.rsplit("/chat/completions", 1)[0] + "/models"
        with httpx.Client(timeout=8) as client:
            response = client.get(models_url, headers=headers)
        if response.status_code == 200:
            payload = response.json()
            count = len(payload.get("data") or payload.get("models") or [])
            return True, f"Ulangan — {count} model mavjud"
        if response.status_code in (401, 403):
            return False, "API kaliti rad etildi (401/403)"
        return False, f"Server javobi: HTTP {response.status_code}"
    except httpx.HTTPError as error:
        return False, f"Ulanmadi: {type(error).__name__}"


def provider_status(live: bool = True) -> list[dict[str, Any]]:
    models = available_models()
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
    active_model = preferred_model or stored_model(db)
    if active_model:
        candidates = order_models(candidates, active_model)
    if preferred_provider in {"nvidia", "openrouter"}:
        head = [m for m in candidates if m["provider"] == preferred_provider]
        tail = [m for m in candidates if m["provider"] != preferred_provider]
        candidates = head + tail
    if not candidates:
        raise service_unavailable("AI provayderlari sozlanmagan.")
    attempts: list[dict[str, Any]] = []
    last_error = "Model javob bermadi."
    started_all = time.perf_counter()
    for index, candidate in enumerate(candidates):
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
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=settings.ai_request_timeout) as client:
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
                continue
            payload = response.json()
            message = (payload.get("choices") or [{}])[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            content = (content or message.get("reasoning_content") or "").strip()
            if not content:
                attempts.append({"provider": candidate["provider"], "model": candidate["id"], "status": "empty"})
                last_error = f"{candidate['id']}: bo'sh javob"
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
            db.add(
                AIUsage(
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
            )
            db.flush()
            return result
        except httpx.TimeoutException:
            attempts.append(
                {
                    "provider": candidate["provider"],
                    "model": candidate["id"],
                    "status": "timeout",
                    "error": f"{settings.ai_request_timeout}s ichida javob yo'q",
                }
            )
            last_error = f"{candidate['id']}: timeout"
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
