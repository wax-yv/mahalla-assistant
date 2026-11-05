from __future__ import annotations

import inspect

from app.services import agents, legislation


def test_smalltalk_passes_provider_and_model():
    source = inspect.getsource(agents._smalltalk)
    assert "preferred_provider=" in source
    assert "preferred_model=" in source

def test_chat_context_carries_preferences():
    source = inspect.getsource(agents.chat)
    assert '"preferred_provider": preferred_provider' in source
    assert '"preferred_model": preferred_model' in source

def test_legislation_ask_accepts_preferences():
    signature = inspect.signature(legislation.ask)
    assert "preferred_provider" in signature.parameters
    assert "preferred_model" in signature.parameters
    body = inspect.getsource(legislation.ask)
    assert "preferred_provider=preferred_provider" in body

def test_legislation_agent_forwards_preferences():
    source = inspect.getsource(agents._legislation_agent)
    assert 'context.get("preferred_provider")' in source
