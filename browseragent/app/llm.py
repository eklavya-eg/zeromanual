import os
from typing import Literal, cast

from browser_use import ChatOpenAI, ChatOpenRouter
from browser_use.llm.base import BaseChatModel
from dotenv import load_dotenv

load_dotenv()

LlmProvider = Literal["openai", "openrouter"]


class LlmConfigurationError(ValueError):
    pass


def create_llm(
    provider: LlmProvider | None = None,
    model: str | None = None,
) -> tuple[BaseChatModel, LlmProvider, str]:
    configured_provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    if configured_provider not in ("openai", "openrouter"):
        raise LlmConfigurationError(
            "LLM_PROVIDER must be either 'openai' or 'openrouter'"
        )

    selected_provider = cast(LlmProvider, configured_provider)
    if selected_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        selected_model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if not api_key:
            raise LlmConfigurationError("OPENAI_API_KEY is required")
        return (
            ChatOpenAI(model=selected_model, api_key=api_key),
            selected_provider,
            selected_model,
        )

    api_key = os.getenv("OPENROUTER_API_KEY")
    selected_model = model or os.getenv(
        "OPENROUTER_MODEL", "nvidia/nemotron-3.5-super-vl:free"
    )
    if not api_key:
        raise LlmConfigurationError("OPENROUTER_API_KEY is required")
    return (
        ChatOpenRouter(model=selected_model, api_key=api_key),
        selected_provider,
        selected_model,
    )
