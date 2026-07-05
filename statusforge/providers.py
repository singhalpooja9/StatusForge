"""Provider catalog for the LLM narrator, shared by extract.py and narrate.py.

Supports several providers through LiteLLM. FREE options: Groq, OpenRouter.

SAFETY (load-bearing): a visitor's API key is NEVER written to os.environ or any
global — Streamlit Community Cloud runs one shared process for all visitors, so a
process-global key would leak across concurrent sessions. The key is always passed
PER CALL as `api_key=...` straight to litellm.completion(). This module only holds
the static provider catalog + model defaults; it never stores a key.
"""

from __future__ import annotations

# Human label -> (default LiteLLM model). Free providers listed first.
PROVIDER_CATALOG: dict[str, str] = {
    "Groq (free)":          "groq/llama-3.3-70b-versatile",
    "OpenRouter (free)":    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "OpenAI":               "openai/gpt-4.1-mini",
    "Anthropic":            "anthropic/claude-sonnet-4-5",
    "Google Gemini":        "gemini/gemini-2.0-flash",
}


def default_model(provider_label: str) -> str:
    """Default LiteLLM model string for a provider label."""
    return PROVIDER_CATALOG.get(provider_label, "groq/llama-3.3-70b-versatile")
