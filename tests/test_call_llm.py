import os
import pytest

import teacherflow.utils.call_llm as llm_module
from teacherflow.utils.call_llm import call_llm, _call_llm_gemini
from google.auth.exceptions import DefaultCredentialsError


def test_gemini_adc_error(monkeypatch):
    """When ADC are missing and project ID is set we emit a helpful message."""
    # configure environment as if using Gemini with project ID only
    monkeypatch.setenv("LLM_PROVIDER", "GEMINI")
    monkeypatch.setenv("GEMINI_PROJECT_ID", "some-project")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # simulate google.auth.default throwing DefaultCredentialsError
    import google.auth

    def fake_default(scopes=None):
        raise DefaultCredentialsError("no creds")

    monkeypatch.setattr(google.auth, "default", fake_default)

    with pytest.raises(RuntimeError) as excinfo:
        _call_llm_gemini("prompt")

    msg = str(excinfo.value)
    assert "application default credentials" in msg.lower()
    assert "gemini" in msg.lower()


def test_call_llm_uses_cache(tmp_path, monkeypatch):
    """Smoke test to ensure call_llm cache logic doesn't crash."""
    # use a dummy provider to avoid network
    monkeypatch.setenv("LLM_PROVIDER", "DUMMY")

    # monkeypatch internal provider call to just echo prompt
    def fake_provider(prompt, use_cache=True):
        return f"echo:{prompt}"

    monkeypatch.setattr(llm_module, "_call_llm_provider", fake_provider)

    # first call should store in cache
    result1 = call_llm("hi", use_cache=True)
    assert result1 == "echo:hi"
    # second call should be served from cache
    result2 = call_llm("hi", use_cache=True)
    assert result2 == result1
