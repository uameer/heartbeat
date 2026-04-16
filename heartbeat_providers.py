import os
from typing import Optional

PROVIDER = os.getenv("HEARTBEAT_PROVIDER", "anthropic").lower()
OPENAI_MODEL = os.getenv("HEARTBEAT_OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = os.getenv("HEARTBEAT_ANTHROPIC_MODEL", "claude-3-7-sonnet-latest")
OLLAMA_MODEL = os.getenv("HEARTBEAT_OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_BASE_URL = os.getenv("HEARTBEAT_OLLAMA_BASE_URL", "http://localhost:11434")
GEMINI_MODEL = os.getenv("HEARTBEAT_GEMINI_MODEL", "gemini-3.1-flash-lite-preview")


def build_client(provider: str):
    """Lazy import provider client to avoid unnecessary import failures."""
    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable not set")
        from openai import OpenAI
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    if provider == "ollama":
        from openai import OpenAI
        return OpenAI(
            base_url=f"{OLLAMA_BASE_URL}/v1",
            api_key="ollama",
        )

    if provider == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY environment variable not set")
        from openai import OpenAI
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.environ["GEMINI_API_KEY"],
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def choose_model(provider: str, model_override: Optional[str]) -> str:
    if model_override:
        return model_override
    if provider == "openai":
        return OPENAI_MODEL
    if provider == "ollama":
        return OLLAMA_MODEL
    if provider == "gemini":
        return GEMINI_MODEL
    return ANTHROPIC_MODEL
