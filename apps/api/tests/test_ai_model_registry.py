"""O-9: model reyestri — tip, override validatsiyasi va mavjud model tekshiruvi.

Muqova:
- `MODEL_REGISTRY: list[dict[str, Any]]` deb belgilangan, lekin ichida
  **tuple**lar bor — tur tekshiruvchi (mypy) xato beradi.
- `AI_MODEL_CONFIG_JSON` override'ida noto'g'ri element turi
  (`item.get` → `AttributeError`) yoki noto'g'ri `context` (`int()` →
  `ValueError`) bo'lsa butun model ro'yxati ishlashdan to'xtaydi.
- Mavjud bo'lmagan model ID har chaqiruvda bekor tarmoq so'rovi va
  kechikish keltiradi.

To'g'rilash: tur to'g'ri belgilanadi; override elementlari turi va kaliti
bo'yicha tekshiriladi (noto'g'ri elementlar jimgina o'tkazib yuboriladi);
modellar provayderning jonli `/models` ro'yxati bilan kesishtiriladi
(1 soat kesh) — mavjud bo'lmagan model ishga tushmaydi.
"""

from __future__ import annotations

import typing

import httpx

from app.core.config import settings
from app.services import ai_gateway


# ------------------------------------------------------------------ tip


def test_registry_annotation_is_tuple_list():
    """`MODEL_REGISTRY` tipi tuple ro'yxatini ko'rsatishi kerak."""
    hints = typing.get_type_hints(ai_gateway)
    assert hints["MODEL_REGISTRY"] == list[tuple[str, str, str, int, int]], (
        f"tip noto'g'ri: {hints['MODEL_REGISTRY']}"
    )


def test_registry_entries_are_five_element_tuples():
    """Har bir registratsiya yozuvi 5 elementli tuple bo'lishi kerak."""
    for entry in ai_gateway.MODEL_REGISTRY:
        assert isinstance(entry, tuple), f"tuple emas: {entry!r}"
        assert len(entry) == 5, f"5 element kerak: {entry!r}"
        model_id, provider, label, context, rank = entry
        assert isinstance(model_id, str) and model_id
        assert isinstance(provider, str) and provider
        assert isinstance(label, str) and label
        assert isinstance(context, int) and context > 0
        assert isinstance(rank, int)


# ------------------------------------------------------------- override


def _set_override(monkeypatch, value: dict) -> None:
    monkeypatch.setattr(
        type(settings),
        "ai_models_override",
        property(lambda self: value),
        raising=False,
    )


def test_override_ignores_non_mapping_items(monkeypatch):
    """Noto'g'ri turdagi elementlar jimgina o'tkazib yuboriladi (xato emas)."""
    _set_override(monkeypatch, {"nvidia": [123, None, True, 4.5]})
    models = ai_gateway.available_models()
    assert models == [], f"noto'g'ri elementlar qabul qilindi: {models}"


def test_override_ignores_item_without_id(monkeypatch):
    """`id` kaliti yo'q elementlar o'tkazib yuboriladi."""
    _set_override(monkeypatch, {"nvidia": [{"label": "nomi bor, id yo'q"}]})
    models = ai_gateway.available_models()
    assert models == [], f"id'siz element qabul qilindi: {models}"


def test_override_ignores_non_numeric_context(monkeypatch):
    """`context` raqam bo'lmasa element o'tkazib yuboriladi (ValueError emas)."""
    _set_override(monkeypatch, {"nvidia": [{"id": "nvidia/test", "context": "katta"}]})
    models = ai_gateway.available_models()
    assert models == [], f"noto'g'ri context qabul qilindi: {models}"


def test_override_accepts_valid_string_and_dict_items(monkeypatch):
    """To'g'ri formatdagi elementlar qabul qilinadi."""
    _set_override(
        monkeypatch,
        {"nvidia": ["nvidia/one", {"id": "nvidia/two", "label": "Ikki", "context": 4096}]},
    )
    models = ai_gateway.available_models()
    ids = [item["id"] for item in models]
    assert ids == ["nvidia/one", "nvidia/two"], f"model ro'yxati noto'g'ri: {ids}"
    assert models[1]["label"] == "Ikki"
    assert models[1]["context"] == 4096


def test_override_ignores_provider_with_non_list_items(monkeypatch):
    """Provider qiymati ro'yxat bo'lmasa o'tkazib yuboriladi."""
    _set_override(monkeypatch, {"nvidia": "nvidia/one"})
    models = ai_gateway.available_models()
    assert models == []


# --------------------------------------------------- jonli model ro'yxati


def test_live_models_ttl_is_one_hour():
    """Jonli ro'yxat keshi 1 soat bo'lishi kerak."""
    assert ai_gateway.LIVE_MODELS_TTL_SECONDS == 3600


class _ModelsResponse:
    status_code = 200

    def __init__(self, ids: list[str]):
        self._ids = ids

    def json(self):
        return {"data": [{"id": model_id} for model_id in self._ids]}


class _ModelsClient:
    calls: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None):
        _ModelsClient.calls.append(url)
        return _ModelsResponse(["nvidia/one", "nvidia/two"])


def test_refresh_intersects_with_live_provider_models(monkeypatch):
    """Faqat provayderda mavjud modellar ishga tushadi."""
    _set_override(
        monkeypatch,
        {"nvidia": ["nvidia/one", "nvidia/yo'q"]},
    )
    monkeypatch.setattr(ai_gateway, "_provider_model_ids", lambda provider: {"nvidia/one"})
    models = ai_gateway.refresh_models()
    assert [item["id"] for item in models] == ["nvidia/one"], (
        f"mavjud bo'lmagan model qoldi: {models}"
    )


def test_refresh_kept_when_live_check_unavailable(monkeypatch):
    """Jonli tekshiruv imkonsiz bo'lsa — sozlamadagi ro'yxat ishlatiladi."""
    _set_override(monkeypatch, {"nvidia": ["nvidia/one"]})
    monkeypatch.setattr(ai_gateway, "_provider_model_ids", lambda provider: None)
    models = ai_gateway.refresh_models()
    assert [item["id"] for item in models] == ["nvidia/one"]


def test_available_models_does_not_call_network(monkeypatch):
    """`available_models()` so'rov yo'lida tarmoqqa chiqmasligi kerak."""

    def _boom(*args, **kwargs):
        raise AssertionError("tarmoqqa chiqildi")

    monkeypatch.setattr(ai_gateway, "_provider_models", _boom)
    monkeypatch.setattr(ai_gateway, "_provider_model_ids", _boom)
    _set_override(monkeypatch, {"nvidia": ["nvidia/one"]})
    models = ai_gateway.available_models()
    assert [item["id"] for item in models] == ["nvidia/one"]


def test_live_model_ids_are_cached(monkeypatch):
    """Jonli ro'yxat 1 soat kesh bilan bir marta yuklanadi."""
    _ModelsClient.calls = []
    monkeypatch.setattr(httpx, "Client", _ModelsClient)
    monkeypatch.setattr(settings, "nvidia_nim_api_key", "test-key")
    ai_gateway._provider_models_cache.clear()

    first = ai_gateway._provider_model_ids("nvidia")
    second = ai_gateway._provider_model_ids("nvidia")

    assert first == {"nvidia/one", "nvidia/two"}
    assert second == first
    assert len(_ModelsClient.calls) == 1, (
        f"kesh ishlamadi: {_ModelsClient.calls} ta so'rov"
    )
    ai_gateway._provider_models_cache.clear()


# --------------------------------------------- mavjud bo'lmagan model ID


def test_resolve_model_rejects_unknown_id():
    """Noma'lum model ID bo'sh string'ga aylanadi (so'rov yuborilmaydi)."""
    models = [
        {"id": "nvidia/one", "provider": "nvidia", "label": "One", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 0}
    ]
    assert ai_gateway.resolve_model(models, "nvidia/one") == "nvidia/one"
    assert ai_gateway.resolve_model(models, "nvidia/yo'q") == ""
    assert ai_gateway.resolve_model(models, "") == ""


def test_unknown_stored_model_is_never_requested(monkeypatch):
    """Saqlangan model mavjud bo'lmasa — u so'rovga yuborilmasligi kerak."""
    requested: list[str] = []

    class _Response:
        status_code = 200
        text = "fake"

        def json(self):
            return {
                "model": "nvidia/one",
                "choices": [{"message": {"content": "Salom"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            requested.append(json["model"])
            return _Response()

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(
        ai_gateway,
        "available_models",
        lambda: [
            {"id": "nvidia/one", "provider": "nvidia", "label": "One", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 0}
        ],
    )
    monkeypatch.setattr(ai_gateway, "stored_model", lambda db: "nvidia/yo'q")

    from app.core.db import SessionLocal

    with SessionLocal() as db:
        result = ai_gateway.chat_completion(
            db, messages=[{"role": "user", "content": "salom"}], agent="test-o9"
        )

    assert result.content == "Salom"
    assert "nvidia/yo'q" not in requested, (
        f"mavjud bo'lmagan model so'rovga yuborildi: {requested}"
    )
    assert requested == ["nvidia/one"], f" kutilgan faqat mavjud model: {requested}"
