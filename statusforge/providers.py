"""Provider catalog for the LLM narrator.

SAFETY (load-bearing): a key is NEVER written to os.environ — Streamlit Community
Cloud runs one shared process for all visitors, so a process-global key would leak
across concurrent sessions. Keys are always passed PER CALL as api_key=... to
litellm.completion(). This module only holds the static catalog + model defaults.
"""

from __future__ import annotations

# Human label -> default LiteLLM model. Free providers first.
PROVIDER_CATALOG: dict[str, str] = {
    "Groq (free)":       "groq/llama-3.3-70b-versatile",
    "OpenRouter (free)": "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "OpenAI":            "openai/gpt-4.1-mini",
    "Anthropic":         "anthropic/claude-sonnet-4-5",
    "Google Gemini":     "gemini/gemini-2.0-flash",
}


def default_model(provider_label: str) -> str:
    return PROVIDER_CATALOG.get(provider_label, "groq/llama-3.3-70b-versatile")


def owner_groq_key() -> str:
    """The owner's shared Groq key from Streamlit secrets, or '' if none.

    Wrapped so a local checkout / CI (no secrets.toml) stays on the offline path
    instead of raising. Never falls back to os.environ.
    """
    try:
        import streamlit as st
        return str(st.secrets.get("GROQ_API_KEY", "")) if hasattr(st, "secrets") else ""
    except Exception:
        return ""
