from __future__ import annotations

import typing

import httpx

from app.core.config import settings
from app.services import ai_gateway

def test_registry_annotation_is_tuple_list():
    hints = typing.get_type_hints(ai_gateway)
    assert hints["MODEL_REGISTRY"] == list[tuple[str, str, str, int, int]], (
        f"tip noto'g'ri: {hints['MODEL_REGISTRY']}"
    )

def test_registry_entries_are_five_element_tuples():
    for entry in ai_gateway.MODEL_REGISTRY:
        assert isinstance(entry, tuple), f"tuple emas: {entry!r}"
        assert len(entry) == 5, f"5 element kerak: {entry!r}"
        model_id, provider, label, context, rank = entry
        assert isinstance(model_id, str) and model_id
        assert isinstance(provider, str) and provider
        assert isinstance(label, str) and label
        assert isinstance(context, int) and context > 0
        assert isinstance(rank, int)

def _set_override(monkeypatch, value: dict) -> None:
    monkeypatch.setattr(
        type(settings),
        "ai_models_override",
        property(lambda self: value),
        raising=False,
    )

def test_override_ignores_non_mapping_items(monkeypatch):
    _set_override(monkeypatch, {"nvidia": [123, None, True, 4.5]})
    models = ai_gateway.available_models()
    assert models == [], f"noto'g'ri elementlar qabul qilindi: {models}"

def test_override_ignores_item_without_id(monkeypatch):
    _set_override(monkeypatch, {"nvidia": [{"label": "nomi bor, id yo'q"}]})
    models = ai_gateway.available_models()
    assert models == [], f"id'siz element qabul qilindi: {models}"

def test_override_ignores_non_numeric_context(monkeypatch):
    _set_override(monkeypatch, {"nvidia": [{"id": "nvidia/test", "context": "katta"}]})
    models = ai_gateway.available_models()
    assert models == [], f"noto'g'ri context qabul qilindi: {models}"

def test_override_accepts_valid_string_and_dict_items(monkeypatch):
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
    _set_override(monkeypatch, {"nvidia": "nvidia/one"})
    models = ai_gateway.available_models()
    assert models == []

def test_live_models_ttl_is_one_hour():
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
    _set_override(monkeypatch, {"nvidia": ["nvidia/one"]})
    monkeypatch.setattr(ai_gateway, "_provider_model_ids", lambda provider: None)
    models = ai_gateway.refresh_models()
    assert [item["id"] for item in models] == ["nvidia/one"]

def test_available_models_does_not_call_network(monkeypatch):

    def _boom(*args, **kwargs):
        raise AssertionError("tarmoqqa chiqildi")

    monkeypatch.setattr(ai_gateway, "_provider_models", _boom)
    monkeypatch.setattr(ai_gateway, "_provider_model_ids", _boom)
    _set_override(monkeypatch, {"nvidia": ["nvidia/one"]})
    models = ai_gateway.available_models()
    assert [item["id"] for item in models] == ["nvidia/one"]

def test_live_model_ids_are_cached(monkeypatch):
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

def test_resolve_model_rejects_unknown_id():
    models = [
        {"id": "nvidia/one", "provider": "nvidia", "label": "One", "context": 1000, "free": True, "capabilities": ["chat"], "rank": 0}
    ]
    assert ai_gateway.resolve_model(models, "nvidia/one") == "nvidia/one"
    assert ai_gateway.resolve_model(models, "nvidia/yo'q") == ""
    assert ai_gateway.resolve_model(models, "") == ""

def test_unknown_stored_model_is_never_requested(monkeypatch):
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
