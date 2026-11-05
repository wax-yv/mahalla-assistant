"""D-8: UI'da tanlangan provayder/model chat zanjirida qo'llanadi.

Muammo (audit D-8): `preferred_provider` `chat()` ga uzatilardi, lekin
hech qayerda ishlatilmasdi; `preferred_model` faqat smalltalk'da —
foydalanuvchi tanlovi e'tiborsiz qolardi.
"""

from __future__ import annotations

import inspect

from app.services import agents, legislation


def test_smalltalk_passes_provider_and_model():
    """`_smalltalk` provayder va modelni gateway'ga uzatadi."""
    source = inspect.getsource(agents._smalltalk)
    assert "preferred_provider=" in source
    assert "preferred_model=" in source


def test_chat_context_carries_preferences():
    """`chat()` handler'ga uzatadigan kontekstda tanlovlar bor."""
    source = inspect.getsource(agents.chat)
    assert '"preferred_provider": preferred_provider' in source
    assert '"preferred_model": preferred_model' in source


def test_legislation_ask_accepts_preferences():
    """`legislation.ask` provayder/model parametrlarini qabul qiladi."""
    signature = inspect.signature(legislation.ask)
    assert "preferred_provider" in signature.parameters
    assert "preferred_model" in signature.parameters
    body = inspect.getsource(legislation.ask)
    assert "preferred_provider=preferred_provider" in body


def test_legislation_agent_forwards_preferences():
    """Legislation agenti kontekstdagi tanlovlarni uzatadi."""
    source = inspect.getsource(agents._legislation_agent)
    assert 'context.get("preferred_provider")' in source
